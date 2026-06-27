-- 044_subtitle_job_kind_and_soft_delete.sql
-- 字幕任务扩展：单条 extract 也走 SubtitleJob + 软删除支持
--
-- 背景：
-- Sprint 19 时单条 /extract 是同步阻塞调用，切页面会丢失进度。
-- Sprint 21 改为异步任务化：单条也创建 SubtitleJob（kind='single', total=1），
-- 与批量任务（kind='batch'）共用一张表，前端可统一展示历史记录。
-- 同时加 deleted_at 支持用户在前端删除记录（软删除，保留审计）。
--
-- 向后兼容：kind 默认 'batch'，所有历史数据自动归为批量；deleted_at 默认 NULL。

BEGIN;

-- 1. subtitle_jobs 加 kind 字段（single / batch）
ALTER TABLE subtitle_jobs
  ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'batch';

-- 所有历史数据（来自 Sprint 19 批量任务）自动归为 batch，无需 UPDATE

-- 2. subtitle_jobs 加 deleted_at 字段（软删除）
ALTER TABLE subtitle_jobs
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- 历史查询过滤 deleted_at IS NULL，已有数据默认 NULL = 未删除，无需 UPDATE

-- 3. 索引：按 kind + deleted_at 过滤的列表查询
CREATE INDEX IF NOT EXISTS idx_subtitle_jobs_kind_deleted
  ON subtitle_jobs(kind, deleted_at);

COMMIT;
