-- 054_eval_case_jobs.sql
-- AIGC 评测 — 异步运行：按 case 拆分的 job 表（方案 C：arq+Redis，Phase 2）
-- plan: docs/superpowers/plans/2026-07-26-async-run-architecture.md
--
-- 一个 run 拆成 N 个 case-job（每个 test_case 一行）；arq worker 从 Redis 取 job 执行。
-- status 由 worker 推进：pending → running → done/failed；cancel 时 → cancelled。
-- 重启恢复：status='running' 且 started_at 超时的，启动时由 worker 重置 pending 重投。

CREATE TABLE IF NOT EXISTS eval_case_jobs (
    id            BIGSERIAL    PRIMARY KEY,
    run_id        BIGINT       NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    test_case_id  BIGINT       NOT NULL REFERENCES eval_test_cases(id) ON DELETE RESTRICT,
    status        VARCHAR(20)  NOT NULL DEFAULT 'pending',   -- pending/running/done/failed/cancelled
    attempts      INT          NOT NULL DEFAULT 0,
    max_attempts  INT          NOT NULL DEFAULT 3,
    last_error    TEXT,
    enqueued_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    CONSTRAINT uq_eval_case_jobs_run_testcase UNIQUE (run_id, test_case_id),
    CONSTRAINT chk_eval_case_jobs_status
        CHECK (status IN ('pending','running','done','failed','cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_eval_case_jobs_status_enqueued
    ON eval_case_jobs (status, enqueued_at);
CREATE INDEX IF NOT EXISTS idx_eval_case_jobs_run
    ON eval_case_jobs (run_id);
