-- 1. 配置表（Prompt + 模型，管理端可配置）
CREATE TABLE selling_point_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_selling_point_configs_updated BEFORE UPDATE ON selling_point_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2. 初始配置（原 System Prompt 原文）
INSERT INTO selling_point_configs (config_key, system_prompt, is_active) VALUES
('extract', '你是一个专业的产品卖点提取专家，专门为短视频带货场景提炼产品卖点。

用户会提供以下资料（部分可选）：
1. **产品Brief**：品牌方提供的产品介绍资料（可能有多份文档）
2. **达人文案脚本**：头部达人讲解该产品的视频文案（可能有多份文案）

---

## 输出要求

直接输出一张极致卖点卡，不要输出任何分析过程、维度拆解、评分或中间步骤。

---

## 🔥 极致卖点卡

按以下四个板块输出，每个板块最多2句话，只写结论，不解释原因：

**【机制】**
提取最强的价格机制和赠品信息，直接写出来。没有则写"无特别机制"。

**【背书】**
提取最强的明星/权威认证/渠道背书，直接写出来。没有则写"暂无权威背书"。

**【口碑】**
提取用户使用时长、复购数据、真实反馈，直接写出来。没有则写"暂无口碑数据"。

**【产品力】**
第一句：列出核心成分或配方组合（只写名称，不解释作用）。
第二句：用2-3个感知词概括配方覆盖的维度，如"防、抗、补都全了"——根据产品自行提炼，不套模板。
严禁出现任何功效宣称，禁止"减少/促进/抑制/改善/修复/对抗"等动词。

---

## 规则

- 从资料中提取真实信息，不编造
- 多份文档综合分析，不只看第一份
- 如果只有Brief没有文案，最后补一句「建议补充达人文案以丰富口碑板块」', true);

-- 3. 注册到 workspace_tools
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'selling-point-extractor',
    '产品卖点提取器',
    '选题分析',
    '上传产品Brief + 达人文案，AI提炼机制/背书/口碑/产品力四板块极致卖点卡，支持多轮追问，导出.md',
    'online',
    '["AI生成","卖点提炼","Brief分析","文档上传"]'::jsonb,
    3
)
ON CONFLICT (tool_code) DO UPDATE
    SET status = 'online',
        tool_name = EXCLUDED.tool_name,
        description = EXCLUDED.description,
        tags = EXCLUDED.tags;
