-- ============================================================================
-- eval 模块 demo 数据（安雅 rubric 版，2026-07-26 Phase 0）
-- 前置：先 TRUNCATE eval_* CASCADE 再跑 migrations/053_eval_core.sql（建 4 维 + rubric + default 策略），
--       再跑本文件（test_cases / versions / schedules / judge_models / 2 条 demo run）。
-- 可重跑：按 name 去重。
-- input_payload 键对齐渲染管线：name / persona(→{{soul}}) / product_info / original_script / messages
-- ============================================================================
\set ADMIN_ID `(SELECT id FROM users WHERE username='admin')`

-- ① 测试样本（5）—— input_payload 用规范键
INSERT INTO eval_test_cases (tool_code, name, description, input_payload, tags, is_active, created_by)
SELECT t.tool_code, t.name, t.description, t.input_payload, t.tags, t.is_active, (SELECT id FROM users WHERE username='admin')
FROM (VALUES
  ('qianchuan-writer'::varchar, '焦虑型 · 美妆精华开屏（熬夜脸黄）'::text, '3 秒痛点钩子前置，主打熬夜暗沉提亮，60 秒口播'::text,
   jsonb_build_object(
     'name','慧敏','persona','韩国欧尼慧敏：亲和种草风、爱用"姐妹们"开场、擅长期望值管理',
     'product_info', E'核心成分：5% 烟酰胺 + 双重玻尿酸 + 熊果苷\n价格：198 买一送一（正装+替换装）\n定位：熬夜脸黄，28 天提亮\n人群：25-35 熬夜女性白领\n背书：皮肤科医生推荐、SGS 报告',
     'original_script', E'【0-3s】姐妹们，熬夜脸都黄了吧？\n【3-15s】我用 28 天这支 5% 烟酰胺精华，黄气被吃掉了。\n【15-35s】熊果苷阻断、烟酰胺代谢，一条龙。\n【35-50s】皮肤科医生推荐，敏感肌可用。\n【50-60s】198 买一送一，前 500 名送化妆包，冲！',
     'messages', jsonb_build_array(jsonb_build_object('role','user','content','仿写一条美妆精华千川文案，3 秒抓"熬夜脸黄"痛点，突出 5% 烟酰胺，结尾 198 买一送一逼单，60 秒。'))
   ), ARRAY['焦虑型','美妆','熬夜','提亮']::text[], TRUE::boolean),
  ('qianchuan-writer', '诱惑型 · 护肤套装大促逼单', '满减+赠品矩阵，限时大促',
   jsonb_build_object('name','慧敏','persona','韩国欧尼慧敏：亲和种草风、擅长算账式逼单',
     'product_info', E'四件套（洁面+水+乳+霜）\n价格：日常 596，活动 399 再减 100 = 299\n赠品：正装眼霜+面膜10片+化妆棉+托特包\n限时 2 小时，库存 800 套',
     'original_script', E'【0-5s】这套护肤我囤了三套，今天价格我没忍住。\n【5-25s】596 今天 399 再减 100 等于 299，赠品比正装多。\n【25-45s】换季敏感用它最稳。\n【45-60s】只上 2 小时 800 套，囤一套用半年，冲！',
     'messages', jsonb_build_array(jsonb_build_object('role','user','content','仿写护肤套装大促千川文案，满 399 减 100 + 丰厚赠品，限时 2 小时，算账式逼单，60 秒。'))
   ), ARRAY['诱惑型','护肤','大促','囤货'], TRUE),
  ('qianchuan-writer', '痛点型 · 减肥代餐阻糖不反弹', '反弹焦虑切入，主打餐后阻糖，避违规词',
   jsonb_build_object('name','慧敏','persona','韩国欧尼慧敏：亲和种草风、擅长共情式痛点',
     'product_info', E'餐后阻糖饮（白芸豆+L-阿拉伯糖）\n饱腹 4 小时，120 大卡\n高蛋白 15g + 膳食纤维 6g，0 蔗糖\n价格：15 袋 159，三盒 399（赠摇摇杯）\n合规：普通食品，不承诺具体减重斤数',
     'original_script', E'【0-5s】吃完火锅有负罪感对吧？\n【5-20s】我餐后来一袋阻糖饮，把碳水挡在门外。\n【20-40s】120 大卡顶饱 4 小时，高蛋白高纤维。\n【40-60s】三盒 399 送摇摇杯，吃大餐也不慌，冲！',
     'messages', jsonb_build_array(jsonb_build_object('role','user','content','仿写代餐阻糖饮千川文案，从"吃完大餐负罪感"切入，主打餐后阻糖+饱腹，不能承诺具体减重斤数，60 秒。'))
   ), ARRAY['痛点型','减肥','阻糖','大餐'], TRUE),
  ('qianchuan-writer', '场景型 · 低卡零食办公室解馋', '下午茶场景，主打低卡饱腹',
   jsonb_build_object('name','慧敏','persona','韩国欧尼慧敏：亲和种草风、擅长场景代入',
     'product_info', E'低卡高蛋白威化（12 根/盒）\n一根 95 大卡（≈半个苹果），蛋白 6g，0 蔗糖\n口味：海盐焦糖/抹茶红豆/巧克力\n场景：下午 3 点、健身加餐、加班抗饿\n价格：39.9/盒，三盒 99\n背书：0 防腐剂，孕妈可吃',
     'original_script', E'【0-5s】下午三点，办公室都想来点甜的？\n【5-20s】我抽屉常备这个低卡威化，一根 95 大卡。\n【20-40s】蛋白 6g 0 蔗糖，解馋没负担。\n【40-60s】三盒 99，囤一抽屉，冲！',
     'messages', jsonb_build_array(jsonb_build_object('role','user','content','仿写低卡零食千川文案，代入"下午三点办公室解馋"场景，主打一根 95 大卡+高蛋白，60 秒。'))
   ), ARRAY['场景型','零食','低卡','办公室'], TRUE),
  ('qianchuan-writer', '效果型 · 厨房重油污清洁剂', '效果对比，主打一擦净+环保',
   jsonb_build_object('name','慧敏','persona','韩国欧尼慧敏：亲和种草风、擅长视觉化效果演示',
     'product_info', E'厨房重油污清洁剂（500ml 喷雾）\n生物酶分解油污，一擦即净免拆洗\n适用：油烟机/灶台/瓷砖/玻璃\n安全：食品级配方，不伤手\n价格：29.9/瓶，两瓶 49.9（送海绵 3 块）',
     'original_script', E'【0-5s】看这个油烟机，脏到不想做饭了？\n【5-25s】喷一下生物酶清洁剂，30 秒一擦，跟新的一样，免拆洗。\n【25-45s】食品级，母婴厨房放心用。\n【45-60s】两瓶 49.9 送海绵，厨房焕新，冲！',
     'messages', jsonb_build_array(jsonb_build_object('role','user','content','仿写厨房油污清洁剂千川文案，"脏油烟机→一擦净"反差开头，主打生物酶免拆洗+食品级安全，60 秒。'))
   ), ARRAY['效果型','家居','去油','厨房'], TRUE)
) AS t(tool_code, name, description, input_payload, tags, is_active)
WHERE NOT EXISTS (SELECT 1 FROM eval_test_cases t2 WHERE t2.name = t.name);

-- ② 版本（3）—— 权重改 4 新维 + glm 配置
INSERT INTO eval_versions (tool_code, name, description, config_payload, parent_version_id, source_kol_id, auto_run_on_create, auto_run_tags, is_active, created_by)
SELECT 'qianchuan-writer', v.name, v.description,
       jsonb_build_object(
         'system_prompt_template', v.prompt,
         'model_id','k3','provider','kimi',
         'scoring_model_id','glm-4.6','scoring_provider','glm','scoring_adapter','yunwu',
         'dimension_weights', jsonb_build_object('hook_strength',0.35,'conversion_power',0.30,'structure_fidelity',0.20,'persona_consistency',0.15),
         'temperature',1,'max_tokens',900
       ),
       NULL, NULL, FALSE, ARRAY[]::text[], v.is_active, (SELECT id FROM users WHERE username='admin')
FROM (VALUES
  ('v1.2-痛点共鸣'::text, '基线：强调痛点共鸣钩子，转化引导偏弱'::text,
   E'你是千川脚本文案生成器，扮演达人【{{name}}】。\n\n人设档案：\n{{soul}}\n\n产品信息（以此为准，不得编造）：\n{{product_info}}\n\n参考原版结构：\n{{original_script}}\n\n要求：3 秒【痛点共鸣】开场；严格用上述产品信息；口语化、情绪起伏；60 秒；结尾给行动引导。\n\n对话：\n{{messages}}'::text, FALSE::boolean),
  ('v1.3-行动引导', '线上版：强化结尾 CTA + 稀缺感 + 价格机制三件套',
   E'你是千川脚本文案生成器，扮演达人【{{name}}】。\n\n人设档案：\n{{soul}}\n\n产品信息（以此为准）：\n{{product_info}}\n\n参考原版结构：\n{{original_script}}\n\n要求：3 秒【痛点共鸣】开场；结尾必含【行动引导+稀缺感+价格机制】三件套；60 秒。\n\n对话：\n{{messages}}', TRUE),
  ('v1.4-人设强化', '实验版：强化 persona 语言风格',
   E'你是千川脚本文案生成器，扮演达人【{{name}}】。\n\n人设档案（必须严守其口头禅、语气、价值观）：\n{{soul}}\n\n产品信息：\n{{product_info}}\n\n参考原版结构：\n{{original_script}}\n\n要求：全程用达人标志性口头禅；把卖点翻译成"这个达人会怎么说"；60 秒。\n\n对话：\n{{messages}}', FALSE)
) AS v(name, description, prompt, is_active)
WHERE NOT EXISTS (SELECT 1 FROM eval_versions v2 WHERE v2.name = v.name);
UPDATE eval_versions SET parent_version_id=(SELECT id FROM eval_versions WHERE name='v1.2-痛点共鸣') WHERE name='v1.3-行动引导';
UPDATE eval_versions SET parent_version_id=(SELECT id FROM eval_versions WHERE name='v1.3-行动引导') WHERE name='v1.4-人设强化';

-- ③ 定时策略（3）
INSERT INTO eval_schedule_policies (name, cron, version_id, filter_tags, is_active, created_by)
SELECT s.name, s.cron, (SELECT id FROM eval_versions WHERE name=s.vn), s.ft, s.ia, (SELECT id FROM users WHERE username='admin')
FROM (VALUES
  ('夜间全量回归'::text,'0 2 * * *'::text,'v1.3-行动引导'::text,ARRAY[]::text[],TRUE::boolean),
  ('每周一核心集回归','0 9 * * 1','v1.3-行动引导',ARRAY['美妆','护肤'],TRUE),
  ('美妆线每日回归','30 9 * * *','v1.4-人设强化',ARRAY['美妆','提亮'],FALSE)
) AS s(name,cron,vn,ft,ia)
WHERE NOT EXISTS (SELECT 1 FROM eval_schedule_policies s2 WHERE s2.name=s.name);

-- ④ 评委模型（4）
INSERT INTO eval_judge_models (model_id, provider, adapter, applicable_output_type, note, is_active, created_by)
SELECT t.m,t.p,t.a,t.ot,t.n,t.ia,(SELECT id FROM users WHERE username='admin')
FROM (VALUES
  ('glm-4-flash'::text,'yunwu'::text,'yunwu'::text,'copy'::text,'主力评委：快、稳、JSON 可靠'::text,TRUE::boolean),
  ('glm-4.5','yunwu','yunwu','copy','备选：推理强，适合高难度 case',TRUE),
  ('glm-4.6','yunwu','yunwu','copy','备选：推理强',FALSE),
  ('qwen-max','yunwu','yunwu','copy','交叉评委：异构防同源偏好',FALSE)
) AS t(m,p,a,ot,n,ia)
WHERE NOT EXISTS (SELECT 1 FROM eval_judge_models j WHERE j.model_id=t.m AND j.adapter=t.a);

-- ⑤ 2 条 demo run + 4 维评分（v1.2 基线 vs v1.3 线上，B 略好）
DO $$
DECLARE va bigint; vb bigint; sid bigint; ra bigint; rb bigint; cr bigint;
  bs decimal; bb decimal; tc RECORD; dm RECORD; r RECORD;
BEGIN
  SELECT id INTO va FROM eval_versions WHERE name='v1.2-痛点共鸣';
  SELECT id INTO vb FROM eval_versions WHERE name='v1.3-行动引导';
  SELECT id INTO sid FROM eval_strategies WHERE name='default';
  IF va IS NULL OR vb IS NULL OR sid IS NULL THEN RETURN; END IF;

  INSERT INTO eval_runs(version_id,strategy_id,name,trigger_type,status,filter_tags,total_cases,completed_cases,failed_cases,metadata,created_by,started_at,finished_at)
  VALUES(va,sid,'基线回归 · v1.2-痛点共鸣','manual','completed',ARRAY[]::text[],5,5,0,
    jsonb_build_object('resolved_scoring',jsonb_build_object('model_id','glm-4.6','provider','glm','adapter','yunwu')),
    (SELECT id FROM users WHERE username='admin'),NOW()-interval '3 hour',NOW()-interval '170 minute') RETURNING id INTO ra;
  INSERT INTO eval_runs(version_id,strategy_id,name,trigger_type,status,filter_tags,total_cases,completed_cases,failed_cases,metadata,created_by,started_at,finished_at)
  VALUES(vb,sid,'线上回归 · v1.3-行动引导','manual','completed',ARRAY[]::text[],5,5,0,
    jsonb_build_object('resolved_scoring',jsonb_build_object('model_id','glm-4.6','provider','glm','adapter','yunwu')),
    (SELECT id FROM users WHERE username='admin'),NOW()-interval '1 hour',NOW()-interval '50 minute') RETURNING id INTO rb;

  FOR tc IN SELECT id,name FROM eval_test_cases ORDER BY id LOOP
    FOR r IN SELECT rid,tag FROM (VALUES (ra,'A'),(rb,'B')) AS x(rid,tag) LOOP
      INSERT INTO eval_case_results(run_id,test_case_id,generated_output,output_payload)
      VALUES(r.rid,tc.id,'【'||CASE WHEN r.tag='A' THEN 'v1.2 基线' ELSE 'v1.3 线上' END||'】'||tc.name||' 仿写稿……（demo 示例文本）',
        jsonb_build_object('char_count',320,'model',CASE WHEN r.tag='A' THEN 'k3' ELSE 'k3' END)) RETURNING id INTO cr;
      FOR dm IN SELECT id,name FROM eval_dimensions WHERE tool_code='qianchuan-writer' ORDER BY id LOOP
        bs := CASE dm.name
          WHEN 'hook_strength'        THEN 6.4 + (tc.id % 3)*0.3
          WHEN 'conversion_power'    THEN 5.9 + (tc.id % 3)*0.3
          WHEN 'structure_fidelity'  THEN 7.0 + (tc.id % 2)*0.2
          WHEN 'persona_consistency' THEN 7.4 + (tc.id % 2)*0.2
        END;
        bb := bs + CASE dm.name WHEN 'conversion_power' THEN 0.9 WHEN 'hook_strength' THEN 0.6 ELSE 0.4 END;
        INSERT INTO eval_scores(case_result_id,dimension_id,weight_used,ai_score,ai_reasoning,ai_strengths,ai_weaknesses,human_score)
        VALUES(cr,dm.id,
          CASE dm.name WHEN 'hook_strength' THEN 0.35 WHEN 'conversion_power' THEN 0.30 WHEN 'structure_fidelity' THEN 0.20 ELSE 0.15 END,
          ROUND(CASE WHEN r.tag='A' THEN bs ELSE bb END,1),
          CASE dm.name
            WHEN 'hook_strength' THEN '开头钩子'||CASE WHEN r.tag='A' THEN '力度一般、铺垫偏多' ELSE '较强、痛点前置' END
            WHEN 'conversion_power' THEN CASE WHEN r.tag='A' THEN '结尾逼单弱、缺稀缺感' ELSE 'CTA 三件套齐全、转化驱动强' END
            WHEN 'structure_fidelity' THEN '骨架'||CASE WHEN r.tag='A' THEN '基本保留、个别段落自发挥' ELSE '贴合原版、实体替换自然' END
            WHEN 'persona_consistency' THEN CASE WHEN r.tag='A' THEN '整体像、个别句式偏书面' ELSE '口头禅与语气还原好' END
          END,
          CASE dm.name
            WHEN 'hook_strength' THEN ARRAY['痛点前置']
            WHEN 'conversion_power' THEN ARRAY[CASE WHEN r.tag='B' THEN 'CTA 三件套' ELSE '价格清楚' END]
            WHEN 'structure_fidelity' THEN ARRAY['贴合骨架']
            WHEN 'persona_consistency' THEN ARRAY['口语化']
          END,
          CASE dm.name
            WHEN 'hook_strength' THEN ARRAY[CASE WHEN r.tag='A' THEN '进入正题慢' ELSE '逼单略急' END]
            WHEN 'conversion_power' THEN ARRAY[CASE WHEN r.tag='A' THEN '缺稀缺感' ELSE '稍硬广' END]
            WHEN 'structure_fidelity' THEN ARRAY['中段微调']
            WHEN 'persona_consistency' THEN ARRAY[CASE WHEN r.tag='A' THEN '个别书面化' ELSE '口头禅重复' END]
          END,
          CASE WHEN tc.id=1 AND dm.name='hook_strength' AND r.tag='A' THEN 7.5 ELSE NULL END);
      END LOOP;
    END LOOP;
  END LOOP;
END $$;

SELECT 'test_cases' t,count(*) FROM eval_test_cases WHERE deleted_at IS NULL
UNION ALL SELECT 'versions',count(*) FROM eval_versions WHERE deleted_at IS NULL
UNION ALL SELECT 'schedules',count(*) FROM eval_schedule_policies WHERE deleted_at IS NULL
UNION ALL SELECT 'judge_models',count(*) FROM eval_judge_models WHERE deleted_at IS NULL
UNION ALL SELECT 'dimensions',count(*) FROM eval_dimensions
UNION ALL SELECT 'rubrics',count(*) FROM eval_rubrics
UNION ALL SELECT 'runs',count(*) FROM eval_runs
UNION ALL SELECT 'scores',count(*) FROM eval_scores;
