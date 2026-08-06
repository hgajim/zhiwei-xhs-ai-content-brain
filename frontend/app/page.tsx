"use client";

import { useEffect, useMemo, useState } from "react";
import "./detail.css";
import "./motion.css";
import ArticleLibrary from "./ArticleLibrary";
import WorkspaceSwitcher from "./WorkspaceSwitcher";

type View = "dashboard" | "teach" | "articles" | "knowledge" | "review";
type Mode = "positive_example" | "negative_example" | "revision_pair" | "experience";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
function apiFetch(input:RequestInfo|URL,init:RequestInit={}){
  const token=typeof window!=="undefined"?window.localStorage.getItem("zhiwei-access-token"):null;
  const headers=new Headers(init.headers||{});if(token)headers.set("Authorization",`Bearer ${token}`);
  return fetch(input,{...init,headers,credentials:"include"});
}

function ArticleLibraryLegacy({brandCode}:{brandCode:string}){
  const [items,setItems]=useState<any[]>([]),[selected,setSelected]=useState<any>(null),[detail,setDetail]=useState<any>(null),[loading,setLoading]=useState(true),[query,setQuery]=useState("");
  useEffect(()=>{setLoading(true);apiFetch(`${API}/v1/xhs/articles?brand_code=${brandCode}&limit=100`).then(r=>r.json()).then(d=>setItems(d.items||[])).finally(()=>setLoading(false))},[brandCode]);
  function open(item:any){setSelected(item);setDetail(null);apiFetch(`${API}/v1/xhs/articles/${item.id}`).then(r=>r.json()).then(setDetail)}
  const visible=items.filter(x=>!query||`${x.title} ${x.creator_name}`.toLowerCase().includes(query.toLowerCase()));const n=(v:any)=>v==null?"—":Number(v).toLocaleString("zh-CN");
  return <section className="page articles-page"><div className="filterbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索标题、达人、产品…"/><button className="active">全部</button><span className="view-toggle">共 {visible.length} 篇</span></div>{loading?<div className="article-state">正在读取文章…</div>:<div className="article-grid">{visible.map((item,i)=><article className="article-card interactive" key={item.id} onClick={()=>open(item)}><div className={`cover c${i%4+1} ${item.first_asset_id?"has-image":""}`}>{item.first_asset_id&&<img src={`${API}/v1/assets/${item.first_asset_id}/content`} alt="文章首图"/>}<strong>{item.title||"未命名文章"}</strong></div><div className="article-info"><h3>{item.title||"未命名文章"}</h3><p>{item.creator_name||"未记录作者"}</p><div className="article-metrics"><span>♡ {n(item.like_count)}</span><span>☆ {n(item.collect_count)}</span><span>◯ {n(item.comment_count)}</span></div></div></article>)}</div>}{selected&&<div className="note-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setSelected(null)}}><button className="note-close" onClick={()=>setSelected(null)}>×</button><div className="note-dialog">{!detail?<div className="note-loading">正在打开文章…</div>:<><div className="note-gallery">{detail.images?.[0]?.asset_id?<img src={`${API}/v1/assets/${detail.images[0].asset_id}/content`} alt="文章图片"/>:<div>暂无图片</div>}</div><div className="note-content"><header><div className="note-avatar">{(detail.article.creator_name||"运").slice(0,1)}</div><strong>{detail.article.creator_name||"未记录作者"}</strong><button>关注</button></header><div className="note-scroll"><h2>{detail.versions[0]?.title||"未命名文章"}</h2><p>{detail.versions[0]?.body}</p><div className="note-tags">{detail.versions[0]?.hashtags?.map((x:string)=><span key={x}>#{x}</span>)}</div><small>{detail.article.published_at?new Date(detail.article.published_at).toLocaleString("zh-CN"):"发布时间未获取"}</small></div><footer><span>♡ {n(detail.interactions[0]?.like_count)}</span><span>☆ {n(detail.interactions[0]?.collect_count)}</span><span>◯ {n(detail.interactions[0]?.comment_count)} 评论</span><a href={detail.article.source_url||"#"} target="_blank">打开原链接 ↗</a></footer></div></>}</div></div>}</section>
}

function ReviewWorkspace({brandCode}:{brandCode:string}){
  const [title,setTitle]=useState(""),[body,setBody]=useState(""),[busy,setBusy]=useState(false),[result,setResult]=useState<any>(null),[message,setMessage]=useState(""),[compare,setCompare]=useState(false);
  async function review(){if(!body.trim()){setMessage("请先粘贴需要审核的文章");return}setBusy(true);setMessage("");setResult(null);try{const r=await apiFetch(`${API}/v1/xhs/ai-reviews`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({brand_code:brandCode,title,body,created_by:"当前用户",compare})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"审核失败");setResult(d)}catch(e){setMessage(e instanceof Error?e.message:"审核失败")}finally{setBusy(false)}}
  const absorbTarget=result?.comparison?result.with_knowledge:result;
  async function absorb(){if(!absorbTarget)return;setBusy(true);try{const r=await apiFetch(`${API}/v1/xhs/ai-reviews/${absorbTarget.id}/absorb`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmed_by:"当前用户"})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"吸收失败");setMessage("已吸收调用个人知识库的审核经验，并加入学习与向量队列") }catch(e){setMessage(e instanceof Error?e.message:"吸收失败")}finally{setBusy(false)}}
  return <section className="page review-workspace"><div className="toolbar"><div><span className="eyebrow">引用你的个人知识与公共合规知识</span><h2>AI 审核</h2><p>90分及以上视为通过；对比模式只改变是否调用个人向量知识库。</p></div><button className="primary" disabled={busy} onClick={review}>{busy?(compare?"正在生成两组结果…":"正在审核…"):"开始审核"}</button></div><div className="review-compare-option"><div><strong>对比知识库效果</strong><p>同时生成“调用个人知识库”和“跳过个人知识库”两套审核与改稿。</p></div><button type="button" className={`auto-absorb-switch ${compare?"on":""}`} aria-label="对比知识库效果" aria-pressed={compare} onClick={()=>setCompare(!compare)} disabled={busy}><i/></button></div><div className="review-input"><input value={title} onChange={e=>setTitle(e.target.value)} placeholder="文章标题（选填）"/><textarea value={body} onChange={e=>setBody(e.target.value)} placeholder="粘贴达人原稿…"/></div>{message&&<div className="notice">{message}</div>}{busy&&<LearningProgress/>}{result&&<>{result.comparison?<><div className="comparison-summary"><strong>个人知识库带来的差异</strong><span>评分差 {result.score_delta>0?"+":""}{result.score_delta} 分</span><span>引用个人知识 {result.knowledge_citation_count} 条</span></div><div className="review-comparison-grid"><ReviewResultPanel result={result.with_knowledge} title="调用个人知识库" highlighted/><ReviewResultPanel result={result.without_knowledge} title="跳过个人知识库"/></div></>:<><div className="review-layout"><div className="draft"><span>原稿</span><h3>{title||"未命名文章"}</h3><p>{body}</p></div><ReviewResultPanel result={result} title="审核结论"/></div><div className="revised"><span>AI建议修改稿</span><p>{result.revised_text||"未生成修改稿"}</p><button onClick={()=>navigator.clipboard.writeText(result.revised_text||"")}>复制修改稿</button></div></>}<div className="review-actions"><button className="ghost" onClick={()=>{setResult(null);setMessage("")}}>重新审核</button><button className="primary" disabled={busy} onClick={absorb}>{result.comparison?"吸收个人知识库版本":"吸收本次审核经验"}</button></div></>}</section>
}

function ReviewResultPanel({result,title,highlighted=false}:{result:any;title:string;highlighted?:boolean}){
  const label:any={pass:"通过",minor_revision:"轻微修改",major_revision:"重大修改",reject:"不建议发布"};
  return <div className={`review-variant ${highlighted?"knowledge-variant":""}`}><div className="review-variant-head"><div><span>{highlighted?"个人运营大脑":"模型通用能力"}</span><h3>{title}</h3></div><span className={`review-decision ${result.decision}`}>{label[result.decision]}</span></div><div className="review-score"><strong>{result.score}</strong><span>审核评分<br/><small>{result.score>=90?"达到发布标准":"需要修改后发布"}</small></span></div><h3 className="variant-summary">{result.summary}</h3><div className="variant-issues">{(result.issues||[]).map((x:any,i:number)=><div className="issue" key={i}><b>{String(i+1).padStart(2,"0")}</b><div><strong>{x.problem}</strong><p>原文：{x.quote||"整体判断"}</p><p>建议：{x.suggestion}</p><small>{x.knowledge_version_id?"已引用个人知识":"未引用个人知识"}</small></div></div>)}</div><div className="variant-revised"><span>完整修改稿</span><p>{result.revised_text||"未生成修改稿"}</p><button className="ghost" onClick={()=>navigator.clipboard.writeText(result.revised_text||"")}>复制</button></div></div>
}

const navigation: { id: View; label: string; mark: string }[] = [
  { id: "dashboard", label: "工作台", mark: "⌂" },
  { id: "teach", label: "吸收导入", mark: "✦" },
  { id: "articles", label: "文章库", mark: "▤" },
  { id: "review", label: "AI 审核", mark: "✓" },
];

const modeCards: { id: Mode; title: string; hint: string; mark: string }[] = [
  { id: "positive_example", title: "好文章", hint: "让 AI 学会哪里值得复用", mark: "↗" },
  { id: "negative_example", title: "不好的文章", hint: "识别问题和避免方式", mark: "↘" },
  { id: "revision_pair", title: "修改前后稿", hint: "自动对比并推断修改原因", mark: "⇄" },
  { id: "experience", title: "口述经验", hint: "直接说出你的运营判断", mark: "◌" },
];

export default function Home() {
  const [view, setView] = useState<View>("dashboard");
  const [mode, setMode] = useState<Mode>("revision_pair");
  const [beforeTitle, setBeforeTitle] = useState("");
  const [before, setBefore] = useState("");
  const [afterTitle, setAfterTitle] = useState("");
  const [after, setAfter] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [notice, setNotice] = useState("");
  const [articleUrl, setArticleUrl] = useState("");
  const [parsedArticle, setParsedArticle] = useState<any>(null);
  const [parsingUrl, setParsingUrl] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoAbsorb, setAutoAbsorb] = useState(false);
  const [account,setAccount]=useState<any>(null);
  const [authReady,setAuthReady]=useState(false);
  const [activeWorkspaceId,setActiveWorkspaceId]=useState("");

  useEffect(() => {
    setAutoAbsorb(window.localStorage.getItem("brand-kb-auto-absorb") === "true");
    const token=window.localStorage.getItem("zhiwei-access-token");
    if(!token){setAuthReady(true);return}
    apiFetch(`${API}/v1/auth/me`).then(async r=>{if(!r.ok)throw new Error();return r.json()}).then(setAccount).catch(()=>window.localStorage.removeItem("zhiwei-access-token")).finally(()=>setAuthReady(true));
  }, []);

  function changeAutoAbsorb(enabled: boolean) {
    setAutoAbsorb(enabled);
    window.localStorage.setItem("brand-kb-auto-absorb", String(enabled));
  }

  function resetImportForm() {
    setBeforeTitle(""); setBefore(""); setAfterTitle(""); setAfter(""); setFeedback(""); setArticleUrl("");
    setParsedArticle(null); setResult(null);
  }

  async function confirmSession(sessionId: string) {
    const response = await apiFetch(`${API}/v1/xhs/learning-sessions/${sessionId}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed_by: "本地运营用户", publish_to_retrieval: true,
        rejected_insight_ids: [], corrections: [] }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "确认失败");
    return data;
  }

  const title = useMemo(() => view === "knowledge" ? "知识管理" : navigation.find((item) => item.id === view)?.label, [view]);
  const activeWorkspace=account?.workspaces?.find((x:any)=>String(x.id)===activeWorkspaceId)||account?.workspaces?.[0];
  const brandCode=activeWorkspace?.brand_code||"demo_brand";

  async function startLearning() {
    if (mode !== "experience" && !before.trim()) {
      setNotice("请先粘贴或上传一篇文章"); return;
    }
    if (mode === "revision_pair" && !after.trim()) {
      setNotice("请补充修改后的文章"); return;
    }
    if (mode === "experience" && !feedback.trim()) {
      setNotice("请说出你想教给 AI 的经验"); return;
    }
    setBusy(true); setNotice(""); setResult(null);
    const externalId = `web-${Date.now()}`;
    const article = (articleTitle: string, text: string, versionType: string) => ({
      article_type: "creator_submission", version_type: versionType,
      external_id: parsedArticle?.platform_note_id || externalId,
      platform_note_id: parsedArticle?.platform_note_id || null,
      source_url: parsedArticle?.canonical_url || null,
      creator_name: parsedArticle?.creator_name || null,
      title: articleTitle, body: text,
      hashtags: parsedArticle?.hashtags || [],
      metadata: parsedArticle ? { image_urls: parsedArticle.image_urls,
        image_count: parsedArticle.image_count, like_count: parsedArticle.like_count, collect_count:parsedArticle.collect_count,
        comment_count:parsedArticle.comment_count,share_count:parsedArticle.share_count,
        imported_from_url: true } : {},
    });
    try {
      const learningPayload = {
        brand_code: brandCode, learning_mode: mode,
        user_feedback: feedback || null, created_by: "本地运营用户",
        original_article: mode === "experience" ? null : article(beforeTitle, before, "creator_original"),
        revised_article: mode === "revision_pair" ? article(afterTitle, after, "approved_final") : null,
      };
      // 自动吸收模式只等待“任务已登记”，不等待AI分析，随后立即释放表单。
      const response = await apiFetch(`${API}/v1/xhs/learning-sessions${autoAbsorb?"/background":""}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(learningPayload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "分析失败");
      if (autoAbsorb && data.accepted) {
        resetImportForm();
        setNotice(data.deduplicated
          ? "相同任务已经在后台处理中或已经完成，本次没有重复创建；可以继续导入。"
          : "已加入后台学习队列，可以立即导入下一篇；分析、吸收和向量化将在后台继续。"
        );
      } else if (data.deduplicated && data.session?.status === "confirmed") {
        resetImportForm();
        setNotice("检测到相同内容：此前已经吸收并写入向量库，本次未重复分析或创建任务。");
      } else {
        setResult(data);
        if (data.deduplicated) setNotice("检测到相同输入，已复用此前分析结果，没有再次调用 AI。");
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "暂时无法连接后端服务");
    } finally { setBusy(false); }
  }

  async function confirmLearning() {
    if (!result?.session?.id) return;
    setBusy(true); setNotice("");
    try {
      const data = await confirmSession(result.session.id);
      setNotice(`已吸收 ${data.candidate_knowledge_version_ids?.length || 0} 条经验，并进入向量化队列`);
      // 吸收成功后关闭候选分析区，只保留明确的成功反馈。
      setResult(null);
    } catch (error) { setNotice(error instanceof Error ? error.message : "确认失败"); }
    finally { setBusy(false); }
  }

  async function parseArticleUrl() {
    if (!articleUrl.trim()) { setNotice("请粘贴小红书文章链接"); return; }
    setParsingUrl(true); setNotice(""); setParsedArticle(null);
    try {
      const response = await apiFetch(`${API}/v1/xhs/parse-url`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: articleUrl.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "链接解析失败");
      setParsedArticle(data);
      setBeforeTitle(data.title || "");
      setBefore(data.body || "");
      setNotice(`解析成功：正文、作者和 ${data.image_count} 张图片已读取`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "链接解析失败"); }
    finally { setParsingUrl(false); }
  }

  if(!authReady)return <div className="auth-loading">正在打开你的运营大脑…</div>;
  if(!account)return <AuthScreen onAuthenticated={(data:any)=>{window.localStorage.setItem("zhiwei-access-token",data.access_token);apiFetch(`${API}/v1/auth/me`).then(r=>r.json()).then(setAccount)}}/>;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-seal">⌁</span><div><strong>知微</strong><small>内容运营大脑</small></div></div>
        <nav>{navigation.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}><span className={`nav-icon nav-icon-${item.id}`} aria-hidden="true"/>{item.label}{item.id === "teach" && <i>主流程</i>}</button>)}</nav>
        <button className="sidebar-create" onClick={() => setView("teach")}><span>＋</span> 新建导入</button>
        <WorkspaceSwitcher account={account} activeId={activeWorkspace?.id||""} onSelect={setActiveWorkspaceId} onAccount={setAccount}/>
        <QueueCenter api={API} brandCode={brandCode}/>
        {account.user?.is_admin&&<button className="sidebar-settings" onClick={() => setSettingsOpen(true)} aria-label="模型设置"><span>⚙</span><b>设置</b></button>}
        <div className="sidebar-foot"><div className="status-dot"/><div><strong>知识大脑运行中</strong><small>模型连接正常</small></div></div>
      </aside>

      <main className="main">
        <header><div className="page-heading"><span className="eyebrow">品牌小红书运营中心</span><h1>{title}</h1></div><div className="header-actions">{view === "articles" && <button className="primary" onClick={() => setView("teach")}>＋ 导入文章</button>}<button className="icon-button" aria-label="通知">♢</button><button className="avatar">运</button></div></header>
        {view === "dashboard" && <Dashboard brandCode={brandCode} onTeach={() => setView("teach")} />}
        {view === "teach" && <Teach brandCode={brandCode} mode={mode} setMode={setMode} beforeTitle={beforeTitle} setBeforeTitle={setBeforeTitle} before={before} setBefore={setBefore} afterTitle={afterTitle} setAfterTitle={setAfterTitle} after={after} setAfter={setAfter} feedback={feedback} setFeedback={setFeedback} busy={busy} result={result} notice={notice} startLearning={startLearning} confirmLearning={confirmLearning} articleUrl={articleUrl} setArticleUrl={setArticleUrl} parsedArticle={parsedArticle} parsingUrl={parsingUrl} parseArticleUrl={parseArticleUrl} autoAbsorb={autoAbsorb} changeAutoAbsorb={changeAutoAbsorb} />}
        {view === "articles" && <ArticleLibrary brandCode={brandCode} />}
        {view === "knowledge" && <Knowledge />}
        {view === "review" && <ReviewWorkspace brandCode={brandCode} />}
      </main>
      {settingsOpen&&<div className="settings-overlay"><div className="settings-dialog"><button className="settings-close" onClick={()=>setSettingsOpen(false)} aria-label="关闭设置">×</button><Settings api={API} brandCode={brandCode} setNotice={setNotice} notice={notice}/></div></div>}
    </div>
  );
}

function AuthScreen({onAuthenticated}:{onAuthenticated:(data:any)=>void}){
  const [registering,setRegistering]=useState(false);const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [name,setName]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function submit(event:any){event.preventDefault();setBusy(true);setError("");try{const response=await fetch(`${API}/v1/auth/${registering?"register":"login"}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password,display_name:name})});const data=await response.json();if(!response.ok)throw new Error(data.detail||"操作失败");onAuthenticated(data)}catch(reason){setError(reason instanceof Error?reason.message:"操作失败")}finally{setBusy(false)}}
  return <main className="auth-page"><section className="auth-brand"><span>知微</span><h1>把你的判断，<br/>训练成自己的运营大脑。</h1><p>文章、审核经验和表达偏好只属于你的个人空间。</p><div><i/>个人知识隔离　<i/>持续学习　<i/>可追溯审核</div></section><form className="auth-card" onSubmit={submit}><span className="eyebrow">个人小红书运营大脑</span><h2>{registering?"创建你的账号":"欢迎回来"}</h2><p>{registering?"注册后会自动创建第一个运营大脑。":"登录后继续训练你的内容风格。"}</p>{registering&&<label>称呼<input value={name} onChange={e=>setName(e.target.value)} placeholder="你的名字"/></label>}<label>邮箱<input type="email" required value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@example.com"/></label><label>密码<input type="password" required minLength={registering?10:1} value={password} onChange={e=>setPassword(e.target.value)} placeholder={registering?"至少10个字符":"输入密码"}/></label>{error&&<div className="auth-error">{error}</div>}<button className="primary" disabled={busy}>{busy?"请稍候…":registering?"注册并创建运营大脑":"登录"}</button><button type="button" className="auth-switch" onClick={()=>{setRegistering(!registering);setError("")}}>{registering?"已有账号？返回登录":"没有账号？创建一个"}</button><small>当前为本地验证环境，邮箱验证将在正式部署时启用。</small></form></main>
}

function Dashboard({ brandCode,onTeach }: { brandCode:string;onTeach: () => void }) {
  const [health,setHealth]=useState<any>(null),[healthError,setHealthError]=useState(""),[loading,setLoading]=useState(true);
  useEffect(()=>{let active=true;setLoading(true);apiFetch(`${API}/v1/brands/${brandCode}/absorption-health`).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail||"健康度读取失败");return data}).then(data=>{if(active){setHealth(data);setHealthError("")}}).catch(reason=>{if(active)setHealthError(reason instanceof Error?reason.message:"健康度读取失败")}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[brandCode]);
  const quality=health?.quality_metrics||{};
  const modes=['positive_example','negative_example','revision_pair','experience'];
  return <section className="page dashboard">
    <div className="hero-panel"><div><span className="pill">今天的内容工作</span><h2>把你的判断，<br/>变成团队的大脑。</h2><p>上传文章或修改前后稿，只说一句整体评价。AI 会自动拆解并学习你的运营经验。</p><button className="primary" onClick={onTeach}>开始教 AI <span>→</span></button></div><div className="hero-orbit"><div className="orbit-center">AI<small>正在学习</small></div><span className="orbit-tag t1">品牌调性</span><span className="orbit-tag t2">标题结构</span><span className="orbit-tag t3">审核经验</span><span className="orbit-tag t4">达人语感</span></div></div>
    {healthError&&<div className="health-error">吸收健康度暂时不可用：{healthError}</div>}
    <div className="metric-grid"><Metric n={loading?"…":String(quality.confirmed_sessions??0)} label="已确认训练" delta={`累计 ${quality.total_sessions??0} 次摄入`}/><Metric n={loading?"…":String(quality.active_knowledge??0)} label="有效知识" delta={`重复率 ${quality.duplicate_knowledge_rate??0}%`}/><Metric n={loading?"…":String(quality.pending_sessions??0)} label="待处理训练" delta={`${quality.failed_sessions??0} 个失败任务`} emphasis/><Metric n={loading?"…":health?String(Math.round(health.score)):"—"} label="吸收健康度" delta={health?.status||"正在读取"}/></div>
    <div className="two-col"><div className="panel"><div className="panel-head"><div><span className="eyebrow">下一步怎么训练</span><h3>动态训练建议</h3></div></div>{health?.recommendations?.length?<div className="health-recommendations">{health.recommendations.map((item:any)=><div className="health-recommendation" key={`${item.priority}-${item.mode}`}><b>{item.priority}</b><div><strong>{item.title}</strong><p>{item.reason}</p><small>{item.action} · {item.estimated_lift}</small></div></div>)}</div>:<div className="dashboard-empty"><strong>{loading?"正在诊断训练结构…":"当前没有紧急补强项"}</strong><p>继续保持四类素材的真实、具体和多样性。</p></div>}</div><div className="panel"><div className="panel-head"><div><span className="eyebrow">四种训练信号</span><h3>素材结构</h3></div></div><div className="training-mix">{modes.map(mode=>{const item=health?.mode_metrics?.[mode];return <div className="mix-row" key={mode}><div><strong>{item?.label||"读取中"}</strong><span>{item?.count??0} 次 · 目标 {item?.target_share??0}%</span></div><div className="mix-track"><i style={{width:`${Math.min(Number(item?.actual_share||0),100)}%`}}/></div><b>{item?.actual_share??0}%</b></div>})}</div></div></div>
  </section>
}

function Metric({n,label,delta,emphasis}:{n:string,label:string,delta:string,emphasis?:boolean}) { return <div className={`metric ${emphasis?"emphasis":""}`}><span>{label}</span><strong>{n}</strong><small>{delta}</small></div> }

function Teach(props:any) {
  const {brandCode,mode,setMode,beforeTitle,setBeforeTitle,before,setBefore,afterTitle,setAfterTitle,after,setAfter,feedback,setFeedback,busy,result,notice,startLearning,confirmLearning,articleUrl,setArticleUrl,parsedArticle,parsingUrl,parseArticleUrl,autoAbsorb,changeAutoAbsorb}=props;
  return <section className="page teach"><div className="intro"><div><span className="eyebrow">一次输入，自动拆解</span><h2>今天想教 AI 什么？</h2><p>标题和正文会分别保存；你不需要逐项解释好在哪里，再补充一句整体判断即可。</p></div><span className="step-indicator">01 <i/> 02 <i/> 03</span></div>
    <AbsorptionHealthPanel brandCode={brandCode}/>
    <div className="url-import"><span className="url-icon">↗</span><div><label>通过小红书链接导入</label><p>自动读取标题、正文、作者、话题和全部图片</p></div><input value={articleUrl} onChange={(e:any)=>setArticleUrl(e.target.value)} placeholder="粘贴 https://www.xiaohongshu.com/explore/..."/><button onClick={parseArticleUrl} disabled={parsingUrl}>{parsingUrl?"正在解析…":"解析链接"}</button></div>
    {parsedArticle&&<div className="parsed-strip"><strong>已读取：{parsedArticle.title}</strong><span>{parsedArticle.creator_name||"未知作者"} · {parsedArticle.image_count} 张图片（开始学习后自动保存） · {parsedArticle.hashtags?.length||0} 个话题</span></div>}
    <div className="mode-grid">{modeCards.map(card=><button key={card.id} className={mode===card.id?"selected":""} onClick={()=>setMode(card.id)}><span>{card.mark}</span><strong>{card.title}</strong><small>{card.hint}</small></button>)}</div>
    <div className="teaching-canvas">
      {mode==="experience" ? <div className="single-input"><label>把你的经验直接告诉 AI</label><textarea value={feedback} onChange={e=>setFeedback(e.target.value)} placeholder="例如：生活方式达人不要突然大段科普成分，会破坏她原本的人设和叙事节奏。"/></div> : <>
        <div className={mode==="revision_pair"?"editor-grid":"editor-grid single"}><Editor label={mode==="revision_pair"?"修改前":"文章素材"} titleValue={beforeTitle} onTitleChange={setBeforeTitle} value={before} onChange={setBefore} titlePlaceholder={mode==="revision_pair"?"输入原稿标题":"输入文章标题"} placeholder="把文章正文粘贴到这里，或拖入 Word、截图、图片…" badge="原稿"/>{mode==="revision_pair"&&<Editor label="修改后" titleValue={afterTitle} onTitleChange={setAfterTitle} value={after} onChange={setAfter} titlePlaceholder="输入修改后的标题" placeholder="粘贴审核后的最终正文…" badge="终稿"/>}</div>
        <div className="feedback-row"><span>✦</span><div><label>补充一句你的判断 <em>选填</em></label><input value={feedback} onChange={e=>setFeedback(e.target.value)} placeholder={mode==="positive_example"?"例如：植入自然，开头很抓人":"例如：原稿功效说得太满，修改后更可信"}/></div></div>
      </>}
      <div className="auto-absorb-option">
        <span className="auto-absorb-icon">↯</span>
        <div><strong>自动确认并加入队列</strong><p>开启后任务入队即清空表单，AI会在后台继续分析、吸收和向量化。</p></div>
        <button type="button" className={`auto-absorb-switch ${autoAbsorb?"on":""}`} aria-label="自动确认并加入队列" aria-pressed={autoAbsorb} onClick={()=>changeAutoAbsorb(!autoAbsorb)}><i/></button>
      </div>
      {notice&&<div className="notice">{notice}</div>}
      <div className="canvas-actions"><span>AI 会自动分析结构、调性、卖点、风险与适用边界</span><button className="primary" disabled={busy} onClick={startLearning}>{busy&&!result?(autoAbsorb?"正在加入队列…":"正在理解与提炼…"):"开始学习"} <b>→</b></button></div>
    </div>
    {busy&&!result&&!autoAbsorb&&<LearningProgress/>}
    {result&&<AnalysisResult result={result} busy={busy} onConfirm={confirmLearning}/>} 
  </section>
}

function healthLevel(score:number){
  if(score<40)return {key:"red",label:"薄弱"};
  if(score<60)return {key:"orange",label:"需要补强"};
  if(score<80)return {key:"yellow",label:"基本健康"};
  return {key:"green",label:"健康"};
}

function AbsorptionHealthPanel({brandCode}:{brandCode:string}){
  const [health,setHealth]=useState<any>(null),[error,setError]=useState(""),[loading,setLoading]=useState(true);
  useEffect(()=>{let active=true;const load=()=>apiFetch(`${API}/v1/brands/${brandCode}/absorption-health`).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail||"健康度读取失败");return data}).then(data=>{if(active){setHealth(data);setError("")}}).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"健康度读取失败")}).finally(()=>{if(active)setLoading(false)});setLoading(true);load();const timer=setInterval(load,10000);return()=>{active=false;clearInterval(timer)}},[brandCode]);
  if(loading)return <section className="absorption-health-card loading"><strong>正在判断你下一步最该教 AI 什么…</strong></section>;
  if(error)return <section className="absorption-health-card error"><strong>暂时无法读取吸收健康度</strong><span>{error}</span></section>;
  const overall=Number(health?.score||0),level=healthLevel(overall);
  const first=health?.recommendations?.[0];
  const dimensions=[['素材质量',health?.dimensions?.material_quality,'材料完整、有证据、可执行'],['训练结构',health?.dimensions?.signal_balance,'四类训练信号是否平衡'],['内容覆盖',health?.dimensions?.content_coverage,'内容类型是否足够多样'],['知识纯净',health?.dimensions?.knowledge_purity,'失败、重复与低置信是否受控']];
  return <section className={`absorption-health-card level-${level.key}`}>
    <div className="health-card-heading"><div><span>吸收质量健康评价</span><strong>你的运营大脑现在是 {Math.round(overall)} 分</strong></div><i>{level.label}</i></div>
    <div className="health-next-action"><span>现在应该做</span><strong>{first?.action||"继续导入不同类型的真实运营案例"}</strong><p>{first?.reason||"保持四类训练材料真实、具体且多样。"}</p></div>
    <div className="health-score-line"><strong>{Math.round(overall)}</strong><div><i style={{width:`${overall}%`}}/></div><span>100</span></div>
    <div className="health-dimension-grid">{dimensions.map(([name,score,description])=>{const value=Number(score||0),itemLevel=healthLevel(value);return <div className={`health-dimension level-${itemLevel.key}`} key={String(name)}><span>{name}</span><strong>{Math.round(value)}</strong><i>{itemLevel.label}</i><p>{description}</p></div>})}</div>
  </section>
}

function Editor({label,titleValue,onTitleChange,value,onChange,titlePlaceholder,placeholder,badge}:{label:string;titleValue:string;onTitleChange:(v:string)=>void;value:string;onChange:(v:string)=>void;titlePlaceholder:string;placeholder:string;badge:string}) { return <div className="editor"><div className="editor-top"><label>{label}</label><span>{badge}</span></div><label className="editor-field-label">文章标题</label><input className="editor-title-input" value={titleValue} onChange={e=>onTitleChange(e.target.value)} placeholder={titlePlaceholder}/><label className="editor-field-label body-label">文章正文</label><textarea value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/><div className="drop-hint"><b>＋</b> 支持粘贴文字 · Word · Excel · 截图 · 图片</div></div> }

function LearningProgress(){
  return <div className="learning-progress" role="status" aria-live="polite"><div className="learning-orb"><i/><i/><i/><span>AI</span></div><div><strong>正在理解这篇内容</strong><p>系统会自动完成拆解，你不需要逐项填写说明。</p><div className="learning-steps"><span>读取文章与图片</span><span>分析结构和风险</span><span>生成候选经验</span></div></div></div>
}

function AnalysisResult({result,busy,onConfirm}:{result:any,busy:boolean,onConfirm:()=>void}) {
  const insights=result.insights||[];
  const focus=insights.filter((x:any)=>x.needs_confirmation);
  const [confirmedIds,setConfirmedIds]=useState<Set<string>>(new Set());
  useEffect(()=>setConfirmedIds(new Set()),[result.session?.id]);
  function confirmOne(id:string){setConfirmedIds(previous=>{const next=new Set(previous);next.add(id);return next})}
  const remaining=focus.filter((item:any)=>!confirmedIds.has(String(item.id))).length;
  return <div className="analysis panel"><div className="analysis-head"><div><span className="candidate-badge">AI 初步提炼 · 尚未吸收</span><h3>{result.session?.analysis_summary||`提炼出 ${insights.length} 条候选经验`}</h3><p>这些都是候选经验。优先检查有疑问的内容，其余内容无需逐条操作。</p>{result.image_ingestion&&<p className="image-ingestion-result">图片摄入：已保存 {result.image_ingestion.stored} 张{result.image_ingestion.failed?`，${result.image_ingestion.failed} 张失败`:""}</p>}</div><div className="analysis-count"><strong>{insights.length}</strong><small>候选经验</small></div></div>{insights.map((item:any)=>{const checked=confirmedIds.has(String(item.id));return <div className={`insight ${item.needs_confirmation?"focus":""} ${checked?"checked":""}`} key={item.id}><div className="insight-mark">{checked?"✓":item.needs_confirmation?"?":"✓"}</div><div><span>{item.dimension} · 置信度 {Math.round(Number(item.confidence)*100)}%</span><strong>{item.judgment}</strong><p>{item.reusable_rule}</p></div>{item.needs_confirmation?<button className="insight-confirm-button" disabled={checked} onClick={()=>confirmOne(String(item.id))}>{checked?"已确认":"需要你的判断"}</button>:<span className="understood-label">无需重点确认</span>}</div>})}<div className="analysis-actions"><span>{remaining?`${remaining} 条需要你的判断`:"没有需要重点确认的内容"}</span><button className="primary" disabled={busy} onClick={onConfirm}>{busy?"正在吸收…":"确认并吸收全部"}</button></div></div>
}

function Articles({brandCode}:{brandCode:string}){
  const [items,setItems]=useState<any[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [query,setQuery]=useState("");
  const [filter,setFilter]=useState("全部");
  const [forgetTarget,setForgetTarget]=useState<any>(null);
  const [forgetPreview,setForgetPreview]=useState<any>(null);
  const [forgetBusy,setForgetBusy]=useState(false);
  const [forgetError,setForgetError]=useState("");
  function loadArticles(){
    let active=true;
    setLoading(true);
    apiFetch(`${API}/v1/xhs/articles?brand_code=${brandCode}&limit=100`)
      .then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail||"文章记录读取失败");return data})
      .then(data=>{if(active)setItems(data.items||[])})
      .catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"文章记录读取失败")})
      .finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  }
  useEffect(()=>{
    return loadArticles();
  },[]);
  async function openForget(item:any){
    setForgetTarget(item);setForgetPreview(null);setForgetError("");setForgetBusy(true);
    try{
      const response=await apiFetch(`${API}/v1/xhs/articles/${item.id}/forget-preview`);
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"无法计算遗忘范围");
      setForgetPreview(data);
    }catch(reason){setForgetError(reason instanceof Error?reason.message:"无法计算遗忘范围")}
    finally{setForgetBusy(false)}
  }
  async function confirmForget(){
    if(!forgetTarget?.id)return;setForgetBusy(true);setForgetError("");
    try{
      const response=await apiFetch(`${API}/v1/xhs/articles/${forgetTarget.id}/forget-knowledge`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({forgotten_by:"本地运营用户",reason:"用户在文章库主动遗忘派生知识"})});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"遗忘失败");
      setForgetTarget(null);setForgetPreview(null);loadArticles();
    }catch(reason){setForgetError(reason instanceof Error?reason.message:"遗忘失败")}
    finally{setForgetBusy(false)}
  }
  const typeLabel=(item:any)=>item.learning_mode==="positive_example"?"正例":item.learning_mode==="negative_example"?"反例":item.article_type==="competitor_content"?"竞品":item.learning_mode==="revision_pair"?"修改案例":"普通文章";
  const statusMeta=(item:any)=>({absorbed:["已吸收","absorbed"],forgotten:["知识已遗忘","forgotten"],pending_confirmation:["待确认","pending"],processing:["吸收中","processing"],failed:["吸收失败","failed"],not_learned:["未吸收","not-learned"]}[item.absorption_status]||["未吸收","not-learned"]);
  const visible=items.filter(item=>{
    const matchesQuery=!query.trim()||[item.title,item.creator_name,item.product_code].some(value=>String(value||"").toLowerCase().includes(query.trim().toLowerCase()));
    return matchesQuery&&(filter==="全部"||typeLabel(item)===filter);
  });
  const formatTime=(value:string|null)=>value?new Intl.DateTimeFormat("zh-CN",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(new Date(value)):"尚未确认";
  return <section className="page articles-page">
    <div className="filterbar"><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索标题、达人、产品…"/>{["全部","正例","反例","竞品"].map(name=><button key={name} className={filter===name?"active":""} onClick={()=>setFilter(name)}>{name}</button>)}<span className="view-toggle">共 {visible.length} 篇</span></div>
    {loading&&<div className="article-state">正在读取文章和吸收记录…</div>}
    {error&&<div className="article-state error">{error}<small>请确认后端服务和数据库正在运行。</small></div>}
    {!loading&&!error&&visible.length===0&&<div className="article-state"><strong>{items.length?"没有符合条件的文章":"还没有已导入的文章"}</strong><small>{items.length?"尝试更换关键词或分类。":"从“吸收导入”添加第一篇文章后，会在这里显示吸收状态。"}</small></div>}
    {!loading&&!error&&visible.length>0&&<div className="article-grid">{visible.map((item,i)=>{const [status,statusClass]=statusMeta(item);return <article className="article-card" key={item.id}><div className={`cover c${i%4+1} ${item.first_asset_id?"has-image":""}`}>{item.first_asset_id&&<img src={`${API}/v1/assets/${item.first_asset_id}/content`} alt="文章首图" loading="lazy"/>}<span>{typeLabel(item)}</span><strong>{(item.title||"未命名文章").slice(0,18)}</strong></div><div className="article-info"><div><span>{item.version_type==="approved_final"?"终稿":"原稿"}</span><i className={`absorption-status ${statusClass}`}>{status}</i></div><h3>{item.title||"未命名文章"}</h3><p>{item.creator_name||"未记录作者"} · {formatTime(item.confirmed_at||item.completed_at||item.version_created_at)}</p><div className="absorption-evidence"><span>{item.knowledge_count||0} 条知识</span><span>{item.insight_count||0} 条提炼结果</span><span>{item.image_count||0} 张图片已保存</span>{item.failed_image_count>0&&<span className="image-failed">{item.failed_image_count} 张失败</span>}{item.confirmed_at&&item.absorption_status!=="forgotten"&&<span>吸收于 {formatTime(item.confirmed_at)}</span>}</div>{item.absorption_status==="absorbed"&&<button className="forget-knowledge-button" onClick={()=>openForget(item)}>忘记这篇文章产生的知识</button>}{item.absorption_status==="forgotten"&&<p className="forgotten-hint">原文与图片仍保留，可重新导入学习</p>}</div></article>})}</div>}
    {forgetTarget&&<div className="modal-backdrop"><div className="confirm-modal forget-modal" role="dialog" aria-modal="true" aria-labelledby="forget-title"><div className="modal-warning">!</div><h3 id="forget-title">忘记这篇文章产生的知识？</h3><p className="forget-article-title">{forgetTarget.title||"未命名文章"}</p>{forgetBusy&&!forgetPreview?<div className="forget-loading">正在计算影响范围…</div>:forgetPreview&&<><div className="forget-impact"><div><strong>{forgetPreview.knowledge_version_count}</strong><span>知识版本</span></div><div><strong>{forgetPreview.chunk_count}</strong><span>文本分块</span></div><div><strong>{forgetPreview.vector_count}</strong><span>向量数据</span></div><div><strong>{forgetPreview.job_count}</strong><span>队列任务</span></div></div><p>原始文章和 {forgetTarget.image_count||0} 张已保存图片不会删除。遗忘后，这些知识不再参与 AI 检索，并允许重新吸收。</p>{forgetPreview.affected_article_count>1&&<div className="forget-warning">该学习记录同时关联 {forgetPreview.affected_article_count} 篇文章，相关派生知识会一起被遗忘。</div>}</>}{forgetError&&<div className="queue-error">{forgetError}</div>}<div><button className="ghost" disabled={forgetBusy} onClick={()=>{setForgetTarget(null);setForgetPreview(null)}}>取消</button><button className="danger-button" disabled={forgetBusy||!forgetPreview?.can_forget} onClick={confirmForget}>{forgetBusy?"处理中…":"确认遗忘知识"}</button></div></div></div>}
  </section>
}

function Knowledge(){const groups=[['品牌调性','0','说什么，更定义怎么说'],['合规红线','0','明确不能触碰的表达'],['内容方法','0','标题、开头与种草结构'],['审核经验','0','从真实修改中持续学习'],['正反案例','0','用具体内容提供证据'],['竞品参考','0','只学习方法，不冒充规则']];return <section className="page"><div className="toolbar"><div><span className="eyebrow">可追溯的运营判断</span><h2>知识库</h2></div><div><button className="ghost">冲突中心 <b className="alert-dot">0</b></button><button className="primary">＋ 添加经验</button></div></div><div className="knowledge-summary"><div><strong>知识健康度 —</strong><span>正式知识 0 条 · 候选知识 0 条 · 冲突 0 条</span></div><div className="health"><i style={{width:"0%"}}/></div></div><div className="knowledge-grid">{groups.map(([name,n,desc],i)=><button className="knowledge-card" key={name}><span className={`knowledge-icon k${i}`}>◇</span><div><small>{n} 条知识</small><strong>{name}</strong><p>{desc}</p></div><b>→</b></button>)}</div></section>}

function Review(){return <section className="page"><div className="toolbar"><div><span className="eyebrow">即将接入完整审核大脑</span><h2>AI 审核</h2></div><button className="primary">开始新审核</button></div><div className="review-layout"><div className="draft"><span>原稿</span><h3>熬夜脸三天满血复活</h3><p>最近工作太忙，每天都熬到凌晨。幸好遇到了这款面霜，用了三天暗沉彻底消失，所有人都必须试试……</p><mark>用了三天暗沉彻底消失</mark><mark>所有人都必须试试</mark></div><div className="review-result"><span className="risk">高风险 · 2项</span><h3>审核结论与问题</h3><div className="review-score"><strong>62</strong><span>可发布程度<br/><small>需要较大修改</small></span></div><div className="issue"><b>01</b><div><strong>功效承诺绝对化</strong><p>“彻底消失”缺乏证据且可信度较低。</p></div></div><div className="issue"><b>02</b><div><strong>强迫式推荐破坏原生感</strong><p>建议改为具体使用感受和适用人群。</p></div></div></div></div><div className="revised"><span>AI 建议修改稿</span><p>最近工作节奏有点乱，晚间护肤也跟着做了减法。连续使用这款面霜后，肌肤看起来更细腻，暗沉状态也有所改善……</p><button>复制修改稿</button></div></section>}

function QueueCenter({api,brandCode}:{api:string,brandCode:string}){
  const [open,setOpen]=useState(false);
  const [data,setData]=useState<any>(null);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(false);
  function refresh(silent=false){
    if(!silent)setLoading(true);
    apiFetch(`${api}/v1/brands/${brandCode}/learning-queue?limit=30`)
      .then(async response=>{const result=await response.json();if(!response.ok)throw new Error(result.detail||"队列读取失败");return result})
      .then(result=>{setData(result);setError("")})
      .catch(reason=>setError(reason instanceof Error?reason.message:"队列读取失败"))
      .finally(()=>setLoading(false));
  }
  useEffect(()=>{refresh(true);const timer=setInterval(()=>refresh(true),open?3000:10000);return()=>clearInterval(timer)},[open]);
  const active=(data?.summary?.pending||0)+(data?.summary?.running||0);
  const formatTime=(value:string|null)=>value?new Intl.DateTimeFormat("zh-CN",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(new Date(value)):"--";
  return <><button className="sidebar-queue" onClick={()=>{setOpen(true);refresh()}} aria-label="学习与向量队列"><span>●</span><b>学习队列</b>{active>0&&<i>{active>99?"99+":active}</i>}</button>{open&&<div className="settings-overlay queue-overlay"><div className="queue-dialog" role="dialog" aria-modal="true" aria-labelledby="queue-title"><button className="settings-close" onClick={()=>setOpen(false)} aria-label="关闭队列">×</button><div className="queue-heading"><div><span className="eyebrow">真实写入状态</span><h2 id="queue-title">AI学习与向量化队列</h2><p>只有出现“已进入向量库”，才代表Embedding已成功写入。</p></div><button className="ghost" onClick={()=>refresh()} disabled={loading}>{loading?"刷新中…":"刷新状态"}</button></div>{error&&<div className="queue-error">{error}</div>}{data&&<><div className="queue-summary"><div><span>进行中</span><strong>{data.summary.active_items}</strong><small>学习与确认流程</small></div><div><span>向量队列</span><strong>{data.summary.pending+data.summary.running}</strong><small>{data.summary.running} 个正在处理</small></div><div><span>已写入向量</span><strong>{data.summary.vector_count}</strong><small>数据库真实记录</small></div><div className={data.summary.failed?"has-failure":""}><span>失败任务</span><strong>{data.summary.failed}</strong><small>可查看失败原因</small></div></div><div className="queue-list">{data.items.length===0?<div className="queue-empty">还没有学习记录</div>:data.items.map((item:any)=><div className="queue-item" key={item.id}><div className={`queue-state-dot ${item.state}`}>{item.state==="vectorized"?"✓":item.state.includes("failed")?"!":""}</div><div className="queue-item-main"><div className="queue-item-title"><strong>{item.title}</strong><span className={`queue-state ${item.state}`}>{item.state_label}</span></div><p>{item.creator_name||"本地运营用户"} · {formatTime(item.confirmed_at||item.completed_at||item.created_at)}</p><div className="queue-progress"><i style={{width:`${item.progress}%`}}/></div><div className="queue-meta"><span>候选经验 {item.insight_count||0}</span><span>正式知识 {item.knowledge_count||0}</span><span>向量 {item.embedding_count||0}/{item.chunk_count||0}</span>{item.pending_jobs>0&&<span>排队 {item.pending_jobs}</span>}{item.running_jobs>0&&<span>处理中 {item.running_jobs}</span>}</div>{item.last_job_error&&<div className="queue-item-error">{item.last_job_error}</div>}</div></div>)}</div></>}</div></div>}</>
}

function Settings({api,brandCode,setNotice,notice}:{api:string,brandCode:string,setNotice:(s:string)=>void,notice:string}) {
  const [baseUrl,setBaseUrl]=useState("https://你的服务地址/compatible-mode/v1");
  const [model,setModel]=useState("qwen-plus");
  const [key,setKey]=useState("");
  const [working,setWorking]=useState<"save"|"test"|null>(null);
  const [configured,setConfigured]=useState(false);
  const [showResetDialog,setShowResetDialog]=useState(false);

  useEffect(()=>{
    apiFetch(`${api}/v1/brands/${brandCode}/ai-settings/content_learning`)
      .then(async r=>r.ok?await r.json():null)
      .then(data=>{if(data){setBaseUrl(data.base_url);setModel(data.model_name);setConfigured(true)}})
      .catch(()=>{});
  },[api]);

  function friendlyError(error:unknown) {
    if (error instanceof TypeError && /fetch/i.test(error.message))
      return "无法连接本地后端，请确认知识库服务正在运行后重试。";
    return error instanceof Error ? error.message : "操作失败，请检查配置后重试。";
  }
  function validate() {
    const value=baseUrl.trim();
    if (!value.startsWith("https://")) return "API地址必须以 https:// 开头。";
    if (value.includes("api.deepseek.com") && value.includes("compatible-mode"))
      return "DeepSeek不使用 compatible-mode 地址，请改为 https://api.deepseek.com。";
    if (value.includes("api.deepseek.com") && !["deepseek-v4-flash","deepseek-v4-pro"].includes(model.trim()))
      return "当前DeepSeek模型名称请填写 deepseek-v4-flash 或 deepseek-v4-pro。";
    if (!model.trim()) return "请填写模型名称。";
    return "";
  }
  async function save(showSuccess=true) {
    const validation=validate(); if(validation){setNotice(validation);return false}
    setWorking("save");
    try {
      const r=await apiFetch(`${api}/v1/brands/${brandCode}/ai-settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({purpose:"content_learning",provider:"openai_compatible",base_url:baseUrl.trim(),model_name:model.trim(),api_key:key||null,enabled:true,extra_options:{}})});
      const d=await r.json().catch(()=>({})); if(!r.ok)throw new Error(d.detail||`保存失败（${r.status}）`);
      setConfigured(true); if(showSuccess)setNotice("设置已加密保存。建议继续点击“测试连接”确认模型可用。"); setKey(""); return true;
    } catch(e){setNotice(friendlyError(e));return false} finally{setWorking(null)}
  }
  async function testConnection(){
    const validation=validate(); if(validation){setNotice(validation);return}
    setWorking("test");
    try{
      if(key){const saved=await save(false);if(!saved)return;setWorking("test")}
      const r=await apiFetch(`${api}/v1/brands/${brandCode}/ai-settings/content_learning/test`,{method:"POST"});
      const d=await r.json().catch(()=>({})); if(!r.ok)throw new Error(d.detail||`连接失败（${r.status}）`);
      setNotice(`连接成功：${d.model_name} 可以正常返回结果。`);
    }catch(e){setNotice(friendlyError(e))}finally{setWorking(null)}
  }
  function choose(provider:"bailian"|"deepseek"){
    if(configured)return;
    if(provider==="deepseek"){setBaseUrl("https://api.deepseek.com");setModel("deepseek-v4-flash")}
    else{setBaseUrl("https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/compatible-mode/v1");setModel("qwen-plus")}
    setNotice("");
  }
  async function resetApiKey(){
    setWorking("save");
    try{
      const r=await apiFetch(`${api}/v1/brands/${brandCode}/ai-settings/content_learning`,{method:"DELETE"});
      const d=await r.json().catch(()=>({})); if(!r.ok)throw new Error(d.detail||"重置失败");
      setConfigured(false);setShowResetDialog(false);setKey("");setNotice("API Key已重置，请重新选择模型并填写新密钥。");
    }catch(e){setShowResetDialog(false);setNotice(friendlyError(e))}finally{setWorking(null)}
  }
  return <><section className="page settings"><div className="toolbar"><div><span className="eyebrow">由你选择大脑</span><h2>模型设置</h2></div><span className="secure">{configured?"密钥已加密保存":"等待配置密钥"}</span></div><div className={`settings-card ${configured?"configured":""}`}><div className="setting-title"><span>✦</span><div><h3>内容理解模型</h3><p>用于理解好坏文章、前后稿差异和你的运营经验</p></div><i>{configured?"已配置":"待配置"}</i></div><div className="provider-presets"><span>快速选择</span><button disabled={configured} onClick={()=>choose("bailian")}>阿里云百炼</button><button disabled={configured} onClick={()=>choose("deepseek")}>DeepSeek</button></div><label>API 地址<input disabled={configured} value={baseUrl} onChange={e=>setBaseUrl(e.target.value)}/><small>填写兼容OpenAI的接口根地址，系统会自动追加 /chat/completions。</small></label><div className="field-grid"><label>模型名称<input disabled={configured} value={model} onChange={e=>setModel(e.target.value)}/><small>DeepSeek可选 deepseek-v4-flash 或 deepseek-v4-pro。</small></label><label>API Key<input disabled={configured} type="password" value={key} onChange={e=>setKey(e.target.value)} placeholder={configured?"API Key 已安全保存":"填写或粘贴API Key"}/><small>{configured?"如需更换密钥，请先点击重置。":"密钥只会加密保存，不会在页面中回显。"}</small></label></div><div className="setting-actions"><button className="ghost" onClick={testConnection} disabled={working!==null||!configured}>{working==="test"?"正在测试…":"测试连接"}</button>{configured?<button className="reset-button" onClick={()=>setShowResetDialog(true)} disabled={working!==null}>重置 API Key</button>:<button className="primary" onClick={()=>save()} disabled={working!==null}>{working==="save"?"正在保存…":"保存设置"}</button>}</div>{notice&&<div className="notice">{notice}</div>}</div><div className="auto-route"><div><span>自动</span><div><strong>智能模型选择</strong><p>系统根据任务难度、速度和成本自动选择最合适的模型。</p></div></div><button className="switch on"><i/></button></div></section>{showResetDialog&&<div className="modal-backdrop" role="presentation"><div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="reset-title"><span className="modal-warning">!</span><h3 id="reset-title">是否重置 API Key？</h3><p>重置后，当前模型配置和已加密保存的API Key将被删除，AI吸收导入功能会暂停，直到你重新配置密钥。</p><div><button className="ghost" onClick={()=>setShowResetDialog(false)} disabled={working!==null}>取消</button><button className="danger-button" onClick={resetApiKey} disabled={working!==null}>{working?"正在重置…":"确认重置"}</button></div></div></div>}</>
}
