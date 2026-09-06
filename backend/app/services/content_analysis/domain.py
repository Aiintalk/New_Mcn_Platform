"""内容分析阶段一的稳定业务语义，不包含存储、路由或外部调用。"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import isfinite


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


class OpeningKind(str, Enum):
    """开头结论的证据语义。"""

    LANGUAGE = "language"


class EvidenceType(str, Enum):
    """结论依据的来源类型。"""

    TITLE = "title"
    TRANSCRIPT = "transcript"
    METADATA = "metadata"


class InteractionObservationType(str, Enum):
    """允许进入分析结果的非时间序列互动语义。"""

    CURRENT_VALUE = "current_value"
    CURRENT_RELATIVE_PERFORMANCE = "current_relative_performance"
    CURRENT_COMPOSITION = "current_composition"
    DATA_MATURITY = "data_maturity"


class InteractionMetric(str, Enum):
    """互动观察允许引用的四项当前指标。"""

    LIKE = "like"
    COMMENT = "comment"
    SHARE = "share"
    FAVORITE = "favorite"


class RelativePerformanceLevel(str, Enum):
    """当前值相对当前基准的受限等级。"""

    ABOVE = "above"
    NEAR = "near"
    BELOW = "below"
    UNKNOWN = "unknown"


class DataMaturity(str, Enum):
    """采集后时间对应的数据成熟度：小于 6 小时、6—12 小时、至少 12 小时。"""

    EARLY = "early"
    INITIAL = "initial"
    QUALITATIVE = "qualitative"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} 必须带时区")


def _require_non_empty_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空文本")


def _require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} 必须是不可变元组")


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
        for field_name in (
            "like_count",
            "comment_count",
            "share_count",
            "favorite_count",
        ):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{field_name} 互动值只能是非负整数或空值")
        if self.play_count is not None and type(self.play_count) is not int:
            raise ValueError("play_count 只能是整数或空值")
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
    title: str | None = None
    transcript: str | None = None
    operations_review_url: str | None = None

    def __post_init__(self) -> None:
        _require_timezone(self.published_at, "published_at")
        _require_timezone(self.captured_at, "captured_at")
        for field_name in ("title", "transcript", "operations_review_url"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{field_name} 必须是非空文本或空值")


@dataclass(frozen=True)
class AnalysisEvidence:
    """可定位、可区分来源类型的分析依据。"""

    evidence_type: EvidenceType
    locator: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_type, EvidenceType):
            raise ValueError("分析依据类型不受支持")
        if not isinstance(self.locator, str) or not self.locator.strip():
            raise ValueError("分析依据定位不能为空")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("分析依据说明不能为空")


@dataclass(frozen=True)
class InteractionObservation:
    """只用封闭字段表达当前互动观察。"""

    observation_type: InteractionObservationType
    metric: InteractionMetric | None = None
    current_value: int | None = None
    relative_level: RelativePerformanceLevel | None = None
    benchmark_value: float | None = None
    sample_size: int | None = None
    numerator_metric: InteractionMetric | None = None
    numerator_value: int | None = None
    denominator_metric: InteractionMetric | None = None
    denominator_value: int | None = None
    maturity: DataMaturity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observation_type, InteractionObservationType):
            raise ValueError("互动观察类型不受支持")
        fields = {
            "metric": self.metric,
            "current_value": self.current_value,
            "relative_level": self.relative_level,
            "benchmark_value": self.benchmark_value,
            "sample_size": self.sample_size,
            "numerator_metric": self.numerator_metric,
            "numerator_value": self.numerator_value,
            "denominator_metric": self.denominator_metric,
            "denominator_value": self.denominator_value,
            "maturity": self.maturity,
        }
        required_and_allowed = {
            InteractionObservationType.CURRENT_VALUE: (
                {"metric", "current_value"},
                {"metric", "current_value"},
            ),
            InteractionObservationType.CURRENT_RELATIVE_PERFORMANCE: (
                {"metric", "relative_level"},
                {"metric", "relative_level", "benchmark_value", "sample_size"},
            ),
            InteractionObservationType.CURRENT_COMPOSITION: (
                {
                    "numerator_metric",
                    "numerator_value",
                    "denominator_metric",
                    "denominator_value",
                },
                {
                    "numerator_metric",
                    "numerator_value",
                    "denominator_metric",
                    "denominator_value",
                },
            ),
            InteractionObservationType.DATA_MATURITY: (
                {"maturity"},
                {"maturity"},
            ),
        }
        required, allowed = required_and_allowed[self.observation_type]
        provided = {name for name, value in fields.items() if value is not None}
        if not required <= provided or not provided <= allowed:
            raise ValueError("互动观察字段组合与类型不匹配")

        metric_fields = (self.metric, self.numerator_metric, self.denominator_metric)
        if any(
            value is not None and not isinstance(value, InteractionMetric)
            for value in metric_fields
        ):
            raise ValueError("互动指标不受支持")
        if self.relative_level is not None and not isinstance(
            self.relative_level, RelativePerformanceLevel
        ):
            raise ValueError("相对表现等级不受支持")
        if self.maturity is not None and not isinstance(self.maturity, DataMaturity):
            raise ValueError("数据成熟度不受支持")

        counts = (self.current_value, self.numerator_value, self.denominator_value)
        if any(
            value is not None and (type(value) is not int or value < 0)
            for value in counts
        ):
            raise ValueError("当前互动值只能是非负整数或空值")
        if self.benchmark_value is not None and (
            type(self.benchmark_value) not in (int, float)
            or not isfinite(self.benchmark_value)
            or self.benchmark_value < 0
        ):
            raise ValueError("当前基准值必须是非负有限数")
        if self.sample_size is not None and (
            type(self.sample_size) is not int or self.sample_size <= 0
        ):
            raise ValueError("当前基准样本数必须大于零")
        if self.denominator_value == 0:
            raise ValueError("当前互动构成的分母不能为零")


@dataclass(frozen=True)
class OpeningAnnotation:
    """开头信息：未标注、可用片段，或不可用原因三态。"""

    status: OpeningTagStatus
    kind: OpeningKind | None = None
    fragment: str | None = None
    evidence: tuple[AnalysisEvidence, ...] = ()
    unavailable_reason: str | None = None
    applicable_boundaries: tuple["SourceConstraint", ...] = ()

    def __post_init__(self) -> None:
        _require_tuple(self.evidence, "开头依据")
        _require_tuple(self.applicable_boundaries, "开头适用边界")
        if self.fragment is not None and (
            not isinstance(self.fragment, str) or not self.fragment.strip()
        ):
            raise ValueError("开头片段必须为非空文本或空值")
        if self.unavailable_reason is not None and (
            not isinstance(self.unavailable_reason, str)
            or not self.unavailable_reason.strip()
        ):
            raise ValueError("开头不可用原因必须为非空文本或空值")
        if any(not isinstance(item, AnalysisEvidence) for item in self.evidence):
            raise ValueError("开头依据必须使用结构化类型")
        if any(
            not isinstance(item, SourceConstraint)
            for item in self.applicable_boundaries
        ):
            raise ValueError("开头适用边界必须使用结构化类型")
        if not isinstance(self.status, OpeningTagStatus):
            raise ValueError("开头状态必须使用封闭枚举")
        if self.status == OpeningTagStatus.UNANNOTATED:
            if (
                self.kind is not None
                or self.fragment
                or self.evidence
                or self.unavailable_reason
                or self.applicable_boundaries
            ):
                raise ValueError("未标注开头不能附带类型、片段、依据或不可用原因")
        elif self.status == OpeningTagStatus.AVAILABLE:
            if (
                not isinstance(self.kind, OpeningKind)
                or not self.fragment
                or not self.evidence
                or self.unavailable_reason
            ):
                raise ValueError("可用开头必须包含开头类型、片段和依据，且不能包含不可用原因")
        elif self.status == OpeningTagStatus.UNAVAILABLE:
            if (
                not isinstance(self.kind, OpeningKind)
                or self.fragment
                or self.evidence
                or not self.unavailable_reason
                or self.applicable_boundaries
            ):
                raise ValueError("不可用开头必须包含开头类型和原因，且不能包含片段或依据")


class SourceFactKind(str, Enum):
    """会限制跨项目复用的来源事实类别。"""

    BRAND = "brand"
    PRODUCT = "product"
    PRICE = "price"
    PROMOTION = "promotion"
    EFFICACY = "efficacy"
    PROOF = "proof"
    PRODUCT_CLAIM = "product_claim"
    PERSON_IDENTITY = "person_identity"
    PERSONAL_EXPERIENCE = "personal_experience"
    OTHER = "other"


_GENERIC_RESTRICTED_FRAGMENTS = {
    "原视频",
    "视频",
    "来源",
    "来源内容",
    "内容",
    "展示",
    "商品",
    "产品",
    "事实",
    "陈述",
}


@dataclass(frozen=True)
class SourceFact:
    """受指定来源约束的事实。"""

    statement: str
    source: str
    kind: SourceFactKind = SourceFactKind.OTHER
    restricted_fragments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple(self.restricted_fragments, "来源限定片段")
        if not isinstance(self.kind, SourceFactKind):
            raise ValueError("来源事实类别不受支持")
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise ValueError("来源事实不能为空")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("来源事实必须包含来源")
        if self.kind != SourceFactKind.OTHER and not self.restricted_fragments:
            raise ValueError("具体来源事实必须明确来源限定片段")
        normalized_statement = "".join(
            character.casefold()
            for character in self.statement
            if character.isalnum()
        )
        if any(
            not isinstance(fragment, str)
            or not fragment.strip()
            or "".join(
                character.casefold()
                for character in fragment
                if character.isalnum()
            )
            not in normalized_statement
            for fragment in self.restricted_fragments
        ):
            raise ValueError("来源限定片段必须是事实陈述中的非空文本")
        if self.kind != SourceFactKind.OTHER and any(
            "".join(
                character.casefold()
                for character in fragment
                if character.isalnum()
            )
            in _GENERIC_RESTRICTED_FRAGMENTS
            for fragment in self.restricted_fragments
        ):
            raise ValueError("来源限定片段必须指向具体来源实体或说法")


@dataclass(frozen=True)
class SourceJudgment:
    """基于来源作出的判断。"""

    statement: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.statement, "来源判断")


@dataclass(frozen=True)
class SourceAssumption:
    """解释来源时使用的假设。"""

    statement: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.statement, "来源假设")


@dataclass(frozen=True)
class SourceLimitation:
    """来源本身的限制。"""

    statement: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.statement, "来源限制")


@dataclass(frozen=True)
class ReusableMethod:
    """可复用的方法，与事实和判断分开保存。"""

    name: str
    description: str
    method_key: str
    evidence: tuple[AnalysisEvidence, ...]
    applicable_boundaries: tuple["SourceConstraint", ...]

    def __post_init__(self) -> None:
        _require_tuple(self.evidence, "可复用方法依据")
        _require_tuple(self.applicable_boundaries, "可复用方法适用边界")
        if not isinstance(self.method_key, str) or not self.method_key.strip():
            raise ValueError("可复用方法必须包含稳定方法键")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("可复用方法名称不能为空")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("可复用方法说明不能为空")
        if not self.evidence or any(
            not isinstance(item, AnalysisEvidence) for item in self.evidence
        ):
            raise ValueError("可复用方法必须包含结构化来源证据")
        if not self.applicable_boundaries or any(
            not isinstance(item, SourceConstraint)
            for item in self.applicable_boundaries
        ):
            raise ValueError("可复用方法必须包含结构化适用边界")


@dataclass(frozen=True)
class SourceConstraint:
    """来源信息可适用的边界。"""

    statement: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.statement, "来源适用边界")


@dataclass(frozen=True)
class SourceInformation:
    """来源限定信息的结构化信任边界。"""

    facts: tuple[SourceFact, ...] = ()
    judgments: tuple[SourceJudgment, ...] = ()
    assumptions: tuple[SourceAssumption, ...] = ()
    limitations: tuple[SourceLimitation, ...] = ()
    source_constraints: tuple[SourceConstraint, ...] = ()

    def __post_init__(self) -> None:
        expected_types = {
            "facts": SourceFact,
            "judgments": SourceJudgment,
            "assumptions": SourceAssumption,
            "limitations": SourceLimitation,
            "source_constraints": SourceConstraint,
        }
        for field_name in expected_types:
            _require_tuple(getattr(self, field_name), field_name)
        if any(
            not isinstance(item, expected_type)
            for field_name, expected_type in expected_types.items()
            for item in getattr(self, field_name)
        ):
            raise ValueError("来源限定信息必须使用对应的结构化对象")


@dataclass(frozen=True)
class ProjectFact:
    """已确认的项目事实。"""

    key: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("项目事实键必须是非空文本")
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("项目事实值必须是非空文本")


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
        _require_tuple(self.confirmed_facts, "项目确认事实")
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

    def __post_init__(self) -> None:
        if any(
            type(value) not in (int, float)
            or not isfinite(value)
            or value < 0
            for value in (self.mean, self.median)
        ):
            raise ValueError("人设点赞基线均值和中位数必须是非负有限数")
        if type(self.sample_size) is not int or self.sample_size <= 0:
            raise ValueError("人设点赞基线样本数必须为正整数")
        if any(
            type(value) is not int or value < 0
            for value in (self.maximum, self.minimum)
        ):
            raise ValueError("人设点赞基线最高和最低值必须为非负整数")
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("人设点赞基线均值必须位于最低和最高值之间")
        if not self.minimum <= self.median <= self.maximum:
            raise ValueError("人设点赞基线中位数必须位于最低和最高值之间")


@dataclass(frozen=True)
class WeeklyPersonaBaseline:
    """一个稳定账号在最近 30 个完整自然日的人设点赞基准。"""

    account_id: str
    window_start: datetime
    window_end: datetime
    baseline: LikeBaseline

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("周度人设基准必须包含账号编号")
        _require_timezone(self.window_start, "window_start")
        _require_timezone(self.window_end, "window_end")
        if self.window_start >= self.window_end:
            raise ValueError("周度人设基准窗口无效")


@dataclass(frozen=True)
class BasicAnalysis:
    """基础分析是主分类与来源限定信息的唯一产出位置。"""

    content: ContentRecord
    category: ContentCategory
    confidence: ConfidenceLevel
    opening: OpeningAnnotation
    data_maturity: DataMaturity | None = None
    source_information: SourceInformation = SourceInformation()
    reusable_methods: tuple[ReusableMethod, ...] = ()
    topic: str | None = None
    summary: str | None = None
    structure: tuple[str, ...] = ()
    persuasion_chain: tuple[str, ...] = ()
    interaction_observations: tuple[InteractionObservation, ...] = ()
    undetermined_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, ContentRecord):
            raise ValueError("基础分析内容必须使用结构化内容对象")
        if not isinstance(self.category, ContentCategory):
            raise ValueError("基础分析分类不受支持")
        if not isinstance(self.confidence, ConfidenceLevel):
            raise ValueError("基础分析可信程度不受支持")
        if not isinstance(self.opening, OpeningAnnotation):
            raise ValueError("基础分析开头必须使用结构化对象")
        if not isinstance(self.source_information, SourceInformation):
            raise ValueError("来源限定信息必须使用结构化对象")
        for field_name in (
            "reusable_methods",
            "structure",
            "persuasion_chain",
            "interaction_observations",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                raise ValueError(f"{field_name} 必须是不可变元组")
        if any(
            not isinstance(item, ReusableMethod) for item in self.reusable_methods
        ):
            raise ValueError("可复用方法必须使用结构化对象")
        if self.topic is not None and (
            not isinstance(self.topic, str) or not self.topic.strip()
        ):
            raise ValueError("选题必须是非空文本或空值")
        if self.summary is not None and (
            not isinstance(self.summary, str) or not self.summary.strip()
        ):
            raise ValueError("内容摘要必须是非空文本或空值")
        if self.undetermined_reason is not None and (
            not isinstance(self.undetermined_reason, str)
            or not self.undetermined_reason.strip()
        ):
            raise ValueError("无法判断原因必须是非空文本或空值")
        for field_name in ("structure", "persuasion_chain"):
            if any(
                not isinstance(item, str) or not item.strip()
                for item in getattr(self, field_name)
            ):
                raise ValueError(f"{field_name} 必须由非空文本组成")
        if self.data_maturity is not None and not isinstance(
            self.data_maturity, DataMaturity
        ):
            raise ValueError("数据成熟度不受支持")
        if any(
            not isinstance(item, InteractionObservation)
            for item in self.interaction_observations
        ):
            raise ValueError("互动观察必须使用结构化互动观察对象")
        if self.category == ContentCategory.UNDETERMINED:
            if not isinstance(self.undetermined_reason, str) or not (
                self.undetermined_reason.strip()
            ):
                raise ValueError("无法判断原因必须是非空文本")
        elif self.undetermined_reason is not None:
            raise ValueError("已判断主分类时不能携带无法判断原因")
