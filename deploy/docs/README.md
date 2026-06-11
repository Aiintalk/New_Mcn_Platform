# 运维文档目录

> 本目录存放运维相关的所有文档。部署运维时，不出 `deploy/` 目录即可找到全部所需内容。

---

## 部署架构

```
deploy/
├── scripts/                           # 运维脚本
│   ├── start.sh                       #   启动服务（后端 uvicorn + 前端 npm）
│   ├── stop.sh                        #   停止服务
│   ├── health-check.sh                #   健康检查
│   └── init-db.sh                     #   数据库初始化
├── nginx/
│   └── mcn-m1.conf                    #   Nginx 反向代理配置
├── sql/
│   └── .gitkeep                       #   SQL 脚本占位
├── logs/                              # 运行时日志
│   └── backend.log
├── pids/                              # 进程 PID 文件
│
├── docs/                              # ===== 本目录 =====
│   ├── README.md                      #   本文件（架构 + 文档索引）
│   └── tasks/                         #   任务单 + 验收文档（6 个）
│       ├── M1_Sprint0.md              #     基础环境搭建
│       ├── M1_Sprint1.md              #     用户模块部署
│       ├── M1_Sprint4.md              #     AI 模块部署
│       ├── M1_Sprint5_TikHub_独立池化.md #  TikHub 独立池化部署
│       ├── M2_Sprint1_kol_intake.md   #     入驻问卷部署
│       └── M2_测试服首次部署.md         #     测试服首次部署
│
└── README.md                          # 部署说明
```

### 环境要求

| 组件 | 版本 |
|------|------|
| OS | Ubuntu 22.04+ |
| Python | 3.10+ |
| Node.js | 18+ |
| PostgreSQL | 15+ |
| Nginx | 1.24+ |
| PM2 | 最新 |

### 服务清单

| 服务 | 端口 | 启动方式 |
|------|------|----------|
| 后端 API | 8000 | uvicorn app.main:app |
| 前端静态 | 3000 | npm run dev / nginx 静态托管 |
| PostgreSQL | 5432 | systemd |
| Nginx | 80 / 443 | systemd |

---

## 文档存储结构

```
deploy/docs/
└── tasks/       任务单 + 验收文档
                 → 新功能部署、环境变更都放这里
                 → 迭代按 vN 递增新建，不覆盖原文档
                 → 验收文档与任务单同目录，文件名带「开发验收」
```

### 命名规范

```
任务文档：    Mx_Sprintxx_{功能名}[_vN[_迭代类型]]
验收文档：    Mx_Sprintxx_运维端任务_开发验收_{功能名}_vN.md
```

- **迭代类型**（v2 起）：`新增功能` / `修改需求` / `修复Bug`
- **版本号**：一条线累加（v1 → v2 → v3），不重复

---

## 关键约定

- 数据库初始化：`bash backend/scripts/init_db.sh`（默认 postgres/admin123/mcn_m1）
- 健康检查：`bash deploy/scripts/health-check.sh`
- 日志轮转：确认 logs/ 不写满磁盘
- 端口安全：仅开放 80/443，5432 不对外暴露
- 环境变量：`.env` 文件管理，不硬编码到配置中
