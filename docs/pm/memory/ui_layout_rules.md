---
name: ui_layout_rules
description: 运营端和管理端功能入口的统一布局规范，决定新功能放在哪个菜单下
type: feedback
updated: 2026-06-10
---

## 运营端

**所有新增功能入口统一放入「创作中心」**，不单独新增顶级菜单项。

## 管理端

**所有新增功能的配置统一放入「工具配置」→「功能配置」**，不新建独立配置页面。

每个功能卡片内可包含：
- AI 模型选择（绑定对应 config_key 的 ai_model_id）
- Prompt 配置（绑定对应 config_key 的 system_prompt）
- 保存按钮

**Why:** 用户明确规定了全局导航架构，避免各 Sprint 各自添加顶级菜单导致导航混乱。

**How to apply:** 每次写前端任务单时，路由/导航部分按此规范写，不要让前端自行判断放哪里。
