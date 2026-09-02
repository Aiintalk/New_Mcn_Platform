"""内容分析阶段一的稳定业务语义，不包含存储、路由或外部调用。"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class ContentSource(str, Enum):
    """标准输入的内容来源。"""

    MANUAL = "manual"
    CONTENT_LIBRARY = "content_library"
    PLATFORM_SYNC = "platform_sync"


class ContentCategory(str, Enum):
    """阶段一确认的三种内容主分类。"""

    PERSONA = "persona"
    QIANCHUAN = "qianchuan"
    OTHER = "other"


class SyncStatus(str, Enum):
    """内容同步的当前状态。"""

    PENDING = "pending"
    SYNCED = "synced"
    PARTIAL = "partial"
    FAILED = "failed"


class ConfidenceLevel(str, Enum):
    """分析结论的可信程度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class OpeningTagStatus(str, Enum):
    """开头标注的处理状态。"""

    NOT_EVALUATED = "not_evaluated"
    TAGGED = "tagged"
    UNTAGGED = "untagged"


class BusinessStatus(str, Enum):
    """项目或候选内容的业务状态。"""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} 必须带时区")


@dataclass(frozen=True)
class ContentIdentity:
    """平台作品编号和外部链接组成的稳定内容身份。"""

    platform_content_id: str | None = None
    external_url: str | None = None

    def stable_keys(self) -> tuple[tuple[str, str], ...]:
        keys: list[tuple[str, str]] = []
        if self.platform_content_id:
            keys.append(("platform_content_id", self.platform_content_id))
        if self.external_url:
            keys.append(("external_url", self.external_url))
        return tuple(keys)


@dataclass(frozen=True)
class EngagementMetrics:
    """最新互动值；缺失值保持 None，不使用零值替代。"""

    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    favorite_count: int | None = None
    play_count: int | None = None

    def __post_init__(self) -> None:
        if self.play_count is not None and self.play_count <= 0:
            object.__setattr__(self, "play_count", None)

    @property
    def engagement_total(self) -> int:
        """互动合计仅包括点赞、评论、分享和收藏。"""
        return sum(
            value or 0
            for value in (
                self.like_count,
                self.comment_count,
                self.share_count,
                self.favorite_count,
            )
        )


@dataclass(frozen=True)
class ContentRecord:
    """标准化后的单条内容输入。"""

    account_id: str
    source: ContentSource
    identity: ContentIdentity
    category: ContentCategory
    published_at: datetime
    captured_at: datetime
    metrics: EngagementMetrics
    transcript: str | None = None
    video_reference: str | None = None
    sync_status: SyncStatus = SyncStatus.PENDING

    def __post_init__(self) -> None:
        _require_timezone(self.published_at, "published_at")
        _require_timezone(self.captured_at, "captured_at")


@dataclass(frozen=True)
class ProjectAccountRelation:
    """项目与账号的归属关系。"""

    project_id: str
    account_id: str
    context_version: str


@dataclass(frozen=True)
class ProjectContextVersion:
    """可追溯的项目上下文版本。"""

    project_id: str
    version: str
    effective_at: datetime

    def __post_init__(self) -> None:
        _require_timezone(self.effective_at, "effective_at")


@dataclass(frozen=True)
class AnalysisWindows:
    """中国时区的报告日及完整自然日半开区间。"""

    report_date: date
    three_day_start: datetime
    three_day_end: datetime
    thirty_day_start: datetime
    thirty_day_end: datetime


@dataclass(frozen=True)
class LikeBaseline:
    """账号在人设内容中的 30 日点赞基线。"""

    mean: float
    median: float
    sample_size: int
    maximum: int
    minimum: int


@dataclass(frozen=True)
class BasicAnalysis:
    """供下一阶段填充的基础内容分析。"""

    content: ContentRecord
    confidence: ConfidenceLevel
    opening_tag_status: OpeningTagStatus
    summary: str | None = None


@dataclass(frozen=True)
class ProjectJudgment:
    """供下一阶段输出的项目判断。"""

    project_id: str
    status: BusinessStatus
    confidence: ConfidenceLevel
    conclusion: str


@dataclass(frozen=True)
class ContentStatistics:
    """供项目统计和日报复用的确定性统计结果。"""

    account_id: str
    period_start: datetime
    period_end: datetime
    content_count: int
    engagement_total: int

    def __post_init__(self) -> None:
        _require_timezone(self.period_start, "period_start")
        _require_timezone(self.period_end, "period_end")


@dataclass(frozen=True)
class DailyReport:
    """日报的领域对象，内容由后续引擎生成。"""

    project_id: str
    report_date: date
    generated_at: datetime
    judgments: tuple[ProjectJudgment, ...]

    def __post_init__(self) -> None:
        _require_timezone(self.generated_at, "generated_at")


@dataclass(frozen=True)
class ContentCandidate:
    """供后续候选筛选使用的内容及其业务状态。"""

    content: ContentRecord
    status: BusinessStatus
    confidence: ConfidenceLevel
    reason: str | None = None
