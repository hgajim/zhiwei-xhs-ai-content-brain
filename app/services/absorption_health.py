"""吸收质量健康评价第一阶段：材料质量、训练结构、覆盖度与知识纯净度。"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from psycopg import Connection

from app.services.knowledge import get_brand

FORMULA_VERSION = "absorption-health-v1"
MODE_CONFIG = {
    "positive_example": {"label": "好文章", "target": 0.20, "multiplier": 1.00},
    "negative_example": {"label": "不好的文章", "target": 0.20, "multiplier": 1.10},
    "revision_pair": {"label": "修改前后稿", "target": 0.40, "multiplier": 1.50},
    "experience": {"label": "口述经验", "target": 0.20, "multiplier": 1.25},
}


def _bounded(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _specific_feedback(text: str | None) -> float:
    value = (text or "").strip()
    if not value:
        return 0.0
    generic = {"很好", "不错", "不好", "太硬广", "没感觉", "符合调性", "不符合调性"}
    if value in generic:
        return 4.0
    return min(20.0, 7.0 + len(value) / 5.0)


def _session_quality(session: dict[str, Any], insights: list[dict[str, Any]]) -> float:
    """确定性评分，不让评分模型反过来污染训练数据。"""
    mode = session["learning_mode"]
    completeness = 0.0
    if mode == "experience":
        completeness = 20.0 if len((session.get("user_feedback") or "").strip()) >= 12 else 10.0
    else:
        original_ok = bool((session.get("original_title") or "").strip()) and len((session.get("original_body") or "").strip()) >= 30
        revised_ok = bool((session.get("revised_title") or "").strip()) and len((session.get("revised_body") or "").strip()) >= 30
        completeness = 20.0 if original_ok and (mode != "revision_pair" or revised_ok) else 10.0 if session.get("original_body") else 0.0
    feedback = _specific_feedback(session.get("user_feedback"))
    if not insights:
        return _bounded(completeness + feedback)
    evidence_ratio = sum(bool(x.get("evidence_before") or x.get("evidence_after")) for x in insights) / len(insights)
    scope_ratio = sum(bool(x.get("applicability")) for x in insights) / len(insights)
    executable_ratio = sum(len((x.get("reusable_rule") or "").strip()) >= 18 for x in insights) / len(insights)
    confidence = sum(float(x.get("confidence") or 0) for x in insights) / len(insights)
    score = completeness + feedback + evidence_ratio * 20 + scope_ratio * 15 + executable_ratio * 15 + confidence * 10
    if mode == "revision_pair":
        has_pair_evidence = any(x.get("evidence_before") and x.get("evidence_after") for x in insights)
        score += 10 if has_pair_evidence else 0
    return _bounded(score)


def _diminishing_factor(index: int) -> float:
    if index <= 5:
        return 1.0
    if index <= 10:
        return 0.7
    if index <= 20:
        return 0.4
    return 0.2


def calculate_absorption_health(conn: Connection, brand_code: str) -> dict[str, Any]:
    brand = get_brand(conn, brand_code)
    session_rows = [dict(row) for row in conn.execute(
        """SELECT ls.*, ov.title original_title,ov.body original_body,
                  rv.title revised_title,rv.body revised_body
           FROM xhs_learning_sessions ls
           LEFT JOIN xhs_article_versions ov ON ov.id=ls.original_article_version_id
           LEFT JOIN xhs_article_versions rv ON rv.id=ls.revised_article_version_id
           WHERE ls.brand_id=%s ORDER BY ls.created_at""", (brand["id"],)
    ).fetchall()]
    session_ids = [row["id"] for row in session_rows]
    insight_rows = []
    if session_ids:
        insight_rows = [dict(row) for row in conn.execute(
            """SELECT session_id,evidence_before,evidence_after,applicability,reusable_rule,confidence
               FROM xhs_learning_insights WHERE session_id=ANY(%s)""", (session_ids,)
        ).fetchall()]
    insights_by_session: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for insight in insight_rows:
        insights_by_session[insight["session_id"]].append(insight)

    confirmed = [row for row in session_rows if row["status"] == "confirmed"]
    quality_by_session = {row["id"]: _session_quality(row, insights_by_session[row["id"]]) for row in confirmed}
    material_score = sum(quality_by_session.values()) / len(quality_by_session) if quality_by_session else 0.0

    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in confirmed:
        by_mode[row["learning_mode"]].append(row)
    contributions: dict[str, float] = {}
    mode_metrics: dict[str, Any] = {}
    for mode, config in MODE_CONFIG.items():
        ordered = sorted(by_mode[mode], key=lambda row: quality_by_session[row["id"]], reverse=True)
        contribution = sum(quality_by_session[row["id"]] * config["multiplier"] * _diminishing_factor(i) for i, row in enumerate(ordered, 1))
        contributions[mode] = contribution
    total_contribution = sum(contributions.values())
    actual_shares = {mode: (value / total_contribution if total_contribution else 0.0) for mode, value in contributions.items()}
    balance_score = 100 * sum(min(actual_shares[mode], config["target"]) for mode, config in MODE_CONFIG.items())
    for mode, config in MODE_CONFIG.items():
        actual = actual_shares[mode]
        mode_metrics[mode] = {
            "label": config["label"], "count": len(by_mode[mode]),
            "average_quality": round(sum(quality_by_session[x["id"]] for x in by_mode[mode]) / len(by_mode[mode]), 1) if by_mode[mode] else 0,
            "effective_contribution": round(contributions[mode], 1),
            "actual_share": round(actual * 100, 1), "target_share": round(config["target"] * 100),
            "status": "不足" if actual < config["target"] * 0.7 else "偏多" if actual > config["target"] * 1.5 else "合理",
        }

    type_rows = conn.execute(
        """SELECT primary_type,count(*)::int n FROM xhs_content_type_labels label
           JOIN xhs_learning_sessions session ON session.id=label.session_id
           WHERE session.brand_id=%s AND session.status='confirmed'
           GROUP BY primary_type ORDER BY n DESC""", (brand["id"],)
    ).fetchall()
    type_distribution = {row["primary_type"]: row["n"] for row in type_rows}
    labeled_total = sum(type_distribution.values())
    unique_types = len(type_distribution)
    dominant_share = max(type_distribution.values()) / labeled_total if labeled_total else 0.0
    coverage_score = 60 * min(unique_types / 6, 1) + 40 * (1 - dominant_share) if labeled_total else 0.0

    knowledge_row = conn.execute(
        """SELECT count(*)::int total,
                  count(DISTINCT md5(lower(trim(content))))::int distinct_content,
                  count(*) FILTER (WHERE confidence<0.6)::int low_confidence
           FROM kb_item_versions version
           JOIN kb_items item ON item.id=version.item_id
           WHERE item.brand_id=%s AND version.status='active'""", (brand["id"],)
    ).fetchone()
    knowledge_total = int(knowledge_row["total"] or 0)
    duplicate_ratio = 1 - int(knowledge_row["distinct_content"] or 0) / knowledge_total if knowledge_total else 0.0
    low_confidence_ratio = int(knowledge_row["low_confidence"] or 0) / knowledge_total if knowledge_total else 0.0
    failed_count = sum(row["status"] == "failed" for row in session_rows)
    failure_rate = failed_count / len(session_rows) if session_rows else 0.0
    purity_score = 100 - failure_rate * 50 - duplicate_ratio * 30 - low_confidence_ratio * 20 if session_rows else 0.0

    material_score, balance_score, coverage_score, purity_score = map(_bounded, (material_score, balance_score, coverage_score, purity_score))
    overall = _bounded(material_score * 0.30 + balance_score * 0.35 + coverage_score * 0.20 + purity_score * 0.15)

    recommendations = []
    deficits = sorted(MODE_CONFIG, key=lambda mode: actual_shares[mode] - MODE_CONFIG[mode]["target"])
    action_copy = {
        "revision_pair": ("导入真实修改前后稿", "系统最需要学习从原稿到终稿的具体修改动作", "导入3—5组已由你审核完成的前后稿"),
        "experience": ("补充口述运营经验", "品牌潜规则和适用边界无法只靠文章可靠推断", "输入5条包含适用条件的明确判断"),
        "negative_example": ("补充典型坏文章", "反例不足会让系统只会模仿，不会建立问题边界", "导入3篇不同问题类型的坏稿"),
        "positive_example": ("补充不同类型好文章", "正例仍不足以覆盖你的核心内容任务", "优先补充当前缺失的内容运营类型"),
    }
    for priority, mode in enumerate(deficits[:2], 1):
        if actual_shares[mode] < MODE_CONFIG[mode]["target"] * 0.85:
            title, reason, action = action_copy[mode]
            recommendations.append({"priority": priority, "mode": mode, "title": title, "reason": reason, "action": action,
                                    "estimated_lift": "预计提升4—9分" if mode == "revision_pair" else "预计提升2—5分"})
    if dominant_share > 0.55:
        recommendations.append({"priority": len(recommendations) + 1, "mode": "coverage", "title": "降低单一内容类型占比",
                                "reason": f"当前最高频类型占{round(dominant_share*100)}%，容易让审核标准偏科",
                                "action": "下一批优先导入不同运营目标的内容", "estimated_lift": "预计提升2—6分"})
    if failure_rate > 0.05:
        recommendations.append({"priority": len(recommendations) + 1, "mode": "quality", "title": "处理分析失败记录",
                                "reason": f"当前分析失败率为{round(failure_rate*100)}%", "action": "检查失败原因后重试，不要让失败材料计入训练",
                                "estimated_lift": "减少知识缺口"})
    recommendations = recommendations[:3]

    quality_metrics = {
        "total_sessions": len(session_rows), "confirmed_sessions": len(confirmed), "failed_sessions": failed_count,
        "pending_sessions": len(session_rows) - len(confirmed) - failed_count,
        "active_knowledge": knowledge_total, "failure_rate": round(failure_rate * 100, 1),
        "duplicate_knowledge_rate": round(duplicate_ratio * 100, 1), "low_confidence_rate": round(low_confidence_ratio * 100, 1),
        "content_type_count": unique_types, "dominant_type_share": round(dominant_share * 100, 1),
    }
    status = "健康" if overall >= 80 else "基本健康" if overall >= 65 else "需要补强" if overall >= 45 else "训练结构失衡"
    result = {
        "formula_version": FORMULA_VERSION, "phase": 1, "score": overall, "status": status,
        "dimensions": {"material_quality": material_score, "signal_balance": balance_score,
                       "content_coverage": coverage_score, "knowledge_purity": purity_score},
        "weights": {"material_quality": 30, "signal_balance": 35, "content_coverage": 20, "knowledge_purity": 15},
        "mode_metrics": mode_metrics, "content_type_distribution": type_distribution,
        "quality_metrics": quality_metrics, "recommendations": recommendations,
        "note": "第一阶段为数据健康度；检索有效性和实战效果将在后续阶段加入。",
    }
    conn.execute(
        """INSERT INTO xhs_absorption_health_snapshots(
             brand_id,formula_version,overall_score,material_quality_score,signal_balance_score,
             coverage_score,purity_score,mode_metrics,content_type_distribution,quality_metrics,recommendations)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
           ON CONFLICT(brand_id,formula_version,captured_bucket) DO UPDATE SET
             overall_score=excluded.overall_score,material_quality_score=excluded.material_quality_score,
             signal_balance_score=excluded.signal_balance_score,coverage_score=excluded.coverage_score,
             purity_score=excluded.purity_score,mode_metrics=excluded.mode_metrics,
             content_type_distribution=excluded.content_type_distribution,quality_metrics=excluded.quality_metrics,
             recommendations=excluded.recommendations,created_at=now()""",
        (brand["id"], FORMULA_VERSION, overall, material_score, balance_score, coverage_score, purity_score,
         json.dumps(mode_metrics, ensure_ascii=False), json.dumps(type_distribution, ensure_ascii=False),
         json.dumps(quality_metrics, ensure_ascii=False), json.dumps(recommendations, ensure_ascii=False)),
    )
    return result
