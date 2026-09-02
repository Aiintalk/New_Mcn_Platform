"""阶段一确定性内容分析规则的测试。"""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.content_analysis.deterministic import (
    deduplicate_contents,
    derive_windows,
    normalize_play_count,
    persona_like_baseline,
    qianchuan_top_three,
)
from app.services.content_analysis.domain import (
    ContentCategory,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    SyncStatus,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures/content_analysis/phase1_anonymized.json"
)


def content(
    *,
    account_id: str = "account-001",
    category: ContentCategory = ContentCategory.PERSONA,
    platform_content_id: str | None = None,
    external_url: str | None = None,
    published_at: datetime = datetime(2026, 9, 1, 8, tzinfo=SHANGHAI),
    captured_at: datetime = datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
    likes: int | None = 10,
    play_count: int | None = 100,
    transcript: str | None = "合成短文案",
) -> ContentRecord:
    """创建仅用于断言领域规则的合成内容。"""
    return ContentRecord(
        account_id=account_id,
        source=ContentSource.MANUAL,
        identity=ContentIdentity(
            platform_content_id=platform_content_id,
            external_url=external_url,
        ),
        category=category,
        published_at=published_at,
        captured_at=captured_at,
        metrics=EngagementMetrics(
            like_count=likes,
            comment_count=2,
            share_count=3,
            favorite_count=4,
            play_count=play_count,
        ),
        transcript=transcript,
        sync_status=SyncStatus.SYNCED,
    )


def test_derive_windows_converts_to_china_timezone_and_uses_completed_days() -> None:
    run_at = datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc)

    windows = derive_windows(run_at)

    assert windows.report_date.isoformat() == "2026-09-03"
    assert windows.three_day_start == datetime(2026, 9, 1, tzinfo=SHANGHAI)
    assert windows.three_day_end == datetime(2026, 9, 4, tzinfo=SHANGHAI)
    assert windows.thirty_day_start == datetime(2026, 8, 5, tzinfo=SHANGHAI)
    assert windows.thirty_day_end == datetime(2026, 9, 4, tzinfo=SHANGHAI)


def test_derive_windows_changes_report_date_at_china_day_boundary() -> None:
    before_midnight = derive_windows(datetime(2026, 9, 3, 15, 59, tzinfo=timezone.utc))
    at_midnight = derive_windows(datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc))

    assert before_midnight.report_date.isoformat() == "2026-09-02"
    assert at_midnight.report_date.isoformat() == "2026-09-03"


def test_deduplicate_contents_keeps_newest_capture_for_platform_id_or_link() -> None:
    older_id = content(
        platform_content_id="sample-work-001",
        captured_at=datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
        likes=10,
    )
    newer_id = content(
        platform_content_id="sample-work-001",
        captured_at=datetime(2026, 9, 2, 9, tzinfo=SHANGHAI),
        likes=20,
    )
    older_link = content(
        platform_content_id="sample-work-002",
        external_url="https://example.invalid/video/sample-002",
        captured_at=datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
        likes=30,
    )
    newer_link = content(
        platform_content_id="sample-work-003",
        external_url="https://example.invalid/video/sample-002",
        captured_at=datetime(2026, 9, 2, 10, tzinfo=SHANGHAI),
        likes=40,
    )

    result = deduplicate_contents([older_id, newer_id, older_link, newer_link])

    assert [item.metrics.like_count for item in result] == [20, 40]


def test_deduplicate_contents_does_not_merge_text_when_stable_identity_is_missing() -> None:
    first = content(platform_content_id=None, external_url=None, transcript="相同合成文案")
    second = content(
        platform_content_id=None,
        external_url=None,
        transcript="相同合成文案",
        captured_at=datetime(2026, 9, 2, 9, tzinfo=SHANGHAI),
    )

    result = deduplicate_contents([first, second])

    assert result == [first, second]


def test_normalized_input_marks_non_positive_play_count_unavailable_and_excludes_it_from_engagement() -> None:
    item = content(play_count=0)

    assert item.metrics.play_count is None
    assert item.metrics.engagement_total == 19
    assert normalize_play_count(0) is None
    assert normalize_play_count(-1) is None
    assert normalize_play_count(101) == 101


def test_persona_like_baseline_uses_only_thirty_day_persona_contents_with_likes() -> None:
    window_start = datetime(2026, 8, 5, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        content(likes=10, published_at=datetime(2026, 8, 5, tzinfo=SHANGHAI)),
        content(likes=20, published_at=datetime(2026, 8, 10, tzinfo=SHANGHAI)),
        content(likes=40, published_at=datetime(2026, 9, 3, 23, tzinfo=SHANGHAI)),
        content(likes=None, published_at=datetime(2026, 8, 12, tzinfo=SHANGHAI)),
        content(
            category=ContentCategory.QIANCHUAN,
            likes=99,
            published_at=datetime(2026, 8, 12, tzinfo=SHANGHAI),
        ),
        content(likes=88, published_at=datetime(2026, 9, 4, tzinfo=SHANGHAI)),
    ]

    baseline = persona_like_baseline(records, window_start, window_end)

    assert baseline["account-001"].mean == 70 / 3
    assert baseline["account-001"].median == 20
    assert baseline["account-001"].sample_size == 3
    assert baseline["account-001"].maximum == 40
    assert baseline["account-001"].minimum == 10


def test_qianchuan_top_three_uses_current_likes_and_excludes_fourth_and_outside_window() -> None:
    window_start = datetime(2026, 9, 1, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        content(category=ContentCategory.QIANCHUAN, platform_content_id="sample-q1", likes=30),
        content(category=ContentCategory.QIANCHUAN, platform_content_id="sample-q2", likes=90),
        content(category=ContentCategory.QIANCHUAN, platform_content_id="sample-q3", likes=60),
        content(category=ContentCategory.QIANCHUAN, platform_content_id="sample-q4", likes=20),
        content(
            category=ContentCategory.QIANCHUAN,
            platform_content_id="sample-outside",
            likes=999,
            published_at=datetime(2026, 9, 4, tzinfo=SHANGHAI),
        ),
    ]

    top_three = qianchuan_top_three(records, window_start, window_end)

    assert [item.identity.platform_content_id for item in top_three["account-001"]] == [
        "sample-q2",
        "sample-q3",
        "sample-q1",
    ]


def test_phase1_fixture_is_small_anonymous_and_contains_no_long_transcript_or_local_path() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    contents = fixture["contents"]

    assert 1 <= len(contents) <= 10
    assert all(item["account_id"].startswith("account-") for item in contents)
    assert all(
        item["identity"].get("platform_content_id", "").startswith("sample-")
        for item in contents
    )
    assert all(len(item.get("transcript") or "") <= 120 for item in contents)
    assert "/Users/" not in FIXTURE_PATH.read_text(encoding="utf-8")
    assert "C:\\" not in FIXTURE_PATH.read_text(encoding="utf-8")
