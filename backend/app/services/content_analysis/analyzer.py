"""可注入智能分析协议，以及不依赖模型的输出边界清理。"""
from dataclasses import dataclass, replace
from enum import Enum
import re
from typing import Protocol

from .domain import (
    AnalysisEvidence,
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentRecord,
    EvidenceType,
    InteractionMetric,
    InteractionObservationType,
    MediaReadStatus,
    OpeningAnnotation,
    OpeningKind,
    OpeningTagStatus,
    ProjectContextVersion,
    ReusableMethod,
    SourceConstraint,
    SourceFactKind,
    SourceInformation,
    SourceLimitation,
)


class CandidateValueSignal(str, Enum):
    """分析器可声明的封闭候选价值信号。"""

    EARLY_DATA_STRENGTH = "early_data_strength"
    RELATIVE_BENCHMARK_OUTPERFORMANCE = "relative_benchmark_outperformance"
    NOVEL_TOPIC_OR_STRUCTURE = "novel_topic_or_structure"
    CLEAR_TRAFFIC_HOOK = "clear_traffic_hook"
    REUSABLE_CONVERSION_STRUCTURE = "reusable_conversion_structure"
    NOTABLE_SHOT_PERFORMANCE = "notable_shot_performance"


class ProjectFitDimension(str, Enum):
    """项目适配理由必须关联的项目上下文维度。"""

    PROJECT_PERSONA = "project_persona"
    TARGET_USERS = "target_users"
    CONTENT_PLAN = "content_plan"
    OPERATING_DIRECTION = "operating_direction"


@dataclass(frozen=True)
class ProjectFitReason:
    """一条结构化项目适配理由。"""

    dimension: ProjectFitDimension
    statement: str

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, ProjectFitDimension):
            raise ValueError("项目适配理由维度必须使用封闭枚举")
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise ValueError("项目适配理由不能为空")


@dataclass(frozen=True)
class ProjectAssessment:
    """分析器对一个明确项目上下文作出的适配判断。"""

    project_id: str
    context_version: str
    is_fit: bool
    confidence: ConfidenceLevel
    conclusion: str
    is_opportunity: bool = False
    priority: int | None = None
    body_benchmark: str | None = None
    body_benchmark_evidence: tuple[AnalysisEvidence, ...] = ()
    body_benchmark_boundaries: tuple[SourceConstraint, ...] = ()
    value_signals: tuple[CandidateValueSignal, ...] = ()
    fit_reasons: tuple[ProjectFitReason, ...] = ()
    limitations: tuple[str, ...] = ()
    recommended_action: str | None = None
    decision_basis: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.is_fit) is not bool or type(self.is_opportunity) is not bool:
            raise ValueError("项目适配与机会标记必须是原生布尔值")
        if not isinstance(self.confidence, ConfidenceLevel):
            raise ValueError("项目判断可信程度不受支持")
        if not isinstance(self.project_id, str) or not self.project_id.strip():
            raise ValueError("项目判断必须包含项目编号")
        if not isinstance(self.context_version, str) or not self.context_version.strip():
            raise ValueError("项目判断必须包含上下文版本")
        if not isinstance(self.conclusion, str) or not self.conclusion.strip():
            raise ValueError("项目判断结论不能为空")
        if self.priority is not None and (
            type(self.priority) is not int or self.priority < 0
        ):
            raise ValueError("项目判断优先级必须是非负整数或空值")
        if self.body_benchmark is not None and not isinstance(
            self.body_benchmark, str
        ):
            raise ValueError("正文对标必须是文本或空值")
        for field_name in (
            "body_benchmark_evidence",
            "body_benchmark_boundaries",
            "value_signals",
            "fit_reasons",
            "limitations",
            "decision_basis",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                raise ValueError(f"{field_name} 必须是不可变元组")
        if self.body_benchmark is not None:
            if not self.body_benchmark.strip():
                raise ValueError("正文对标不能为空文本")
            if not self.body_benchmark_evidence or any(
                not isinstance(item, AnalysisEvidence)
                for item in self.body_benchmark_evidence
            ):
                raise ValueError("正文对标必须包含结构化来源证据")
            if not self.body_benchmark_boundaries or any(
                not isinstance(item, SourceConstraint)
                for item in self.body_benchmark_boundaries
            ):
                raise ValueError("正文对标必须包含结构化适用边界")
        elif self.body_benchmark_evidence or self.body_benchmark_boundaries:
            raise ValueError("没有正文对标时不能携带正文证据或适用边界")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.limitations
        ):
            raise ValueError("项目判断限制必须是非空文本")
        if self.is_opportunity and not self.is_fit:
            raise ValueError("项目机会必须同时满足项目适配")
        if self.is_opportunity and (
            not isinstance(self.recommended_action, str)
            or not self.recommended_action.strip()
            or not self.decision_basis
        ):
            raise ValueError("项目机会必须包含推荐动作和判断依据")
        if self.recommended_action is not None and (
            not isinstance(self.recommended_action, str)
            or not self.recommended_action.strip()
        ):
            raise ValueError("推荐动作必须是非空文本或空值")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.decision_basis
        ):
            raise ValueError("判断依据必须是非空文本")
        if any(
            not isinstance(signal, CandidateValueSignal)
            for signal in self.value_signals
        ):
            raise ValueError("候选价值信号必须使用封闭枚举")
        if any(
            not isinstance(reason, ProjectFitReason) for reason in self.fit_reasons
        ):
            raise ValueError("项目适配理由必须使用结构化类型")


class ContentAnalyzer(Protocol):
    """由调用方显式注入的异步智能分析边界，不提供默认实现。"""

    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        """产出可跨项目复用的基础内容分析。"""

        ...

    async def assess_project(
        self,
        analysis: BasicAnalysis,
        project_context: ProjectContextVersion,
    ) -> ProjectAssessment:
        """在单一项目上下文中判断内容适配性。"""

        ...


_SENSITIVE_SOURCE_FACT_KINDS = {
    SourceFactKind.BRAND,
    SourceFactKind.PRODUCT,
    SourceFactKind.PRICE,
    SourceFactKind.PROMOTION,
    SourceFactKind.EFFICACY,
    SourceFactKind.PROOF,
    SourceFactKind.PRODUCT_CLAIM,
    SourceFactKind.PERSON_IDENTITY,
    SourceFactKind.PERSONAL_EXPERIENCE,
}


def _normalized_text(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


_UNSUPPORTED_PERFORMANCE_CLAIMS = (
    "播放互动率",
    "播放转化率",
    "逐日增量",
    "增长速度",
    "互动增长",
    "持续上涨",
    "持续下降",
    "上涨趋势",
    "下降趋势",
    "爆发趋势",
    "爆发时间",
    "真实转化好",
    "实际转化好",
    "转化效果好",
    "已验证成交",
    "真实成交",
    "高消耗",
    "高投放",
)
_VISUAL_CLAIM_FRAGMENTS = ("第一画面", "首帧", "镜头", "画面")
_UNSUPPORTED_PERFORMANCE_PATTERNS = (
    re.compile(
        r"(?:近|最近).{0,4}(?:天|日).{0,8}"
        r"(?:互动|点赞|评论|分享|收藏).{0,8}"
        r"(?:越来越|变好|提升|增加|上涨|走高|下降|变差)"
    ),
    re.compile(
        r"(?:互动|点赞|评论|分享|收藏|订单)"
        r"(?:(?!(?:互动|点赞|评论|分享|收藏|订单)).){0,8}"
        r"(?:越来越好|变好|提升|增加|上涨|走高|下降|变差|优异|优秀|突出|"
        r"攀升|飙升|亮眼|可观|出色|非常强|爆棚|大幅增长|猛增|暴涨)"
    ),
    re.compile(
        r"(?:成交|转化|投放|消耗|订单)"
        r"(?:(?!(?:成交|转化|投放|消耗|订单)).){0,8}"
        r"(?:优异|优秀|良好|很好|不错|突出|强劲|较高|很高|提升|上涨|"
        r"攀升|飙升|亮眼|可观|出色|非常强|爆棚|大幅增长|猛增|暴涨)"
    ),
)
_VISUAL_CLAIM_PATTERNS = (
    re.compile(r"(?:开场|开头|起始|一开始).{0,8}(?:展示|出现|露出|呈现)"),
    re.compile(r"(?:展示|露出|呈现).{0,4}(?:产品|商品|人物|场景)"),
    re.compile(r"(?:出现|看见|看到).{0,4}(?:产品|商品|人物|场景)"),
    re.compile(
        r"(?:前|开头|起始)[零一二三四五六七八九十百两\d]+(?:秒|帧).{0,8}"
        r"(?:出现|展示|露出|呈现|看见|看到)"
    ),
)
_NEUTRAL_VISUAL_BOUNDARY_PATTERN = re.compile(
    r"^(?:仅|只)(?:可)?(?:复用|参考|借鉴|验证)"
    r"(?:视觉|画面|镜头|首帧|第一画面)(?:结构|形式|方法|节奏|逻辑)$"
)
_SOURCE_SPECIFIC_PATTERNS = (
    re.compile(
        r"(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两]+)元"
        r"(?!组|结构|方法|模型|分析|逻辑|关系|对立|分类|体系|函数|方程|次)"
        r"(?:内|以下|到手)?"
    ),
    re.compile(r"(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两]+)折"),
    re.compile(r"(?:承诺|保证|证明).{0,6}(?:助眠|美白|祛痘|减肥|治疗|治愈|降血糖|降血压)"),
    re.compile(r"(?:助眠|美白|祛痘|减肥|治疗|治愈|改善睡眠|降血糖|降血压).{0,6}(?:承诺|保证|证明|有效)"),
    re.compile(r"(?:大学|医院|机构|品牌|公司).{0,8}(?:教授|医生|专家|创始人|创办人)"),
    re.compile(r"(?:是|作为|来自).{0,12}(?:教授|医生|专家|创始人|创办人)"),
    re.compile(r"(?:亲身|个人|本人|真实)(?:经历|经验|故事)"),
    re.compile(
        r"(?:复用|照搬|沿用|借鉴|参考|模仿)"
        r"[\u4e00-\u9fffA-Za-z0-9]{2,12}(?:用户)?案例"
    ),
    re.compile(
        r"(?:原视频|来源内容)?(?:中)?(?:展示|使用|介绍|讲述)"
        r"[\u4e00-\u9fffA-Za-z0-9]{2,12}(?:商品|产品|品牌)"
    ),
)

def _contains_unsupported_performance_claim(value: str) -> bool:
    normalized = _normalized_text(value)
    return any(
        fragment in normalized for fragment in _UNSUPPORTED_PERFORMANCE_CLAIMS
    ) or any(pattern.search(normalized) for pattern in _UNSUPPORTED_PERFORMANCE_PATTERNS)


def _contains_visual_claim(value: str) -> bool:
    normalized = _normalized_text(value)
    return any(
        fragment in normalized for fragment in _VISUAL_CLAIM_FRAGMENTS
    ) or any(pattern.search(normalized) for pattern in _VISUAL_CLAIM_PATTERNS)


def _is_neutral_visual_boundary(value: str) -> bool:
    return bool(_NEUTRAL_VISUAL_BOUNDARY_PATTERN.fullmatch(_normalized_text(value)))


def _contains_source_specific_claim(value: str) -> bool:
    normalized = _normalized_text(value)
    normalized_without_generic_brand = normalized.replace("品牌", "").replace(
        "名牌",
        "",
    )
    has_named_brand = bool(
        re.search(r"[\u4e00-\u9fff]{2,8}牌", normalized_without_generic_brand)
    )
    case_marker = "案例"
    named_case_prefix = ""
    if case_marker in normalized:
        named_case_prefix = normalized.split(case_marker, 1)[0]
        removable_prefixes = (
            "原视频中",
            "原视频",
            "来源内容中",
            "来源内容",
            "复用",
            "照搬",
            "沿用",
            "借鉴",
            "参考",
            "模仿",
            "讲述",
            "采用",
            "使用",
        )
        prefix_changed = True
        while prefix_changed:
            prefix_changed = False
            for prefix in removable_prefixes:
                if named_case_prefix.startswith(prefix):
                    named_case_prefix = named_case_prefix[len(prefix) :]
                    prefix_changed = True
                    break
        removable_suffixes = (
            "典型",
            "匿名",
            "通用",
            "目标",
            "真实",
            "用户",
            "顾客",
            "消费者",
            "客户",
        )
        suffix_changed = True
        while suffix_changed:
            suffix_changed = False
            for suffix in removable_suffixes:
                if named_case_prefix.endswith(suffix):
                    named_case_prefix = named_case_prefix[: -len(suffix)]
                    suffix_changed = True
                    break
    has_named_case = len(named_case_prefix) >= 2
    return has_named_brand or has_named_case or any(
        pattern.search(normalized) for pattern in _SOURCE_SPECIFIC_PATTERNS
    )


def _contains_source_limited_fragment(
    value: str,
    source_information: SourceInformation,
) -> bool:
    normalized = _normalized_text(value)
    if _contains_source_specific_claim(normalized):
        return True
    for fact in source_information.facts:
        if (
            fact.kind not in _SENSITIVE_SOURCE_FACT_KINDS
            and not fact.restricted_fragments
        ):
            continue
        for fragment in fact.restricted_fragments:
            if _normalized_text(fragment) in normalized:
                return True
    return False


def is_source_limited_text(
    value: str,
    source_information: SourceInformation,
) -> bool:
    """判断文本是否携带只属于原来源的事实片段。"""
    return _contains_source_limited_fragment(value, source_information)


def is_reusable_method_safe(
    method: ReusableMethod,
    source_information: SourceInformation | None = None,
) -> bool:
    """阻断方法及其证据中具体的来源商品说法。"""
    method_values = (method.method_key, method.name, method.description) + tuple(
        item.detail for item in method.evidence
    )
    boundary_values = tuple(
        item.statement for item in method.applicable_boundaries
    )
    if any(
        _contains_source_specific_claim(value)
        or _contains_unsupported_performance_claim(value)
        for value in method_values
    ):
        return False
    if any(
        _contains_unsupported_performance_claim(value)
        and not _claim_roles_are_valid(
            value,
            role="limitation",
            visual_is_readable=True,
        )
        for value in boundary_values
    ):
        return False
    if source_information is None:
        return True
    if any(
        fact.kind == SourceFactKind.OTHER
        and not fact.restricted_fragments
        and _contains_source_specific_claim(fact.statement)
        for fact in source_information.facts
    ):
        return False
    return not any(
        _contains_source_limited_fragment(value, source_information)
        for value in method_values + boundary_values
    )


def _validate_generated_claims(
    values: tuple[str | None, ...],
    *,
    visual_is_readable: bool,
) -> None:
    for value in values:
        if not value:
            continue
        if _contains_unsupported_performance_claim(value):
            raise ValueError("分析器输出包含当前输入无法支持的效果或趋势结论")
        if not visual_is_readable and _contains_visual_claim(value):
            raise ValueError("分析器输出包含没有可读画面支持的视觉结论")


def _has_unsupported_claim(value: str, *, visual_is_readable: bool) -> bool:
    return _contains_unsupported_performance_claim(value) or (
        not visual_is_readable and _contains_visual_claim(value)
    )


def _claim_roles_are_valid(
    value: str,
    *,
    role: str,
    visual_is_readable: bool,
) -> bool:
    indexed_characters = tuple(
        (character.casefold(), index)
        for index, character in enumerate(value)
        if character.isalnum()
    )
    normalized = "".join(character for character, _ in indexed_characters)
    candidate_spans: set[tuple[int, int]] = set()
    literal_claims = list(_UNSUPPORTED_PERFORMANCE_CLAIMS)
    claim_patterns = list(_UNSUPPORTED_PERFORMANCE_PATTERNS)
    if not visual_is_readable:
        literal_claims.extend(_VISUAL_CLAIM_FRAGMENTS)
        claim_patterns.extend(_VISUAL_CLAIM_PATTERNS)
    for claim in literal_claims:
        start = normalized.find(claim)
        while start >= 0:
            candidate_spans.add((start, start + len(claim)))
            start = normalized.find(claim, start + 1)
    for pattern in claim_patterns:
        candidate_spans.update(
            (match.start(), match.end()) for match in pattern.finditer(normalized)
        )
    claim_spans = tuple(sorted(candidate_spans))
    for start, end in claim_spans:
        raw_start = indexed_characters[start][1]
        raw_end = indexed_characters[end - 1][1] + 1
        before_scope = re.split(r"[，,。；;！？!?]", value[:raw_start])[-1]
        before_scope = re.split(
            r"(?:但是|可是|不过|然而|同时|并且|以及|但|而|却)",
            before_scope,
        )[-1]
        after_scope = re.split(r"[，,。；;！？!?]", value[raw_end:])[0]
        before = _normalized_text(before_scope)[-10:]
        after = _normalized_text(after_scope)[:16]
        role_window = before + normalized[start:end] + after
        if role == "hypothesis":
            has_role = bool(
                re.search(r"(?:可能|或许|推测|假设)(?!性).{0,4}$", before)
                or re.match(r".{0,4}(?:仍待|尚待|待).{0,8}验证", after)
            )
        else:
            has_role = bool(
                re.search(
                    r"(?:无法|不能|不可|不代表|未|尚未).{0,6}$",
                    before,
                )
                or re.search(
                    r"(?:没有|缺少).{0,12}(?:数据|证据|画面|信息|依据)",
                    role_window,
                )
                or re.search(
                    r"(?:结论|判断|分析).{0,4}受限",
                    role_window,
                )
                or re.match(
                    r".{0,4}(?:没有|缺少|无法|不能|不可|未|尚未)"
                    r".{0,8}(?:数据|证据|验证|确认|读取|获得)",
                    after,
                )
            )
        if not has_role:
            return False
    return True


def _validate_source_information_roles(
    source_information: SourceInformation,
    *,
    visual_is_readable: bool,
) -> None:
    for assumption in source_information.assumptions:
        has_unsupported_claim = _has_unsupported_claim(
            assumption.statement,
            visual_is_readable=visual_is_readable,
        )
        if has_unsupported_claim and not _claim_roles_are_valid(
            assumption.statement,
            role="hypothesis",
            visual_is_readable=visual_is_readable,
        ):
            raise ValueError("效果或视觉假设必须明确标记为待验证且不能夹带确定结论")
    for limitation in source_information.limitations:
        has_unsupported_claim = _has_unsupported_claim(
            limitation.statement,
            visual_is_readable=visual_is_readable,
        )
        if has_unsupported_claim and not _claim_roles_are_valid(
            limitation.statement,
            role="limitation",
            visual_is_readable=visual_is_readable,
        ):
            raise ValueError("限制字段不能伪装成确定的效果或视觉结论")


def _validate_limitation_role(
    limitations: tuple[str, ...],
    *,
    visual_is_readable: bool,
) -> None:
    for limitation in limitations:
        has_unsupported_claim = _has_unsupported_claim(
            limitation,
            visual_is_readable=visual_is_readable,
        )
        if has_unsupported_claim and not _claim_roles_are_valid(
            limitation,
            role="limitation",
            visual_is_readable=visual_is_readable,
        ):
            raise ValueError("项目限制字段不能伪装成确定的效果或视觉结论")


def _boundary_claim_is_valid(value: str, *, visual_is_readable: bool) -> bool:
    effective_visual_readable = visual_is_readable or _is_neutral_visual_boundary(
        value
    )
    return not _has_unsupported_claim(
        value,
        visual_is_readable=effective_visual_readable,
    ) or _claim_roles_are_valid(
        value,
        role="limitation",
        visual_is_readable=effective_visual_readable,
    )


def _validate_boundary_claims(
    boundaries: tuple[str, ...],
    *,
    visual_is_readable: bool,
) -> None:
    if any(
        not _boundary_claim_is_valid(
            boundary,
            visual_is_readable=visual_is_readable,
        )
        for boundary in boundaries
    ):
        raise ValueError("适用边界不能伪装成确定的效果或视觉结论")


def _evidence_is_bound(item: AnalysisEvidence, analysis: BasicAnalysis) -> bool:
    if item.evidence_type == EvidenceType.TRANSCRIPT:
        transcript = _normalized_text(analysis.content.transcript or "")
        detail = _normalized_text(item.detail)
        return bool(transcript and detail and detail in transcript)
    if item.evidence_type == EvidenceType.VISUAL:
        return item.locator in analysis.content.media_read_result.evidence_refs
    return False


_METRIC_FIELDS = {
    InteractionMetric.LIKE: "like_count",
    InteractionMetric.COMMENT: "comment_count",
    InteractionMetric.SHARE: "share_count",
    InteractionMetric.FAVORITE: "favorite_count",
}


def _validate_interaction_evidence(analysis: BasicAnalysis) -> None:
    metrics = analysis.content.metrics
    for observation in analysis.interaction_observations:
        if observation.observation_type == InteractionObservationType.CURRENT_VALUE:
            expected = getattr(metrics, _METRIC_FIELDS[observation.metric])
            if observation.current_value != expected:
                raise ValueError("当前互动观察与输入指标不一致")
        elif observation.observation_type == InteractionObservationType.CURRENT_COMPOSITION:
            expected_numerator = getattr(
                metrics,
                _METRIC_FIELDS[observation.numerator_metric],
            )
            expected_denominator = getattr(
                metrics,
                _METRIC_FIELDS[observation.denominator_metric],
            )
            if (
                observation.numerator_value != expected_numerator
                or observation.denominator_value != expected_denominator
            ):
                raise ValueError("当前互动构成与输入指标不一致")


def enforce_project_assessment_boundaries(
    assessment: ProjectAssessment,
    analysis: BasicAnalysis,
) -> ProjectAssessment:
    """阻断来源商品片段或无来源证据的正文结构跨项目传播。"""
    visual_is_readable = (
        analysis.content.media_read_result.status == MediaReadStatus.READABLE
    )
    _validate_generated_claims(
        (
            assessment.conclusion,
            assessment.body_benchmark,
            assessment.recommended_action,
            *(reason.statement for reason in assessment.fit_reasons),
            *assessment.decision_basis,
        ),
        visual_is_readable=visual_is_readable,
    )
    _validate_limitation_role(
        assessment.limitations,
        visual_is_readable=visual_is_readable,
    )
    _validate_boundary_claims(
        tuple(item.statement for item in assessment.body_benchmark_boundaries),
        visual_is_readable=visual_is_readable,
    )
    if any(
        value
        and _contains_source_limited_fragment(value, analysis.source_information)
        for value in (
            assessment.conclusion,
            assessment.recommended_action,
            *(reason.statement for reason in assessment.fit_reasons),
            *assessment.decision_basis,
        )
    ):
        raise ValueError("项目判断包含来源限定信息")
    body = assessment.body_benchmark
    if body is None:
        return assessment
    evidence_is_bound = all(
        _evidence_is_bound(item, analysis)
        for item in assessment.body_benchmark_evidence
    )
    if (
        _contains_source_limited_fragment(body, analysis.source_information)
        or any(
            _contains_source_limited_fragment(
                item.statement,
                analysis.source_information,
            )
            for item in assessment.body_benchmark_boundaries
        )
        or not evidence_is_bound
    ):
        limitation = "正文对标含来源限定信息或无法绑定来源证据，已移除"
        return replace(
            assessment,
            body_benchmark=None,
            body_benchmark_evidence=(),
            body_benchmark_boundaries=(),
            limitations=tuple(dict.fromkeys(assessment.limitations + (limitation,))),
        )
    return assessment


def enforce_analysis_boundaries(analysis: BasicAnalysis) -> BasicAnalysis:
    """清理分析器输出中不能由实际证据支持的确定性结论。"""
    _validate_interaction_evidence(analysis)
    visual_is_readable = (
        analysis.content.media_read_result.status == MediaReadStatus.READABLE
    )
    _validate_generated_claims(
        (
            analysis.topic,
            analysis.summary,
            *analysis.structure,
            *analysis.persuasion_chain,
            *(method.name for method in analysis.reusable_methods),
            *(method.description for method in analysis.reusable_methods),
            *(method.method_key for method in analysis.reusable_methods),
            *(item.statement for item in analysis.source_information.judgments),
        ),
        visual_is_readable=visual_is_readable,
    )
    if not visual_is_readable and any(
        _contains_visual_claim(fact.statement)
        for fact in analysis.source_information.facts
    ):
        raise ValueError("来源事实包含没有可读画面支持的视觉结论")
    _validate_source_information_roles(
        analysis.source_information,
        visual_is_readable=visual_is_readable,
    )
    _validate_limitation_role(
        tuple(
            value
            for value in (
                analysis.undetermined_reason,
                analysis.opening.unavailable_reason,
            )
            if value is not None
        ),
        visual_is_readable=visual_is_readable,
    )
    _validate_boundary_claims(
        tuple(
            boundary.statement
            for method in analysis.reusable_methods
            for boundary in method.applicable_boundaries
        )
        + tuple(
            item.statement
            for item in analysis.source_information.source_constraints
        )
        + tuple(
            item.statement
            for item in analysis.opening.applicable_boundaries
        ),
        visual_is_readable=visual_is_readable,
    )
    if not isinstance(analysis.category, ContentCategory):
        raise ValueError("内容分类只能为人设、千川或无法判断")
    if analysis.category == ContentCategory.UNDETERMINED and not analysis.undetermined_reason:
        raise ValueError("无法判断主分类时必须说明原因")

    has_transcript_input = bool(
        analysis.content.transcript and analysis.content.transcript.strip()
    )
    readable_visual_refs = (
        set(analysis.content.media_read_result.evidence_refs)
        if analysis.content.media_read_result.status == MediaReadStatus.READABLE
        else set()
    )
    opening = analysis.opening
    bound_opening_evidence = tuple(
        item
        for item in opening.evidence
        if (
            item.evidence_type != EvidenceType.TRANSCRIPT
            or has_transcript_input
        )
        and (
            item.evidence_type != EvidenceType.VISUAL
            or item.locator in readable_visual_refs
        )
    )
    expected_opening_evidence = {
        OpeningKind.LANGUAGE: EvidenceType.TRANSCRIPT,
        OpeningKind.FIRST_FRAME: EvidenceType.VISUAL,
    }.get(opening.kind)
    opening_has_matching_evidence = any(
        item.evidence_type == expected_opening_evidence
        for item in bound_opening_evidence
    )
    opening_has_bound_input = (
        opening.kind == OpeningKind.LANGUAGE
        and has_transcript_input
        and bool(
            opening.fragment
            and opening.fragment.strip() in (analysis.content.transcript or "")
        )
        and bool(opening.applicable_boundaries)
        or opening.kind == OpeningKind.FIRST_FRAME
        and bool(readable_visual_refs)
        and bool(opening.applicable_boundaries)
    )
    opening_contains_source_limit = bool(
        (
            opening.fragment
            and _contains_source_limited_fragment(
                opening.fragment,
                analysis.source_information,
            )
        )
        or any(
            _contains_source_limited_fragment(
                item.statement,
                analysis.source_information,
            )
            for item in opening.applicable_boundaries
        )
    )
    opening_contains_unsupported_claim = bool(
        (
            opening.fragment
            and _contains_unsupported_performance_claim(opening.fragment)
        )
        or any(
            not _boundary_claim_is_valid(
                item.statement,
                visual_is_readable=visual_is_readable,
            )
            for item in opening.applicable_boundaries
        )
    )
    if opening.status == OpeningTagStatus.AVAILABLE and not (
        opening_has_matching_evidence
        and opening_has_bound_input
        and not opening_contains_source_limit
        and not opening_contains_unsupported_claim
    ):
        opening = OpeningAnnotation(
            status=OpeningTagStatus.UNAVAILABLE,
            kind=opening.kind,
            unavailable_reason=(
                (
                    "没有非空转写输入，无法判断语言开头"
                    if not has_transcript_input
                    else (
                        "没有转写证据，无法判断语言开头"
                        if not opening_has_matching_evidence
                        else (
                            "开头包含输入无法支持的效果或趋势结论"
                            if opening_contains_unsupported_claim
                            else (
                                "开头含来源限定信息，不能跨项目直接使用"
                                if opening_contains_source_limit
                                else "开头片段无法回到转写证据或缺少适用边界"
                            )
                        )
                    )
                )
                if opening.kind == OpeningKind.LANGUAGE
                else "没有可读画面证据，无法判断第一画面"
            ),
        )
    elif bound_opening_evidence != opening.evidence:
        opening = replace(opening, evidence=bound_opening_evidence)

    visual_shots = tuple(
        item
        for item in analysis.shot_observations
        if item.evidence_type == EvidenceType.VISUAL
        and item.locator in readable_visual_refs
    )
    opening_has_visual = any(
        item.evidence_type == EvidenceType.VISUAL
        for item in opening.evidence
    )
    has_visual_evidence = opening_has_visual or bool(visual_shots)
    limitation = SourceLimitation(
        statement=(
            "没有可读画面证据，镜头与第一画面结论受限"
            if not has_visual_evidence
            else "缺少视觉依据的镜头或第一画面结论已移除"
        )
    )
    source_information = analysis.source_information
    reusable_methods = tuple(
        method
        for method in analysis.reusable_methods
        if is_reusable_method_safe(method, analysis.source_information)
        and all(_evidence_is_bound(item, analysis) for item in method.evidence)
    )
    structure = tuple(
        item
        for item in analysis.structure
        if not _contains_source_limited_fragment(item, analysis.source_information)
    )
    persuasion_chain = tuple(
        item
        for item in analysis.persuasion_chain
        if not _contains_source_limited_fragment(item, analysis.source_information)
    )
    topic = (
        None
        if analysis.topic
        and _contains_source_limited_fragment(
            analysis.topic,
            analysis.source_information,
        )
        else analysis.topic
    )
    summary = (
        None
        if analysis.summary
        and _contains_source_limited_fragment(
            analysis.summary,
            analysis.source_information,
        )
        else analysis.summary
    )
    boundary_changed = (
        opening != analysis.opening
        or visual_shots != analysis.shot_observations
        or not has_visual_evidence
    )
    if boundary_changed and limitation not in source_information.limitations:
        source_information = replace(
            source_information,
            limitations=source_information.limitations + (limitation,),
        )
    return replace(
        analysis,
        opening=opening,
        shot_observations=visual_shots,
        source_information=source_information,
        reusable_methods=reusable_methods,
        topic=topic,
        summary=summary,
        structure=structure,
        persuasion_chain=persuasion_chain,
    )
