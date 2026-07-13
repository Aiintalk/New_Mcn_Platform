-- 050_material_library_media.sql
-- 红人素材库：在既有 kol_references 表上补齐文档解析元数据和私有视频对象引用。
-- 不迁移历史素材；全部新字段允许为空，旧记录保持可读。

BEGIN;

ALTER TABLE kol_references
    ADD COLUMN IF NOT EXISTS data_description TEXT,
    ADD COLUMN IF NOT EXISTS document_name VARCHAR(500),
    ADD COLUMN IF NOT EXISTS document_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS document_size BIGINT,
    ADD COLUMN IF NOT EXISTS video_oss_key VARCHAR(1024),
    ADD COLUMN IF NOT EXISTS video_name VARCHAR(500),
    ADD COLUMN IF NOT EXISTS video_content_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS video_size BIGINT;

CREATE INDEX IF NOT EXISTS idx_kol_references_video_oss_key
    ON kol_references(video_oss_key)
    WHERE video_oss_key IS NOT NULL AND deleted_at IS NULL;

COMMIT;
