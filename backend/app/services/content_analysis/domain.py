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
    """基础分析产出的三种内容主分类。"""

    PERSONA = "persona"
    QIANCHUAN = "qianchuan"
    UNDETERMINED = "undetermined"


class SyncStatus(str, Enum):
    """内容同步的结果状态。"""

    SUCCESS_WITH_CONTENT = "success_with_content"
    SUCCESS_WITHOUT_CONTENT = "success_without_content"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ConfidenceLevel(str, Enum):
    """分析结论的可信程度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class OpeningTagStatus(str, Enum):
    """开头信息的标注状态。"""

    UNANNOTATED = "unannotated"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class EvidenceType(str, Enum):
    """结论依据的来源类型。"""

    TRANSCRIPT = "transcript"
    VISUAL = "visual"
    METADATA = "metadata"


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
    """标准化后的单条内容输入，不含预先判定的主分类。"""

    account_id: str
    source: ContentSource
    identity: ContentIdentity
    published_at: datetime
    captured_at: datetime
    metrics: EngagementMetrics
    transcript: str | None = None
    video_reference: str | None = None
    sync_status: SyncStatus = SyncStatus.SUCCESS_WITH_CONTENT

    def __post_init__(self) -> None:
        _require_timezone(self.published_at, "published_at")
        _require_timezone(self.captured_at, "captured_at")


@dataclass(frozen=True)
class AnalysisEvidence:
    """可定位、可区分来源类型的分析依据。"""

    evidence_type: EvidenceType
    locator: str
    detail: str


@dataclass(frozen=True)
class OpeningAnnotation:
    """开头信息：未标注、可用片段，或不可用原因三态。"""

    status: OpeningTagStatus
    fragment: str | None = None
    evidence: tuple[AnalysisEvidence, ...] = ()
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status == OpeningTagStatus.UNANNOTATED:
            if self.fragment or self.evidence or self.unavailable_reason:
                raise ValueError("未标注开头不能附带片段、依据或不可用原因")
        elif self.status == OpeningTagStatus.AVAILABLE:
            if not self.fragment or not self.evidence or self.unavailable_reason:
                raise ValueError("可用开头必须包含片段和依据，且不能包含不可用原因")
        elif self.status == OpeningTagStatus.UNAVAILABLE:
            if self.fragment or self.evidence or not self.unavailable_reason:
                raise ValueError("不可用开头必须包含原因，且不能包含片段或依据")


@dataclass(frozen=True)
class SourceFact:
    """受指定来源约束的事实。"""

    statement: str
    source: str


@dataclass(frozen=True)
class SourceJudgment:
    """基于来源作出的判断。"""

    statement: str


@dataclass(frozen=True)
class SourceAssumption:
    """解释来源时使用的假设。"""

    statement: str


@dataclass(frozen=True)
class SourceLimitation:
    """来源本身的限制。"""

    statement: str


@dataclass(frozen=True)
class ReusableMethod:
    """可复用的方法，与事实和判断分开保存。"""

    name: str
    description: str


@dataclass(frozen=True)
class SourceConstraint:
    """来源信息可适用的边界。"""

    statement: str


@dataclass(frozen=True)
class SourceInformation:
    """来源限定信息的结构化信任边界。"""

    facts: tuple[SourceFact, ...] = ()
    judgments: tuple[SourceJudgment, ...] = ()
    assumptions: tuple[SourceAssumption, ...] = ()
    limitations: tuple[SourceLimitation, ...] = ()
    reusable_methods: tuple[ReusableMethod, ...] = ()
    source_constraints: tuple[SourceConstraint, ...] = ()


@dataclass(frozen=True)
class ProjectFact:
    """已确认的项目事实。"""

    key: str
    value: str


@dataclass(frozen=True)
class ProjectAccountRelation:
    """项目与账号的归属关系。"""

    project_id: str
    account_id: str
    context_version: str


@dataclass(frozen=True)
class ProjectContextVersion:
    """可追溯且包含已确认项目事实的项目上下文版本。"""

    project_id: str
    version: str
    effective_at: datetime
    project_persona: str
    target_users: str
    content_plan: str
    operating_direction: str
    confirmed_facts: tuple[ProjectFact, ...] = ()

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

    def __post_init__(self) -> None:
        for field_name in (
            "three_day_start",
            "three_day_end",
            "thirty_day_start",
            "thirty_day_end",
        ):
            _require_timezone(getattr(self, field_name), field_name)
        if self.three_day_start >= self.three_day_end:
            raise ValueError("三日窗口的开始必须早于结束")
        if self.thirty_day_start >= self.thirty_day_end:
            raise ValueError("三十日窗口的开始必须早于结束")
        if self.three_day_end != self.thirty_day_end:
            raise ValueError("三日和三十日窗口必须有共同结束时间")


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
    """基础分析是主分类与来源限定信息的唯一产出位置。"""

    content: ContentRecord
    category: ContentCategory
    confidence: ConfidenceLevel
    opening: OpeningAnnotation
    source_information: SourceInformation = SourceInformation()
    undetermined_reason: str | None = None

    def __post_init__(self) -> None:
        if self.category == ContentCategory.UNDETERMINED:
            if not self.undetermined_reason:
                raise ValueError("无法判断主分类时必须说明原因")
        elif self.undetermined_reason:
            raise ValueError("已判断主分类时不能携带无法判断原因")


@dataclass(frozen=True)
class ProjectJudgment:
    """供下一阶段输出的项目判断。"""

    project_id: str
    context_version: str
    status: BusinessStatus
    confidence: ConfidenceLevel
    conclusion: str


@dataclass(frozen=True)
class ContentStatistics:
    """供项目统计和日报复用的确定性统计结果。"""

    project_id: str
    context_version: str
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
    """日报只能聚合所属项目和上下文版本的判断。"""

    project_id: str
    context_version: str
    report_date: date
    generated_at: datetime
    judgments: tuple[ProjectJudgment, ...]

    def __post_init__(self) -> None:
        _require_timezone(self.generated_at, "generated_at")
        if any(
            judgment.project_id != self.project_id
            or judgment.context_version != self.context_version
            for judgment in self.judgments
        ):
            raise ValueError("日报不能混入其他项目或上下文版本的判断")


@dataclass(frozen=True)
class ContentCandidate:
    """候选内容绑定项目及上下文版本，避免跨项目投递。"""

    project_id: str
    context_version: str
    content: ContentRecord
    status: BusinessStatus
    confidence: ConfidenceLevel
    reason: str | None = None
