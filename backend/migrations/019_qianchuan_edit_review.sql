-- 019_qianchuan_edit_review.sql
-- 注册千川剪辑预审工具到 workspace_tools
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
  'qianchuan-edit-review',
  '千川剪辑预审',
  '千川',
  '上传原版爆款与我方成片，AI看画面+文案，给出剪辑和画面插入建议',
  'online',
  '["AI生成","千川","剪辑","多模态","docx"]'::jsonb,
  (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM workspace_tools WHERE category = '千川')
)
ON CONFLICT (tool_code) DO NOTHING;
