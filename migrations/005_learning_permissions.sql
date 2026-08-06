-- 新增教学层表的应用账号权限。
-- 使用独立迁移修复，不修改已经执行过的 003/004。

GRANT SELECT, INSERT, UPDATE, DELETE ON xhs_learning_sessions TO brand_kb;
GRANT SELECT, INSERT, UPDATE, DELETE ON xhs_learning_insights TO brand_kb;
GRANT SELECT, INSERT, UPDATE, DELETE ON brand_ai_settings TO brand_kb;
