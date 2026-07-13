-- 为已有红人工作台配置启用千川成片预审入口。
-- 仅补充系统页签配置，不迁移或改写任何历史业务数据。
UPDATE kol_workspace_configs
SET enabled_tabs = enabled_tabs || '["film-review"]'::jsonb
WHERE NOT enabled_tabs ? 'film-review';
