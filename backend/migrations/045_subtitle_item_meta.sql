-- 045_subtitle_item_meta.sql
-- subtitle_items 加 meta_json 字段：单条 extract 完成后存视频元信息
--
-- 背景：单条 extract 异步化后，需要在 SubtitleItem 上记录视频元信息
-- （play_url/cover_url/nickname/digg_count/aweme_id/audio_url）。
-- 用专用 JSON 字段比 hack job.phase 干净得多。
--
-- 批量任务不需要这些字段（批量只关心 transcript），meta_json 默认 NULL 即可。

BEGIN;

ALTER TABLE subtitle_items
  ADD COLUMN IF NOT EXISTS meta_json TEXT;

COMMENT ON COLUMN subtitle_items.meta_json IS
  '单条 extract 完成后的视频元信息 JSON（play_url/cover_url/nickname/digg_count/aweme_id/audio_url）；批量任务为 NULL';

COMMIT;
