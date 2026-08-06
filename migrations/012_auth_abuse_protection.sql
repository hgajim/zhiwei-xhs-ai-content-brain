CREATE TABLE auth_login_attempts(
 id bigserial PRIMARY KEY,email_hash text NOT NULL,ip_address inet,succeeded boolean NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_auth_attempts_recent ON auth_login_attempts(email_hash,created_at DESC);
GRANT SELECT,INSERT,DELETE ON auth_login_attempts TO brand_kb;
GRANT USAGE,SELECT ON SEQUENCE auth_login_attempts_id_seq TO brand_kb;
