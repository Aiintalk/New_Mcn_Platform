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

    REUSABLE_METHOD = "reusable_method"
    PROJECT_RELEVANCE = "project_relevance"
    CONVERSION_STRUCTURE = "conversion_structure"


@dataclass(frozen=True)
class ProjectAssessment:
    """分析器对一个明确项目上下文作出的适配判断。"""

    project_id: str
    context_version: str
    is_fit: bool
    confidence: ConfidenceLevel
    conclusion: str
    is_opportunity: bool = False
    should_add_to_library: bool = False
    priority: int | None = None
    body_benchmark: str | None = None
    value_signals: tuple[CandidateValueSignal, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(signal, CandidateValueSignal)
            for signal in self.value_signals
        ):
            raise ValueError("候选价值信号必须使用封闭枚举")


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

    opening = analysis.opening
    expected_opening_evidence = {
        OpeningKind.LANGUAGE: EvidenceType.TRANSCRIPT,
        OpeningKind.FIRST_FRAME: EvidenceType.VISUAL,
    }.get(opening.kind)
    opening_has_matching_evidence = any(
        item.evidence_type == expected_opening_evidence for item in opening.evidence
    )
    if opening.status == OpeningTagStatus.AVAILABLE and not opening_has_matching_evidence:
        opening = OpeningAnnotation(
            status=OpeningTagStatus.UNAVAILABLE,
            kind=opening.kind,
            unavailable_reason=(
                "没有转写证据，无法判断语言开头"
                if opening.kind == OpeningKind.LANGUAGE
                else "没有可读画面证据，无法判断第一画面"
            ),
        )

    visual_shots = tuple(
        item
        for item in analysis.shot_observations
        if item.evidence_type == EvidenceType.VISUAL
    )
    opening_has_visual = any(
        item.evidence_type == EvidenceType.VISUAL
        for item in analysis.opening.evidence
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
