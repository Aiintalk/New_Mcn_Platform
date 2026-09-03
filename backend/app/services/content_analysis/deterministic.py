"""内容分析阶段一的无副作用确定性计算。"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from statistics import median
from typing import Iterable
from zoneinfo import ZoneInfo

from .domain import (
    AnalysisWindows,
    BasicAnalysis,
    ContentCategory,
    ContentRecord,
    DataMaturity,
    LikeBaseline,
    WeeklyPersonaBaseline,
)


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
                if records[previous].account_id != record.account_id:
                    kind, value = key
                    raise ValueError(
                        f"稳定内容身份 {kind}:{value} 关联了多个账号"
                    )
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
            and record.metrics.like_count is not None
        ):
            records_by_account[record.account_id].append(record)

    return {
        account_id: tuple(
            sorted(
                records,
                key=_qianchuan_rank_key,
            )[:3]
        )
        for account_id, records in records_by_account.items()
    }


def derive_data_maturity(
    published_at: datetime,
    captured_at: datetime,
) -> DataMaturity:
    """只按发布时间到本次采集时间的年龄计算确定性成熟度。"""
    _require_timezone(published_at, "published_at")
    _require_timezone(captured_at, "captured_at")
    age = captured_at - published_at
    if age < timedelta(0):
        raise ValueError("采集时间不能早于发布时间")
    if age < timedelta(hours=6):
        return DataMaturity.EARLY
    if age < timedelta(hours=12):
        return DataMaturity.INITIAL
    return DataMaturity.QUALITATIVE


def build_weekly_persona_baselines(
    contents: Iterable[BasicAnalysis],
    run_at: datetime,
) -> tuple[WeeklyPersonaBaseline, ...]:
    """独立计算周度 30 日人设点赞基准，不触发日报或智能分析。"""
    windows = derive_windows(run_at)
    remaining = list(contents)
    selected: list[BasicAnalysis] = []
    for record in deduplicate_contents(item.content for item in remaining):
        match_index = next(
            index
            for index, analysis in enumerate(remaining)
            if analysis.content == record
        )
        selected.append(remaining.pop(match_index))
    baselines = persona_like_baseline(
        selected,
        windows.thirty_day_start,
        windows.thirty_day_end,
    )
    return tuple(
        WeeklyPersonaBaseline(
            account_id=account_id,
            window_start=windows.thirty_day_start,
            window_end=windows.thirty_day_end,
            baseline=baseline,
        )
        for account_id, baseline in sorted(baselines.items())
    )


def _qianchuan_rank_key(record: ContentRecord) -> tuple[object, ...]:
    """点赞同分时仍只使用内容自身字段给出稳定次序。"""
    likes = record.metrics.like_count
    identity = record.identity
    return (
        likes is None,
        -(likes or 0),
        -record.published_at.timestamp(),
        not bool(identity.platform_content_id),
        identity.platform_content_id or "",
        not bool(identity.external_url),
        identity.external_url or "",
        -record.captured_at.timestamp(),
        record.source.value,
        record.transcript or "",
        record.video_reference or "",
        record.metrics.comment_count is None,
        -(record.metrics.comment_count or 0),
        record.metrics.share_count is None,
        -(record.metrics.share_count or 0),
        record.metrics.favorite_count is None,
        -(record.metrics.favorite_count or 0),
        record.sync_status.value,
    )


def normalize_play_count(play_count: int | None) -> int | None:
    """将零值或负值播放量标准化为不可用值。"""
    if play_count is None or play_count <= 0:
        return None
    return play_count
