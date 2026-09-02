"""内容分析阶段一的无副作用确定性计算。"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from statistics import median
from typing import Iterable
from zoneinfo import ZoneInfo

from .domain import AnalysisWindows, BasicAnalysis, ContentCategory, ContentRecord, LikeBaseline


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} 必须带时区")


def _half_open_window(start: datetime, end: datetime) -> None:
    _require_timezone(start, "start")
    _require_timezone(end, "end")
    if start >= end:
        raise ValueError("时间窗口的开始必须早于结束")


def derive_windows(run_at: datetime) -> AnalysisWindows:
    """按中国时区计算刚结束的报告日、3 日和 30 日完整自然日。"""
    _require_timezone(run_at, "run_at")
    local_run_at = run_at.astimezone(CHINA_TIMEZONE)
    report_date = local_run_at.date() - timedelta(days=1)
    report_end = datetime.combine(
        report_date + timedelta(days=1), time.min, tzinfo=CHINA_TIMEZONE
    )
    return AnalysisWindows(
        report_date=report_date,
        three_day_start=report_end - timedelta(days=3),
        three_day_end=report_end,
        thirty_day_start=report_end - timedelta(days=30),
        thirty_day_end=report_end,
    )


def deduplicate_contents(contents: Iterable[ContentRecord]) -> list[ContentRecord]:
    """仅凭稳定作品编号或外部链接合并，并保留最新采集记录。"""
    records = list(contents)
    parents = list(range(len(records)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    seen_keys: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        for key in record.identity.stable_keys():
            previous = seen_keys.get(key)
            if previous is not None:
                union(previous, index)
            seen_keys[key] = index

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        grouped[find(index)].append(index)

    result: list[ContentRecord] = []
    for indices in sorted(grouped.values(), key=lambda values: values[0]):
        newest_index = max(indices, key=lambda index: (records[index].captured_at, index))
        result.append(records[newest_index])
    return result


def persona_like_baseline(
    contents: Iterable[BasicAnalysis], start: datetime, end: datetime
) -> dict[str, LikeBaseline]:
    """统计半开区间内每个账号已分析人设内容的点赞基线。"""
    _half_open_window(start, end)
    likes_by_account: dict[str, list[int]] = defaultdict(list)
    for analysis in contents:
        record = analysis.content
        if (
            analysis.category == ContentCategory.PERSONA
            and start <= record.published_at < end
            and record.metrics.like_count is not None
        ):
            likes_by_account[record.account_id].append(record.metrics.like_count)

    return {
        account_id: LikeBaseline(
            mean=sum(likes) / len(likes),
            median=median(likes),
            sample_size=len(likes),
            maximum=max(likes),
            minimum=min(likes),
        )
        for account_id, likes in likes_by_account.items()
    }


def qianchuan_top_three(
    contents: Iterable[BasicAnalysis], start: datetime, end: datetime
) -> dict[str, tuple[ContentRecord, ...]]:
    """按当前点赞值选出半开区间内每账号的已分析千川内容前三条。"""
    _half_open_window(start, end)
    records_by_account: dict[str, list[ContentRecord]] = defaultdict(list)
    for analysis in contents:
        record = analysis.content
        if (
            analysis.category == ContentCategory.QIANCHUAN
            and start <= record.published_at < end
        ):
            records_by_account[record.account_id].append(record)

    return {
        account_id: tuple(
            sorted(
                records,
                key=lambda record: (
                    record.metrics.like_count is not None,
                    record.metrics.like_count if record.metrics.like_count is not None else -1,
                ),
                reverse=True,
            )[:3]
        )
        for account_id, records in records_by_account.items()
    }


def normalize_play_count(play_count: int | None) -> int | None:
    """将零值或负值播放量标准化为不可用值。"""
    if play_count is None or play_count <= 0:
        return None
    return play_count
