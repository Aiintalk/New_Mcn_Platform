-- 014_tiktok_writer.sql
-- 注册 tiktok-writer 工具到 workspace_tools

INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'tiktok-writer',
    'TikTok 脚本仿写',
    '内容创作',
    '粘贴 TikTok 视频文案，AI 分析结构并仿写 Body，支持多轮迭代修改，最终导出 Word',
    'dev',
    '["AI生成","仿写","TikTok","英文","docx"]'::jsonb,
    15
)
ON CONFLICT (tool_code) DO NOTHING;
