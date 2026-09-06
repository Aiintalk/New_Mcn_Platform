-- 智能体任务配置 V1.6 阶段二：共享报告根目录与正式自动任务幂等保护。

BEGIN;

ALTER TABLE agent_task_configs
    ADD COLUMN IF NOT EXISTS report_root_ref TEXT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_task_jobs_content_analysis_formal_auto_run_key
    ON task_jobs ((input_payload->>'run_key'))
    WHERE tool_code IN ('content-analysis-daily', 'content-analysis-weekly')
      AND input_payload->>'agent_code' = 'content-analysis'
      AND input_payload->>'run_type' = 'auto'
      AND input_payload->>'task_code' IN ('daily', 'weekly')
      AND NULLIF(BTRIM(input_payload->>'run_key'), '') IS NOT NULL;

COMMIT;
