"""邮箱密码认证与个人运营大脑。令牌只以SHA-256摘要存储。"""
from __future__ import annotations
import base64, hashlib, hmac, secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from psycopg import Connection
from app.config import settings

def normalize_email(value: str) -> str: return value.strip().lower()
def hash_password(password: str) -> str:
    salt=secrets.token_bytes(16); iterations=310_000
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"
def verify_password(password: str, encoded: str) -> bool:
    try:
        _,raw_iterations,raw_salt,raw_digest=encoded.split('$')
        digest=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.urlsafe_b64decode(raw_salt),int(raw_iterations))
        return hmac.compare_digest(digest,base64.urlsafe_b64decode(raw_digest))
    except Exception: return False
def token_hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def _issue_session(conn: Connection,user_id,user_agent=None,ip_address=None)->dict[str,Any]:
    token=secrets.token_urlsafe(40); expires=datetime.now(timezone.utc)+timedelta(days=settings.auth_session_days)
    conn.execute("INSERT INTO auth_sessions(user_id,token_hash,expires_at,user_agent,ip_address) VALUES(%s,%s,%s,%s,%s)",(user_id,token_hash(token),expires,user_agent,ip_address))
    return {'access_token':token,'token_type':'bearer','expires_at':expires}

def register(conn:Connection,email:str,password:str,display_name:str)->dict[str,Any]:
    email=normalize_email(email)
    if len(password)<10: raise ValueError('密码至少需要10个字符。')
    if conn.execute('SELECT 1 FROM app_users WHERE lower(email)=%s',(email,)).fetchone(): raise ValueError('该邮箱已经注册。')
    user=conn.execute("INSERT INTO app_users(email,password_hash,display_name) VALUES(%s,%s,%s) RETURNING id,email,display_name,status,is_admin",(email,hash_password(password),display_name.strip() or email.split('@')[0])).fetchone()
    workspace=conn.execute("INSERT INTO workspaces(owner_user_id,name) VALUES(%s,'我的小红书运营大脑') RETURNING id,name",(user['id'],)).fetchone()
    conn.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')",(workspace['id'],user['id']))
    code=f"ws_{str(workspace['id']).replace('-','')[:16]}"
    brand=conn.execute("INSERT INTO brands(code,name,workspace_id) VALUES(%s,%s,%s) RETURNING id,code,name",(code,workspace['name'],workspace['id'])).fetchone()
    return {'user':user,'workspace':{**workspace,'brand_code':brand['code']},**_issue_session(conn,user['id'])}

def login(conn:Connection,email:str,password:str,user_agent=None,ip_address=None)->dict[str,Any]:
    normalized=normalize_email(email);email_digest=hashlib.sha256(normalized.encode()).hexdigest()
    failures=conn.execute("SELECT count(*) count FROM auth_login_attempts WHERE email_hash=%s AND succeeded=false AND created_at>now()-interval '15 minutes'",(email_digest,)).fetchone()['count']
    if failures>=8:raise ValueError('尝试次数过多，请15分钟后再试。')
    user=conn.execute("SELECT * FROM app_users WHERE lower(email)=%s",(normalized,)).fetchone()
    valid=bool(user and user['status']=='active' and verify_password(password,user['password_hash']))
    conn.execute('INSERT INTO auth_login_attempts(email_hash,ip_address,succeeded) VALUES(%s,%s,%s)',(email_digest,ip_address,valid))
    if not valid:raise ValueError('邮箱或密码错误。')
    return {'user':{k:user[k] for k in ('id','email','display_name','status','is_admin')},**_issue_session(conn,user['id'],user_agent,ip_address)}

def authenticate(conn:Connection,authorization:str|None)->dict[str,Any]:
    if not authorization or not authorization.lower().startswith('bearer '): raise ValueError('请先登录。')
    row=conn.execute("""SELECT u.id,u.email,u.display_name,u.status,u.is_admin,s.id session_id
      FROM auth_sessions s JOIN app_users u ON u.id=s.user_id
      WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>now()""",(token_hash(authorization.split(' ',1)[1]),)).fetchone()
    if not row or row['status']!='active': raise ValueError('登录已失效，请重新登录。')
    conn.execute('UPDATE auth_sessions SET last_seen_at=now() WHERE id=%s',(row['session_id'],))
    return row

def user_context(conn:Connection,user_id)->dict[str,Any]:
    workspaces=conn.execute("""SELECT w.id,w.name,w.description,w.status,m.role,b.code brand_code
      FROM workspace_members m JOIN workspaces w ON w.id=m.workspace_id JOIN brands b ON b.workspace_id=w.id
      WHERE m.user_id=%s AND w.status='active' ORDER BY w.created_at""",(user_id,)).fetchall()
    return {'workspaces':workspaces}

def authorize_brand(conn:Connection,user_id,brand_code:str)->None:
    allowed=conn.execute("""SELECT 1 FROM brands b JOIN workspace_members m ON m.workspace_id=b.workspace_id
      WHERE b.code=%s AND m.user_id=%s AND b.workspace_id IS NOT NULL""",(brand_code,user_id)).fetchone()
    if not allowed:raise ValueError('无权访问该运营大脑。')

def authorize_entity(conn:Connection,user_id,entity_type:str,entity_id)->None:
    sources={
      'article':"SELECT b.code FROM xhs_articles a JOIN brands b ON b.id=a.brand_id WHERE a.id=%s",
      'article_version':"SELECT b.code FROM xhs_article_versions v JOIN xhs_articles a ON a.id=v.article_id JOIN brands b ON b.id=a.brand_id WHERE v.id=%s",
      'learning_session':"SELECT b.code FROM xhs_learning_sessions s JOIN brands b ON b.id=s.brand_id WHERE s.id=%s",
      'ai_review':"SELECT b.code FROM xhs_ai_review_runs r JOIN brands b ON b.id=r.brand_id WHERE r.id=%s",
      'asset':"SELECT b.code FROM kb_assets a JOIN brands b ON b.id=a.brand_id WHERE a.id=%s",
    }
    row=conn.execute(sources[entity_type],(entity_id,)).fetchone()
    if not row:raise ValueError('记录不存在或不可访问。')
    authorize_brand(conn,user_id,row['code'])
