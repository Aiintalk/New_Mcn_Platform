-- 016_qianchuan_review.sql
-- 注册 qianchuan-review 工具到 workspace_tools

INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'qianchuan-review',
    '千川脚本复盘',
    '投放分析',
    '上传千川脚本 + 投放数据，AI 深度复盘跑量素材、高ROI素材、开头效率，支持导出报告',
    'online',
    '["AI生成","千川","复盘","投放分析","脚本"]'::jsonb,
    4
)
ON CONFLICT (tool_code) DO UPDATE
    SET status    = 'online',
        tool_name = EXCLUDED.tool_name,
        description = EXCLUDED.description,
        tags      = EXCLUDED.tags;
