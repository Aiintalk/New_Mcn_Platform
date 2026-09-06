-- 智能体任务配置 V1.3 阶段一：每个智能体独立维护当前生效的项目范围。

BEGIN;

CREATE TABLE IF NOT EXISTS agent_task_configs (
    id BIGSERIAL PRIMARY KEY,
    agent_code VARCHAR(64) NOT NULL,
    selected_project_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_task_configs_agent_code UNIQUE (agent_code),
    CONSTRAINT chk_agent_task_configs_selected_project_ids_array
        CHECK (jsonb_typeof(selected_project_ids) = 'array')
);

DROP TRIGGER IF EXISTS trg_agent_task_configs_updated ON agent_task_configs;
CREATE TRIGGER trg_agent_task_configs_updated
    BEFORE UPDATE ON agent_task_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
