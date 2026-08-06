-- 个人运营大脑与本地邮箱登录。现有数据迁移到默认本地用户，确保不丢失。
CREATE TABLE app_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    password_hash text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','pending_deletion')),
    email_verified_at timestamptz,
    is_admin boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_app_users_email_lower ON app_users(lower(email));

CREATE TABLE workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES app_users(id),
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived','pending_deletion')),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE workspace_members (
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner','editor','viewer')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id,user_id)
);
CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    user_agent text,
    ip_address inet,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id,expires_at DESC);
CREATE TABLE password_reset_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE usage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES app_users(id),
    workspace_id uuid REFERENCES workspaces(id),
    event_type text NOT NULL,
    quantity numeric NOT NULL DEFAULT 1,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE brands ADD COLUMN workspace_id uuid REFERENCES workspaces(id);

DO $$
DECLARE local_user uuid; local_workspace uuid;
BEGIN
  INSERT INTO app_users(email,password_hash,display_name,email_verified_at,is_admin)
  VALUES('local@zhiwei.test','disabled-local-account','本地测试用户',now(),true)
  RETURNING id INTO local_user;
  INSERT INTO workspaces(owner_user_id,name,description)
  VALUES(local_user,'我的小红书运营大脑','由现有本地知识库迁移') RETURNING id INTO local_workspace;
  INSERT INTO workspace_members VALUES(local_workspace,local_user,'owner',now());
  UPDATE brands SET workspace_id=local_workspace WHERE workspace_id IS NULL;
END $$;

ALTER TABLE brands ALTER COLUMN workspace_id SET NOT NULL;
CREATE UNIQUE INDEX uq_brands_workspace ON brands(workspace_id);

GRANT SELECT,INSERT,UPDATE,DELETE ON app_users,workspaces,workspace_members,
auth_sessions,password_reset_tokens,usage_events TO brand_kb;
