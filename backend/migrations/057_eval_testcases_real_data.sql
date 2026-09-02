-- 057_eval_testcases_real_data.sql
-- 张翀真实测试集集成（方案 A：纯业务数据）配套迁移。
--
-- 背景：
--   1. input_payload 里的 messages（改写指令）是早期遗留死字段——generator.py 渲染
--      版本提示词模板后自行构造 messages（generator.py:88），从不读
--      input_payload['messages']。测试例应只含业务数据，指令归版本提示词。
--   2. 张翀第一批 10 条真实测试例由 seed_eval_testcases_real.py 灌入（带
--      '真实数据' tag），demo 占位数据（'demo' tag）就此停用（保留不删，
--      历史评估结果仍引用它们）。
--
-- 变更：
--   1. 全量剥离 eval_test_cases.input_payload 中的 messages 键（含已软删的）。
--   2. demo tag 的测试例 is_active 置 false。
--
-- 幂等：可重跑（- 'messages' 对无该键的 JSONB 是 no-op；WHERE 条件天然幂等）。

-- 1. 剥离死字段 messages
UPDATE eval_test_cases
SET input_payload = input_payload - 'messages',
    updated_at    = NOW()
WHERE input_payload ? 'messages';

-- 2. 停用 demo 占位测试例（真实数据到达后不再参与新评估运行）
UPDATE eval_test_cases
SET is_active   = FALSE,
    updated_at  = NOW()
WHERE 'demo' = ANY(tags)
  AND is_active = TRUE;
