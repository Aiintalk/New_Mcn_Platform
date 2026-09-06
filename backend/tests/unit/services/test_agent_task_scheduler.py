"""内容分析自动调度启动边界。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.agent_task_scheduler import _due_task_times, start_content_analysis_scheduler


SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_disabled_scheduler_does_not_create_background_work(monkeypatch):
    def unexpected_create_task(*args, **kwargs):
        raise AssertionError("关闭状态不应创建后台任务")

    monkeypatch.setattr("app.services.agent_task_scheduler.asyncio.create_task", unexpected_create_task)

    assert start_content_analysis_scheduler(enabled=False, executor=None) is None


def test_enabled_scheduler_rejects_invalid_executor_without_background_work(monkeypatch):
    def unexpected_create_task(*args, **kwargs):
        raise AssertionError("错误执行器不应创建后台任务")

    monkeypatch.setattr("app.services.agent_task_scheduler.asyncio.create_task", unexpected_create_task)

    assert start_content_analysis_scheduler(enabled=True, executor=object()) is None


def test_due_scan_catches_daily_midnight_skipped_by_a_slow_loop():
    due = _due_task_times(datetime(2026, 9, 8, 0, 1, tzinfo=SHANGHAI))

    assert datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI) in due


def test_due_scan_catches_weekly_one_oclock_after_the_minute_was_skipped():
    due = _due_task_times(datetime(2026, 9, 7, 1, 1, tzinfo=SHANGHAI))

    assert datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI) in due


def test_due_scan_after_process_start_returns_one_latest_daily_and_weekly_instant():
    now = datetime(2026, 9, 9, 12, 34, 56, tzinfo=SHANGHAI)

    first = _due_task_times(now)
    repeated = _due_task_times(now)

    assert first == repeated == (
        datetime(2026, 9, 9, 0, 0, tzinfo=SHANGHAI),
        datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
    )
