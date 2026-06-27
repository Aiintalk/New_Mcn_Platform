-- kols 表新增 5 个人物档案分区字段（Sprint 18）
ALTER TABLE kols ADD COLUMN IF NOT EXISTS background     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS experience     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS relationships  TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS unique_story   TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS extra_notes    TEXT;
