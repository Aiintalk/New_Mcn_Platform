"""可注入智能分析协议，以及不依赖模型的输出边界清理。"""
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from .domain import (
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentRecord,
    EvidenceType,
    OpeningAnnotation,
    OpeningKind,
    OpeningTagStatus,
    ProjectContextVersion,
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
        if not self.statement.strip():
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
    value_signals: tuple[CandidateValueSignal, ...] = ()
    fit_reasons: tuple[ProjectFitReason, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.is_opportunity and not self.is_fit:
            raise ValueError("项目机会必须同时满足项目适配")
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


def enforce_analysis_boundaries(analysis: BasicAnalysis) -> BasicAnalysis:
    """清理分析器输出中不能由实际证据支持的确定性结论。"""
    if not isinstance(analysis.category, ContentCategory):
        raise ValueError("内容分类只能为人设、千川或无法判断")
    if analysis.category == ContentCategory.UNDETERMINED and not analysis.undetermined_reason:
        raise ValueError("无法判断主分类时必须说明原因")

    has_transcript_input = bool(
        analysis.content.transcript and analysis.content.transcript.strip()
    )
    has_video_reference = bool(
        analysis.content.video_reference
        and analysis.content.video_reference.strip()
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
            or has_video_reference
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
        or opening.kind == OpeningKind.FIRST_FRAME
        and has_video_reference
    )
    if opening.status == OpeningTagStatus.AVAILABLE and not (
        opening_has_matching_evidence and opening_has_bound_input
    ):
        opening = OpeningAnnotation(
            status=OpeningTagStatus.UNAVAILABLE,
            kind=opening.kind,
            unavailable_reason=(
                (
                    "没有非空转写输入，无法判断语言开头"
                    if not has_transcript_input
                    else "没有转写证据，无法判断语言开头"
                )
                if opening.kind == OpeningKind.LANGUAGE
                else (
                    "没有视频引用，无法判断第一画面"
                    if not has_video_reference
                    else "没有可读画面证据，无法判断第一画面"
                )
            ),
        )
    elif bound_opening_evidence != opening.evidence:
        opening = replace(opening, evidence=bound_opening_evidence)

    visual_shots = tuple(
        item
        for item in analysis.shot_observations
        if has_video_reference and item.evidence_type == EvidenceType.VISUAL
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
    )
