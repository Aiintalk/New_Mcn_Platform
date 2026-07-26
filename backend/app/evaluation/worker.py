"""
app/evaluation/worker.py

评测模块异步运行 worker（方案 C：arq + Redis，计划 docs/superpowers/plans/2026-07-26-async-run-architecture.md）。

【隔离设计 — 重要】
- Redis 仅评测模块使用，工程其它部分不依赖。本文件 + arq/redis 依赖全部限定在评测模块内。
- 将来评测工程独立部署时，连同 Redis 一起迁出（start_redis.sh 起的 mcn-redis 容器随迁），
  不影响主工程。
- REDIS_URL 从环境变量读（默认 redis://localhost:6379/0），**不进全局 config.py**，
  避免与主工程配置耦合。

【运行 worker】（独立进程，PM2 管理；与 web 进程分离）
    cd backend && source 到 miniforge env
    REDIS_URL=redis://localhost:6379/0 arq app.evaluation.worker.WorkerSettings

【阶段】
- Phase 1（本文件）：基建 + ping 冒烟任务。
- Phase 3：functions 增加 eval_case_job（真实 case 执行：generate + 多维 score）。
"""
import os
from urllib.parse import urlparse

from arq.connections import RedisSettings


def eval_redis_settings() -> RedisSettings:
    """从 REDIS_URL 解析 arq RedisSettings（评测专用，隔离于全局 config）。

    支持标准 redis://[user[:pass]@]host[:port][/db] 形式。
    """
    url = urlparse(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return RedisSettings(
        host=url.hostname or "localhost",
        port=url.port or 6379,
        password=url.password,
        database=int((url.path or "/0").lstrip("/") or "0"),
    )


async def ping(ctx, name: str = "world") -> str:
    """冒烟任务（Phase 1）。Phase 3 起由 eval_case_job 替换为真实 case 执行。"""
    return f"pong: {name}"


class WorkerSettings:
    """arq worker 配置。

    运行：``arq app.evaluation.worker.WorkerSettings``
    一期并发上限 max_jobs=2（已确认；glm 1 条 key=5，留余量）。
    """
    functions = [ping]
    redis_settings = eval_redis_settings()
    max_jobs = 2          # 一期并发上限（凭证池限流）
    job_timeout = 600     # 单 job 上限 10 分钟（单 case：1 生成 + 4 维评分）
    max_tries = 3         # 失败重试次数
