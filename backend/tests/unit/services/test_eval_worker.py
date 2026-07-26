"""
app/evaluation/worker.py 单测（Phase 1：redis 配置解析 + ping 冒烟任务）。

注：真实 enqueue→worker 消费的全链路冒烟已手动验证（见 plan Phase 1）；
本文件固化"REDIS_URL 解析正确 + ping 行为正确"，不依赖 redis 在线。
"""
import pytest

from app.evaluation.worker import WorkerSettings, eval_redis_settings, ping


def test_redis_settings_default(monkeypatch):
    """无 REDIS_URL → 默认 localhost:6379/0。"""
    monkeypatch.delenv("REDIS_URL", raising=False)
    s = eval_redis_settings()
    assert s.host == "localhost"
    assert s.port == 6379
    assert s.database == 0
    assert s.password is None


def test_redis_settings_full_url(monkeypatch):
    """带密码/自定义 host:port/db 的 REDIS_URL 正确解析。"""
    monkeypatch.setenv("REDIS_URL", "redis://:secret@redis-host:6380/2")
    s = eval_redis_settings()
    assert s.host == "redis-host"
    assert s.port == 6380
    assert s.database == 2
    assert s.password == "secret"


async def test_ping_returns_argument():
    """ping 冒烟任务原样回显。"""
    assert await ping({}, "eval-smoke") == "pong: eval-smoke"
    assert await ping({}) == "pong: world"


def test_worker_settings_basics():
    """WorkerSettings 关键配置：注册 ping、并发上限=2、重试=3。"""
    assert ping in WorkerSettings.functions
    assert WorkerSettings.max_jobs == 2      # 一期并发上限（已确认）
    assert WorkerSettings.max_tries == 3
    assert WorkerSettings.job_timeout == 600
