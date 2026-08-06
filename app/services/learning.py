"""低操作成本教学：一次输入，自动拆解，最小确认。"""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection

from app.config import settings
from app.services.articles import create_article, get_article_version
from app.services.knowledge import approve_knowledge, create_knowledge
from app.services.llm import LlmError, structured_chat
from app.services.ai_settings import get_ai_setting

PROMPT_VERSION = "low-friction-v1"
VALID_DIMENSIONS = {
    "title", "opening", "body", "closing", "hashtag", "tone", "structure",
    "selling_point", "compliance", "creator_fit", "visual", "overall", "other",
}
VALID_SENTIMENTS = {"positive", "negative", "revision", "neutral"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_CONTENT_TYPES = {
    "大曝光笔记", "强种草笔记", "搜索承接笔记", "信任背书笔记",
    "场景心智笔记", "产品认知笔记", "对比决策笔记", "口碑扩散笔记",
    "活动转化笔记", "品牌价值笔记", "互动讨论笔记", "低效宣传笔记",
}


def learning_input_hash(
    learning_mode: str,
    original_content_hash: str | None,
    revised_content_hash: str | None,
    user_feedback: str | None,
) -> str:
    """生成稳定输入指纹；忽略无意义空白，但保留用户评价差异。"""
    normalized_feedback = re.sub(r"\s+", " ", (user_feedback or "").strip())
    source = "|".join((learning_mode, original_content_hash or "", revised_content_hash or "", normalized_feedback))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def text_changes(before: str, after: str) -> list[dict[str, str]]:
    """先用确定性算法压缩前后稿差异，减少模型输入和幻觉。"""
    before_lines = [line.strip() for line in before.splitlines() if line.strip()]
    after_lines = [line.strip() for line in after.splitlines() if line.strip()]
    changes: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, before_lines, after_lines).get_opcodes():
        if tag == "equal":
            continue
        changes.append({
            "operation": {"replace": "替换", "delete": "删除", "insert": "新增"}.get(tag, tag),
            "before": "\n".join(before_lines[i1:i2]),
            "after": "\n".join(after_lines[j1:j2]),
        })
    return changes


def _article_text(version: dict[str, Any]) -> str:
    hashtags = " ".join(f"#{tag}" for tag in version.get("hashtags", []))
    return "\n\n".join(x for x in [version.get("title", ""), version.get("body", ""), hashtags] if x)


def _system_prompt() -> str:
    return """你是品牌小红书内容运营的教学理解器。用户只会给整体评价，你必须主动拆解，不得要求用户逐项说明。
你的任务是从正例、反例、前后稿或运营经验中提炼可复用但有适用边界的候选经验。
严格区分：用户明确表达的事实、文本可观察证据、你的推断。不要虚构图片内容；没有图片描述时不得产出visual洞察。
前后稿差异不等于修改原因；原因只能标记为推断，并降低置信度。不要把单篇案例夸大为普遍规则。
只返回JSON对象，格式：
{"summary":"一句总结","insights":[{"dimension":"title|opening|body|closing|hashtag|tone|structure|selling_point|compliance|creator_fit|visual|overall|other","sentiment":"positive|negative|revision|neutral","evidence_before":"原文证据或空","evidence_after":"改后证据或空","judgment":"具体判断","rationale":"为什么","reusable_rule":"带适用条件的候选规则","applicability":{},"exceptions":{},"reason_codes":[],"severity":"low|medium|high|critical或null","confidence":0到1,"needs_confirmation":true或false,"confirmation_reason":"需要确认的原因或空"}]}
以下情况 needs_confirmation 必须为true：置信度低于0.8、合规高风险、缺乏直接证据、修改原因主要靠推断、与用户评价可能不一致。"""


def _classification_prompt_contract() -> str:
    """把 CRISPE 分类压缩为稳定的结构化输出契约，并与经验提炼共用一次调用。"""
    return """
除候选经验外，还要判断学习目标文章的首要运营任务。若有修改后文章，以修改后文章为学习目标；否则以原始文章为目标。纯经验输入则 content_classification 返回 null。
可选主类型仅限：大曝光笔记、强种草笔记、搜索承接笔记、信任背书笔记、场景心智笔记、产品认知笔记、对比决策笔记、口碑扩散笔记、活动转化笔记、品牌价值笔记、互动讨论笔记、低效宣传笔记。
主类型只能有一个；辅助类型最多两个且不能与主类型重复。不要因为出现产品名就判为强种草，也不要因为标题吸睛就判为大曝光。必须根据内容篇幅、最强刺激、用户阅读后最可能行为和产品是否构成核心解决方案判断。
在原 JSON 对象顶层增加：
"content_classification":{"primary_type":"上述类型之一","secondary_types":["最多两个类型"],"target_audience":["核心人群"],"user_stage":"无认知|有需求|正在比较|存在顾虑|准备行动","expected_user_change":"阅读后的认知或行为变化","confidence":0到100整数,"objective_score":0到100整数,"rationale":"主类型判断依据","evidence":["原文、结构或图片证据"],"content_mechanism":{"title":"标题作用","opening":"开头作用","body":"正文机制","visuals":"视觉作用或信息不足","trust":"信任证据或未建立","call_to_action":"行动引导或不明确"},"missing_information":[]}
"""


def _normalize_classification(raw: dict[str, Any]) -> dict[str, Any] | None:
    item = raw.get("content_classification")
    if not isinstance(item, dict) or item.get("primary_type") not in VALID_CONTENT_TYPES:
        return None
    secondary = [x for x in item.get("secondary_types", []) if x in VALID_CONTENT_TYPES and x != item["primary_type"]][:2]
    return {
        "primary_type": item["primary_type"],
        "secondary_types": secondary,
        "target_audience": item.get("target_audience", []) if isinstance(item.get("target_audience"), list) else [],
        "user_stage": str(item.get("user_stage", ""))[:50],
        "expected_user_change": str(item.get("expected_user_change", ""))[:1000],
        "confidence": max(0, min(100, int(item.get("confidence", 0)))),
        "objective_score": max(0, min(100, int(item.get("objective_score", 0)))),
        "rationale": str(item.get("rationale", ""))[:4000] or "模型未提供详细依据",
        "evidence": item.get("evidence", []) if isinstance(item.get("evidence"), list) else [],
        "content_mechanism": item.get("content_mechanism", {}) if isinstance(item.get("content_mechanism"), dict) else {},
        "missing_information": item.get("missing_information", []) if isinstance(item.get("missing_information"), list) else [],
    }


def _normalize_insights(raw: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for item in raw.get("insights", [])[:30]:
        if not all(str(item.get(k, "")).strip() for k in ("judgment", "rationale", "reusable_rule")):
            continue
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        dimension = item.get("dimension", "other")
        sentiment = item.get("sentiment", "neutral")
        severity = item.get("severity")
        normalized.append({
            **item,
            "dimension": dimension if dimension in VALID_DIMENSIONS else "other",
            "sentiment": sentiment if sentiment in VALID_SENTIMENTS else "neutral",
            "severity": severity if severity in VALID_SEVERITIES else None,
            "confidence": confidence,
            "needs_confirmation": bool(item.get("needs_confirmation", False)) or confidence < 0.8,
            "applicability": item.get("applicability") if isinstance(item.get("applicability"), dict) else {},
            "exceptions": item.get("exceptions") if isinstance(item.get("exceptions"), dict) else {},
            "reason_codes": item.get("reason_codes") if isinstance(item.get("reason_codes"), list) else [],
        })
    if not normalized:
        raise LlmError("模型没有提炼出有效的候选经验。")
    return normalized


def enqueue_learning_session(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    """仅登记后台任务并立即返回，供自动吸收模式连续导入。"""
    brand = conn.execute("SELECT id FROM brands WHERE code=%s", (data["brand_code"],)).fetchone()
    if not brand:
        raise ValueError(f"品牌不存在：{data['brand_code']}")
    request_hash = hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    existing = conn.execute(
        """SELECT id,status FROM kb_jobs WHERE brand_id=%s AND job_type='ingest_learning'
           AND payload->>'request_hash'=%s AND status IN ('pending','running','succeeded')
           ORDER BY created_at DESC LIMIT 1""",
        (brand["id"], request_hash),
    ).fetchone()
    if existing:
        return {"accepted": True, "deduplicated": True, "job_id": existing["id"], "status": existing["status"]}
    job = conn.execute(
        """INSERT INTO kb_jobs(brand_id,job_type,entity_type,entity_id,payload,max_attempts)
           VALUES (%s,'ingest_learning','learning_request',%s,%s::jsonb,3) RETURNING id,status""",
        (brand["id"], uuid4(), json.dumps({"request_hash": request_hash, "learning_data": data,
                                           "auto_confirm": True}, ensure_ascii=False, default=str)),
    ).fetchone()
    return {"accepted": True, "deduplicated": False, "job_id": job["id"], "status": job["status"]}


def create_learning_session(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    """完成一键文章摄入与分析；分析失败也保留会话，便于重试。"""
    brand = conn.execute("SELECT id FROM brands WHERE code = %s", (data["brand_code"],)).fetchone()
    if not brand:
        raise ValueError(f"品牌不存在：{data['brand_code']}")

    original_id = revised_id = None
    original_version = revised_version = None
    if data.get("original_article"):
        article_data = {**data["original_article"], "brand_code": data["brand_code"]}
        result = create_article(conn, article_data)
        original_id = result["article_version_id"]
        original_version = get_article_version(conn, original_id)
    if data.get("revised_article"):
        article_data = {**data["revised_article"], "brand_code": data["brand_code"]}
        result = create_article(conn, article_data)
        revised_id = result["article_version_id"]
        revised_version = get_article_version(conn, revised_id)
    if data["learning_mode"] != "experience" and not original_version:
        raise ValueError("文章教学必须提供 original_article。")
    if data["learning_mode"] == "revision_pair" and not revised_version:
        raise ValueError("前后稿教学必须同时提供 revised_article。")
    if data["learning_mode"] == "experience" and not data.get("user_feedback"):
        raise ValueError("纯经验教学必须提供 user_feedback。")

    input_hash = learning_input_hash(
        data["learning_mode"],
        original_version.get("content_hash") if original_version else None,
        revised_version.get("content_hash") if revised_version else None,
        data.get("user_feedback"),
    )
    existing = conn.execute(
        "SELECT id FROM xhs_learning_sessions WHERE brand_id=%s AND input_hash=%s",
        (brand["id"], input_hash),
    ).fetchone()
    if existing:
        result = get_learning_session(conn, existing["id"])
        result["deduplicated"] = True
        return result

    session = conn.execute(
        """INSERT INTO xhs_learning_sessions(
               brand_id, learning_mode, original_article_version_id,
               revised_article_version_id, user_feedback, created_by, input_hash
           ) VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (brand_id, input_hash) WHERE input_hash IS NOT NULL DO NOTHING
           RETURNING id""",
        (brand["id"], data["learning_mode"], original_id, revised_id,
         data.get("user_feedback"), data.get("created_by"), input_hash),
    ).fetchone()
    if not session:
        existing = conn.execute(
            "SELECT id FROM xhs_learning_sessions WHERE brand_id=%s AND input_hash=%s",
            (brand["id"], input_hash),
        ).fetchone()
        result = get_learning_session(conn, existing["id"])
        result["deduplicated"] = True
        return result

    target_image_version = revised_id or original_id
    analyzed_images = []
    if target_image_version:
        analyzed_images = [dict(row) for row in conn.execute(
            """SELECT ordinal,asset_role,visual_type,summary,ocr_text,product_exposure,
                      aesthetic,content_functions,brand_fit_score,cover_click_score,
                      selling_power_score,compliance_risks,evidence,reusable_visual_rules,confidence
               FROM xhs_image_analyses WHERE article_version_id=%s AND status='succeeded'
               ORDER BY ordinal""", (target_image_version,),
        ).fetchall()]
    prompt_data = {
        "教学类型": data["learning_mode"],
        "用户的一句话说明": data.get("user_feedback") or "未提供，请仅根据材料谨慎推断",
        "原始文章": _article_text(original_version) if original_version else None,
        "修改后文章": _article_text(revised_version) if revised_version else None,
        "确定性文本差异": text_changes(
            _article_text(original_version), _article_text(revised_version)
        ) if original_version and revised_version else [],
        "上下文": data.get("context", {}),
        "图片线索": data.get("image_context", []) or analyzed_images,
    }
    try:
        model_config = get_ai_setting(
            conn, data["brand_code"], "content_learning", include_secret=True
        )
        raw = structured_chat(
            _system_prompt() + _classification_prompt_contract(), json.dumps(prompt_data, ensure_ascii=False), model_config=model_config
        )
        insights = _normalize_insights(raw)
        classification = _normalize_classification(raw)
        for ordinal, insight in enumerate(insights):
            conn.execute(
                """INSERT INTO xhs_learning_insights(
                       session_id, ordinal, dimension, sentiment, location_data,
                       evidence_before, evidence_after, judgment, rationale, reusable_rule,
                       applicability, exceptions, reason_codes, severity, confidence,
                       needs_confirmation, confirmation_reason
                   ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s)""",
                (session["id"], ordinal, insight["dimension"], insight["sentiment"],
                 json.dumps(insight.get("location_data", {}), ensure_ascii=False),
                 insight.get("evidence_before"), insight.get("evidence_after"), insight["judgment"],
                 insight["rationale"], insight["reusable_rule"],
                 json.dumps(insight["applicability"], ensure_ascii=False),
                 json.dumps(insight["exceptions"], ensure_ascii=False), insight["reason_codes"],
                 insight["severity"], insight["confidence"], insight["needs_confirmation"],
                 insight.get("confirmation_reason")),
            )
        if classification and (revised_id or original_id):
            target_version_id = revised_id or original_id
            target_role = "revised" if revised_id else "original"
            conn.execute(
                """INSERT INTO xhs_content_type_labels(
                       session_id, article_version_id, label_role, primary_type, secondary_types,
                       target_audience, user_stage, expected_user_change, confidence, objective_score,
                       rationale, evidence, content_mechanism, missing_information
                   ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)""",
                (session["id"], target_version_id, target_role, classification["primary_type"],
                 json.dumps(classification["secondary_types"], ensure_ascii=False),
                 json.dumps(classification["target_audience"], ensure_ascii=False), classification["user_stage"],
                 classification["expected_user_change"], classification["confidence"],
                 classification["objective_score"], classification["rationale"],
                 json.dumps(classification["evidence"], ensure_ascii=False),
                 json.dumps(classification["content_mechanism"], ensure_ascii=False),
                 json.dumps(classification["missing_information"], ensure_ascii=False)),
            )
        needs_count = sum(x["needs_confirmation"] for x in insights)
        status = "needs_confirmation" if needs_count else "ready"
        conn.execute(
            """UPDATE xhs_learning_sessions SET status=%s, analysis_summary=%s,
                      model_name=%s, raw_analysis=%s::jsonb, completed_at=now() WHERE id=%s""",
            (status, str(raw.get("summary", "")),
             model_config["model_name"] if model_config else settings.llm_model,
             json.dumps(raw, ensure_ascii=False), session["id"]),
        )
        result = get_learning_session(conn, session["id"])
        result["deduplicated"] = False
        return result
    except Exception as exc:
        conn.execute(
            "UPDATE xhs_learning_sessions SET status='failed', error_message=%s, completed_at=now() WHERE id=%s",
            (str(exc)[:2000], session["id"]),
        )
        result = get_learning_session(conn, session["id"])
        result["deduplicated"] = False
        return result


def get_learning_session(conn: Connection, session_id: UUID) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM xhs_learning_sessions WHERE id=%s", (session_id,)).fetchone()
    if not session:
        raise ValueError("教学会话不存在。")
    insights = conn.execute(
        "SELECT * FROM xhs_learning_insights WHERE session_id=%s ORDER BY ordinal", (session_id,)
    ).fetchall()
    content_labels = conn.execute(
        "SELECT * FROM xhs_content_type_labels WHERE session_id=%s ORDER BY created_at", (session_id,)
    ).fetchall()
    return {
        "session": session,
        "insights": insights,
        "content_type_labels": content_labels,
        "operation_summary": {
            "total": len(insights),
            "focus_confirmation_count": sum(bool(x["needs_confirmation"]) for x in insights),
            "hint": "只需重点检查 needs_confirmation=true 的项目；其余可整批确认。",
        },
    }


def confirm_learning_session(conn: Connection, session_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    """一次确认整批；用户只需列出少数例外，而不必逐条操作。"""
    session_data = get_learning_session(conn, session_id)
    session = session_data["session"]
    if session["status"] == "confirmed":
        raise ValueError("该教学会话已经确认，不能重复吸收。")
    rejected = {str(x) for x in data.get("rejected_insight_ids", [])}
    corrections = {str(x["insight_id"]): x["correction"] for x in data.get("corrections", [])}
    content_label = session_data.get("content_type_labels", [])
    content_label = content_label[0] if content_label else None
    knowledge_ids = []
    for insight in session_data["insights"]:
        insight_id = str(insight["id"])
        if insight_id in rejected:
            conn.execute("UPDATE xhs_learning_insights SET status='rejected' WHERE id=%s", (insight["id"],))
            continue
        correction = corrections.get(insight_id)
        rule = correction or insight["reusable_rule"]
        status = "edited" if correction else "accepted"
        knowledge = create_knowledge(conn, {
            "brand_code": conn.execute("SELECT code FROM brands WHERE id=%s", (session["brand_id"],)).fetchone()["code"],
            "canonical_key": f"learning.insight.{insight['id']}",
            "knowledge_type": "review_annotation",
            "title": f"运营经验：{insight['judgment'][:50]}",
            "summary": insight["judgment"], "content": rule,
            "authority_level": 2, "confidence": float(insight["confidence"]),
            "scope": insight["applicability"],
            "attributes": {"learning_session_id": str(session_id), "dimension": insight["dimension"],
                           "sentiment": insight["sentiment"], "exceptions": insight["exceptions"],
                           "reason_codes": insight["reason_codes"], "human_confirmed": True,
                           "content_primary_type": content_label["primary_type"] if content_label else None,
                           "content_secondary_types": content_label["secondary_types"] if content_label else []},
            "chunks": [{"chunk_type": "reason", "text": "\n".join(filter(None, [
                insight["judgment"], insight["rationale"], rule])), "metadata": {}}],
        })
        knowledge_ids.append(knowledge["version"]["id"])
        if data.get("publish_to_retrieval", True):
            approve_knowledge(conn, knowledge["version"]["id"], {
                "approved_by": data["confirmed_by"],
                "authority_level": 2,
                "confidence": float(insight["confidence"]),
                "scope": None,
                "attributes": None,
            })
        conn.execute(
            """UPDATE xhs_learning_insights SET status=%s, user_correction=%s,
                      knowledge_version_id=%s, needs_confirmation=false WHERE id=%s""",
            (status, correction, knowledge["version"]["id"], insight["id"]),
        )
    conn.execute(
        "UPDATE xhs_learning_sessions SET status='confirmed', confirmed_at=now() WHERE id=%s",
        (session_id,),
    )
    return {"session_id": session_id, "status": "confirmed",
            "candidate_knowledge_version_ids": knowledge_ids,
            "published_to_retrieval": data.get("publish_to_retrieval", True),
            "next_step": "已进入后台向量化队列。" if data.get("publish_to_retrieval", True)
                         else "候选知识尚未进入生产检索。"}
