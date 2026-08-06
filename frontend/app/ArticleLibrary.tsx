"use client";

import { useEffect, useState } from "react";
import "./ArticleLibrary.css";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function request(url: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers || {});
  const token = localStorage.getItem("zhiwei-access-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers, credentials: "include" });
}

function TypeLabels({ item, detailed = false }: { item: any; detailed?: boolean }) {
  const primary = item?.content_primary_type;
  const secondary = item?.content_secondary_types || [];
  const confidence = item?.content_type_confidence;
  if (!primary) return <span className="content-type-pending">待分类</span>;
  return (
    <div className={`content-type-labels ${detailed ? "detailed" : ""}`}>
      <span className="content-type-primary">{primary}</span>
      {detailed && secondary.map((label: string) => <span className="content-type-secondary" key={label}>{label}</span>)}
      {detailed && confidence != null && <span className="content-type-confidence">置信度 {Math.round(Number(confidence))}%</span>}
    </div>
  );
}

export default function ArticleLibrary({ brandCode }: { brandCode: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [index, setIndex] = useState(0);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [forget, setForget] = useState<any>(null);
  const [deleting, setDeleting] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    setLoading(true);
    request(`${API}/v1/xhs/articles?brand_code=${brandCode}&limit=100`)
      .then((r) => r.json()).then((d) => setItems(d.items || [])).finally(() => setLoading(false));
  }
  useEffect(load, [brandCode]);

  function open(item: any) {
    setSelected(item); setDetail(null); setIndex(0);
    request(`${API}/v1/xhs/articles/${item.id}`).then((r) => r.json()).then(setDetail);
  }
  async function previewForget(item: any, event: any) {
    event.stopPropagation(); setBusy(true);
    const response = await request(`${API}/v1/xhs/articles/${item.id}/forget-preview`);
    setForget({ item, preview: await response.json() }); setBusy(false);
  }
  async function confirmForget() {
    setBusy(true);
    await request(`${API}/v1/xhs/articles/${forget.item.id}/forget-knowledge`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ forgotten_by: "当前用户", reason: "文章库主动遗忘" }),
    });
    setForget(null); setBusy(false); load();
  }
  async function previewDelete(item: any, event: any) {
    event.stopPropagation(); setBusy(true);
    const response = await request(`${API}/v1/xhs/articles/${item.id}/delete-preview`);
    const preview = await response.json();
    if (response.ok) setDeleting({ item, preview });
    setBusy(false);
  }
  async function confirmDelete() {
    setBusy(true);
    const response = await request(`${API}/v1/xhs/articles/${deleting.item.id}?reason=${encodeURIComponent("用户从文章库永久删除")}`, { method: "DELETE" });
    if (response.ok) { setDeleting(null); setSelected(null); load(); }
    setBusy(false);
  }
  async function queueImageUnderstanding(force = false) {
    if (!detail?.versions?.[0]?.id) return;
    setBusy(true);
    await request(`${API}/v1/xhs/article-versions/${detail.versions[0].id}/images/analyze?force=${force}`, { method: "POST" });
    const refreshed = await request(`${API}/v1/xhs/articles/${selected.id}`).then((r) => r.json());
    setDetail(refreshed); setBusy(false);
  }
  const visible = items.filter((x) => !query || `${x.title} ${x.creator_name}`.toLowerCase().includes(query.toLowerCase()));
  const number = (value: any) => value == null ? "—" : Number(value).toLocaleString("zh-CN");

  return <section className="page articles-page">
    <div className="filterbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标题、达人、产品…"/><button className="active">全部</button><span className="view-toggle">共 {visible.length} 篇</span></div>
    {loading ? <div className="article-state">正在读取文章…</div> : <div className="article-grid">{visible.map((item, i) =>
      <article className="article-card interactive" key={item.id} onClick={() => open(item)}>
        <div className={`cover c${i % 4 + 1} ${item.first_asset_id ? "has-image" : ""}`}>
          {item.first_asset_id && <img src={`${API}/v1/assets/${item.first_asset_id}/content`} alt="文章首图"/>}
          <TypeLabels item={item}/><strong>{item.title || "未命名文章"}</strong>
        </div>
        <div className="article-info"><h3>{item.title || "未命名文章"}</h3><p>{item.creator_name || "未记录作者"}</p>
          <div className="article-metrics"><span>♡ {number(item.like_count)}</span><span>☆ {number(item.collect_count)}</span><span>◯ {number(item.comment_count)}</span></div>
          {item.image_count > 0 && <div className="image-learning-state"><span>图片理解 {item.images_understood || 0}/{item.image_count}</span><span>多模态向量 {item.multimodal_vector_count || 0}</span></div>}
          <div className="article-card-actions">
            {item.absorption_status === "absorbed" && <button className="forget-knowledge-button" onClick={(e) => previewForget(item, e)}>忘记知识</button>}
            <button className="delete-article-button" onClick={(e) => previewDelete(item, e)}>删除文章</button>
          </div>
        </div>
      </article>)}</div>}

    {selected && <div className="note-overlay" onMouseDown={(e) => e.target === e.currentTarget && setSelected(null)}>
      <button className="note-close" onClick={() => setSelected(null)}>×</button><div className="note-dialog">
        {!detail ? <div className="note-loading">正在打开文章…</div> : <>
          <div className="note-gallery">{detail.images?.length ? <><img src={`${API}/v1/assets/${detail.images[index]?.asset_id}/content`} alt={`文章图片 ${index + 1}`}/>{detail.images.length > 1 && <div className="gallery-controls"><button onClick={() => setIndex((index - 1 + detail.images.length) % detail.images.length)}>‹</button><span>{index + 1}/{detail.images.length}</span><button onClick={() => setIndex((index + 1) % detail.images.length)}>›</button></div>}</> : <div>暂无图片</div>}</div>
          <div className="note-content"><header><div className="note-avatar">{(detail.article.creator_name || "运").slice(0, 1)}</div><strong>{detail.article.creator_name || "未记录作者"}</strong><button>关注</button></header>
            <div className="note-scroll"><TypeLabels item={selected} detailed/>
              {detail.images?.length > 0 && <div className="image-understanding-panel">
                <div><strong>图片理解</strong><span>{detail.images.filter((x:any) => x.analysis_status === "succeeded").length}/{detail.images.length} 张完成</span></div>
                {detail.images[index]?.analysis_status === "succeeded" ? <>
                  <p>{detail.images[index].analysis_summary}</p>
                  <div className="image-analysis-tags"><span>{detail.images[index].asset_role || "图片"}</span><span>{detail.images[index].visual_type || "视觉内容"}</span><span>品牌匹配 {Math.round(Number(detail.images[index].brand_fit_score || 0))}</span><span>种草力 {Math.round(Number(detail.images[index].selling_power_score || 0))}</span><span>向量 {detail.images[index].multimodal_vector_count}/2</span></div>
                  {detail.images[index].reusable_visual_rules?.length > 0 && <small>可复用经验：{detail.images[index].reusable_visual_rules[0]?.rule}</small>}
                </> : <p>{detail.images[index]?.analysis_error || "这张图片尚未完成AI理解与多模态向量化。"}</p>}
                <button disabled={busy} onClick={() => queueImageUnderstanding(false)}>{busy ? "正在加入队列…" : "学习全部图片"}</button>
              </div>}
              <h2>{detail.versions[0]?.title || "未命名文章"}</h2><p>{detail.versions[0]?.body}</p><div className="note-tags">{detail.versions[0]?.hashtags?.map((x: string) => <span key={x}>#{x}</span>)}</div><small>{detail.article.published_at ? new Date(detail.article.published_at).toLocaleString("zh-CN") : "发布时间未获取"}</small></div>
            <footer><span>♡ {number(detail.interactions[0]?.like_count)}</span><span>☆ {number(detail.interactions[0]?.collect_count)}</span><span>◯ {number(detail.interactions[0]?.comment_count)} 评论</span><a href={detail.article.source_url || "#"} target="_blank">打开原链接 ↗</a></footer>
          </div></>}
      </div>
    </div>}

    {forget && <div className="modal-backdrop"><div className="confirm-modal"><span className="modal-warning">!</span><h3>确认遗忘派生知识？</h3><p>将删除 {forget.preview.knowledge_version_count} 条知识版本、{forget.preview.chunk_count} 个分块和 {forget.preview.vector_count} 条向量；原文和图片保留。</p><div><button className="ghost" onClick={() => setForget(null)}>取消</button><button className="danger-button" disabled={busy} onClick={confirmForget}>{busy ? "处理中…" : "确认遗忘"}</button></div></div></div>}
    {deleting && <div className="modal-backdrop"><div className="confirm-modal article-delete-modal"><span className="modal-warning">!</span><h3>永久删除这篇文章？</h3><p className="delete-article-name">{deleting.preview.article_title}</p><p>删除后不可恢复，并会同步回退由它产生的知识和向量数据。</p><div className="delete-impact-grid"><span>文章版本 <strong>{deleting.preview.version_count}</strong></span><span>图片关联 <strong>{deleting.preview.image_link_count}</strong></span><span>知识版本 <strong>{deleting.preview.knowledge_version_count}</strong></span><span>文本分块 <strong>{deleting.preview.chunk_count}</strong></span><span>向量数据 <strong>{deleting.preview.vector_count}</strong></span><span>队列任务 <strong>{deleting.preview.job_count}</strong></span></div>{deleting.preview.affected_article_count > 1 && <p className="shared-warning">该学习记录还关联其他文章，共享知识会保留，不会误删。</p>}<div><button className="ghost" onClick={() => setDeleting(null)}>取消</button><button className="danger-button" disabled={busy} onClick={confirmDelete}>{busy ? "正在删除…" : "确认永久删除"}</button></div></div></div>}
  </section>;
}
