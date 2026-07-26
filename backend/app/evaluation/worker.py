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

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.evaluation.constants import (
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_TERMINAL,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
)


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
    """冒烟任务（Phase 1）。"""
    return f"pong: {name}"


_pool: ArqRedis | None = None


async def get_eval_pool() -> ArqRedis:
    """共享 redis pool（懒加载，进程级复用；避免 trigger_run 里 N 个 case 建销毁 N 个连接池）。"""
    global _pool
    if _pool is None:
        _pool = await create_pool(eval_redis_settings())
    return _pool


async def enqueue_case_job(job_id: int) -> str | None:
    """把一个 case-job 入队（arq）。复用共享 pool。

    传 `_job_id=f"eval_case:{job_id}"`：arq 在 result_timeout 窗口内对同一 _job_id 去重
    （重复入队返回 None）——recover 重投 / enqueue 重试时不会产生重复 task。
    """
    pool = await get_eval_pool()
    job = await pool.enqueue_job("eval_case_job", job_id, _job_id=f"eval_case:{job_id}")
    return job.job_id if job else None


# job 卡死（running 但 worker 已不存活）的判定阈值：与 WorkerSettings.job_timeout 对齐
_STALE_RUNNING_SECS = 600


async def recover_pending_jobs(db: AsyncSession) -> int:
    """重启恢复（migration 054 注释承诺的机制）：

    1. 把卡死的 running job（started_at 超过 _STALE_RUNNING_SECS，worker 已不存活）
       重置回 pending；
    2. 把所有 pending job 重新入队（arq 按 _job_id 去重，已在队列的不会重复）。

    worker 启动时调（WorkerSettings.on_startup）。返回尝试重新入队的条数
    （被 arq 去重返回 None 的也计入）。
    """
    # 1. 卡死 running → pending（int * interval 合法；避免 int||text 报错）
    await db.execute(
        text(
            "UPDATE eval_case_jobs SET status = 'pending', started_at = NULL "
            "WHERE status = 'running' AND started_at < NOW() - (:secs * INTERVAL '1 second')"
        ),
        {"secs": _STALE_RUNNING_SECS},
    )
    await db.commit()
    # 2. 重投所有 pending（arq 去重）
    rows = (
        await db.execute(
            text("SELECT id FROM eval_case_jobs WHERE status = 'pending' ORDER BY id")
        )
    ).fetchall()
    n = 0
    for (jid,) in rows:
        await enqueue_case_job(jid)
        n += 1
    return n


async def _on_startup(ctx) -> None:
    """arq worker 启动钩子：恢复未入队/卡死的 pending job（重启补偿）。"""
    async with AsyncSessionLocal() as db:
        await recover_pending_jobs(db)


# ---------------------------------------------------------------------------
# case-job 执行 + run 聚合（逻辑函数化，便于单测注入 db；arq task 薄包一层）
# ---------------------------------------------------------------------------

async def aggregate_run_progress(db: AsyncSession, run_id: int, success: bool) -> None:
    """原子累加 run 的完成/失败计数；全部 case 终态则收尾 run。

    用原子 UPDATE（非 ORM +=）避免多 worker 并发竞争计数。
    全部 failed（completed=0）→ run failed；否则 completed（部分失败仍 completed，spec §6.5）。
    """
    if success:
        await db.execute(
            text("UPDATE eval_runs SET completed_cases = completed_cases + 1 WHERE id = :id"),
            {"id": run_id},
        )
    else:
        await db.execute(
            text("UPDATE eval_runs SET failed_cases = failed_cases + 1 WHERE id = :id"),
            {"id": run_id},
        )
    row = (
        await db.execute(
            text(
                "SELECT total_cases, completed_cases, failed_cases "
                "FROM eval_runs WHERE id = :id"
            ),
            {"id": run_id},
        )
    ).fetchone()
    if row and row[0] > 0 and (row[1] + row[2]) >= row[0]:
        status = RUN_STATUS_FAILED if row[1] == 0 else RUN_STATUS_COMPLETED
        await db.execute(
            text("UPDATE eval_runs SET status = :s, finished_at = NOW() WHERE id = :id"),
            {"s": status, "id": run_id},
        )
    await db.commit()


async def run_case_job_logic(
    db: AsyncSession, job_id: int, *, execute=None
) -> str:
    """单个 case-job 的执行逻辑（db 注入，便于单测）。

    - 幂等：job 已终态（done/failed/cancelled）则跳过，防 arq 重试导致 run 计数 over-counting。
    - 失败必收尾：执行抛错 → job→failed + aggregate(success=False) + re-raise（让 arq 重试/记录），
      保证 run 的 failed_cases 累加、run 最终能收尾（不卡 pending）。

    Phase 2（本实现）：stub —— 仅推进状态 + 聚合，不做真实 generate/score。
    Phase 3：在「STUB」处插入真实执行（generate → 多维 score → 写 case_result+scores）。
    """
    # 幂等守卫：已终态则跳过（防重试 over-counting）
    cur_status = (
        await db.execute(text("SELECT status FROM eval_case_jobs WHERE id = :id"), {"id": job_id})
    ).scalar()
    if cur_status in JOB_STATUS_TERMINAL:
        return f"job {job_id} already terminal ({cur_status}), skip"

    run_id = (
        await db.execute(text("SELECT run_id FROM eval_case_jobs WHERE id = :id"), {"id": job_id})
    ).scalar()
    if run_id is None:
        raise RuntimeError(f"eval_case_job: job {job_id} not found (no run_id)")

    # job → running，attempts+1
    await db.execute(
        text(
            "UPDATE eval_case_jobs SET status = :s, started_at = NOW(), "
            "attempts = attempts + 1 WHERE id = :id"
        ),
        {"s": JOB_STATUS_RUNNING, "id": job_id},
    )
    await db.commit()

    success = True
    err: Exception | None = None
    try:
        if execute is None:
            # ── STUB（Phase 2）：仅标记 done。Phase 3 传 execute 做真实 generate+score。 ──
            await db.execute(
                text("UPDATE eval_case_jobs SET status = :s, finished_at = NOW() WHERE id = :id"),
                {"s": JOB_STATUS_DONE, "id": job_id},
            )
            await db.commit()
        else:
            # 注入执行（测试失败路径 / Phase 3 真实执行）
            await execute(db, job_id)
    except Exception as exc:  # noqa: BLE001 —— case 级失败需捕获以保证 run 收尾
        success = False
        err = exc
        await db.rollback()
        await db.execute(
            text(
                "UPDATE eval_case_jobs SET status = :s, finished_at = NOW(), "
                "last_error = :err WHERE id = :id"
            ),
            {"s": JOB_STATUS_FAILED, "err": str(exc)[:500], "id": job_id},
        )
        await db.commit()

    # 无论成败都聚合（保证 run 收尾）；幂等守卫已防重试 over-counting
    await aggregate_run_progress(db, run_id, success=success)

    if not success:
        assert err is not None
        raise err  # 让 arq 记录失败（重试时幂等守卫会跳过，不再 over-count）
    return f"job {job_id} done (stub)"


async def eval_case_job(ctx, job_id: int) -> str:
    """arq 任务入口：开独立 session 调 run_case_job_logic（worker 进程消费）。"""
    async with AsyncSessionLocal() as db:
        return await run_case_job_logic(db, job_id)


class WorkerSettings:
    """arq worker 配置。

    运行：``arq app.evaluation.worker.WorkerSettings``
    一期并发上限 max_jobs=2（已确认；glm 1 条 key=5，留余量）。
    """
    functions = [ping, eval_case_job]
    redis_settings = eval_redis_settings()
    on_startup = _on_startup   # 启动时恢复未入队/卡死的 pending job（重启补偿）
    max_jobs = 2          # 一期并发上限（凭证池限流）
    job_timeout = 600     # 单 job 上限 10 分钟（单 case：1 生成 + 4 维评分）
    max_tries = 3         # 失败重试次数
