"""复用现有模型调用设施的内容分析结构化适配器。"""
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu

from .analyzer import (
    CandidateValueSignal,
    ProjectAssessment,
    CrossProjectSignal,
    ProjectFitDimension,
    ProjectFitReason,
)
from .domain import (
    AnalysisEvidence,
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentRecord,
    DataMaturity,
    EvidenceType,
    InteractionMetric,
    InteractionObservation,
    InteractionObservationType,
    OpeningAnnotation,
    OpeningKind,
    OpeningTagStatus,
    RelativePerformanceLevel,
    ReusableMethod,
    SourceAssumption,
    SourceConstraint,
    SourceFact,
    SourceFactKind,
    SourceInformation,
    SourceJudgment,
    SourceLimitation,
    ProjectContextVersion,
)


class JsonModelClient(Protocol):
    async def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        feature: str,
    ) -> str: ...


_BASIC_RESPONSE_CONTRACT = """只返回一个 JSON 对象，必须包含：
- category: persona|qianchuan|undetermined；confidence: high|medium|low|unverified。
- opening: {status: unannotated|available|unavailable, kind: null|language, fragment: null|文本,
  evidence: [{evidence_type: title|transcript|metadata, locator: 文本, detail: 文本}],
  unavailable_reason: null|文本, applicable_boundaries: [{statement: 文本}]}。
- source_information: {facts: [{statement, source, kind, restricted_fragments: []}],
  judgments: [{statement}], assumptions: [{statement}], limitations: [{statement}],
  source_constraints: [{statement}]}。
- facts.kind 只能取 brand、product、price、promotion、efficacy、proof、product_claim、
  person_identity、personal_experience、other；除 other 外必须给出事实原文中的具体
  restricted_fragments，不能只写“商品”“视频”等泛词；没有来源事实时返回空数组。
- reusable_methods: [{name, description, method_key, evidence: [], applicable_boundaries: []}]。
- topic、summary、undetermined_reason 为文本或 null；structure、persuasion_chain 为文本数组；
  interaction_observations 只能使用以下四种互斥结构：
  1) {observation_type: current_value, metric, current_value}；
  2) {observation_type: current_relative_performance, metric, relative_level,
      benchmark_value?: 数字, sample_size?: 整数}；
  3) {observation_type: current_composition, numerator_metric, numerator_value,
      denominator_metric, denominator_value}；
  4) {observation_type: data_maturity, maturity}。
  metric 只能取 like、comment、share、favorite；relative_level 只能取 above、near、below、unknown；
  maturity 只能取 early、initial、qualitative。没有可靠观察时返回空数组。
  无法判断时 category 必须为 undetermined 并给出原因。
只依据标题、转写和 like/comment/share/favorite 四项当前互动；不得补充输入外事实。"""


_PROJECT_RESPONSE_CONTRACT = """只返回一个 JSON 对象，必须包含：
- is_fit、is_opportunity 为 JSON 布尔值；confidence 为 high|medium|low|unverified；
  conclusion 为非空文本；priority 为非负整数或 null。
- body_benchmark 为文本或 null；非空时 body_benchmark_evidence 与
  body_benchmark_boundaries 必须分别提供来源证据和适用边界。
- value_signals 只能取 early_data_strength、relative_benchmark_outperformance、
  novel_topic_or_structure、clear_traffic_hook、reusable_conversion_structure。
- cross_project_signals 只能取 strong_engagement、novel_content_method、
  reusable_conversion_structure、explicit_cross_project_fit、shared_content_problem_solution；
  cross_project_scenarios 为 [{statement}]，只有明确说明其他项目、商品或共同内容场景时才填写；
  普通项目适配理由和 clear_traffic_hook 不能替代跨项目信号或场景，无依据时两者都返回空数组。
- fit_reasons 为 [{dimension, statement}]，dimension 只能取 project_persona、
  target_users、content_plan、operating_direction；limitations、decision_basis 为文本数组；
  recommended_action 为文本或 null。
只依据结构化内容分析和当前项目上下文；空上下文字段必须写入 limitations。"""


class YunwuContentAnalysisModelClient:
    """通过 yunwu.chat 复用凭据池及 AiCallLog。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        model_id: str,
        provider: str,
        user_id: int,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("内容分析模型配置缺失")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("内容分析模型供应商配置缺失")
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("内容分析模型调用账号配置缺失")
        self._session = session
        self._model_id = model_id
        self._provider = provider
        self._user_id = user_id

    async def complete_json(self, messages, *, feature: str) -> str:
        return await yunwu.chat(
            messages,
            self._session,
            self._model_id,
            provider=self._provider,
            user_id=self._user_id,
            feature=feature,
            temperature=0.1,
            max_tokens=4096,
        )


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"模型字段 {field_name} 必须是对象")
    return value


def _tuple(value: object, field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise ValueError(f"模型字段 {field_name} 必须是数组")
    return tuple(value)


def _parse_json(value: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("模型必须返回单个合法 JSON 对象") from exc
    return _mapping(parsed, "root")


def _json_value(value: object) -> object:
    """把领域对象转换成模型输入可用的 JSON 值。"""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _evidence(value: object) -> AnalysisEvidence:
    item = _mapping(value, "evidence")
    return AnalysisEvidence(
        evidence_type=EvidenceType(item.get("evidence_type")),
        locator=item.get("locator"),
        detail=item.get("detail"),
    )


def _constraints(value: object, field_name: str) -> tuple[SourceConstraint, ...]:
    return tuple(
        SourceConstraint(_mapping(item, field_name).get("statement"))
        for item in _tuple(value, field_name)
    )


def _opening(value: object) -> OpeningAnnotation:
    item = _mapping(value, "opening")
    status = OpeningTagStatus(item.get("status"))
    kind_value = item.get("kind")
    return OpeningAnnotation(
        status=status,
        kind=OpeningKind(kind_value) if kind_value is not None else None,
        fragment=item.get("fragment"),
        evidence=tuple(
            _evidence(entry) for entry in _tuple(item.get("evidence", []), "opening.evidence")
        ),
        unavailable_reason=item.get("unavailable_reason"),
        applicable_boundaries=_constraints(
            item.get("applicable_boundaries", []),
            "opening.applicable_boundaries",
        ),
    )


def parse_source_information(value: object) -> SourceInformation:
    item = _mapping(value, "source_information")
    return SourceInformation(
        facts=tuple(
            SourceFact(
                statement=_mapping(entry, "facts").get("statement"),
                source=_mapping(entry, "facts").get("source"),
                kind=SourceFactKind(_mapping(entry, "facts").get("kind", "other")),
                restricted_fragments=tuple(
                    _tuple(
                        _mapping(entry, "facts").get("restricted_fragments", []),
                        "restricted_fragments",
                    )
                ),
            )
            for entry in _tuple(item.get("facts", []), "facts")
        ),
        judgments=tuple(
            SourceJudgment(_mapping(entry, "judgments").get("statement"))
            for entry in _tuple(item.get("judgments", []), "judgments")
        ),
        assumptions=tuple(
            SourceAssumption(_mapping(entry, "assumptions").get("statement"))
            for entry in _tuple(item.get("assumptions", []), "assumptions")
        ),
        limitations=tuple(
            SourceLimitation(_mapping(entry, "limitations").get("statement"))
            for entry in _tuple(item.get("limitations", []), "limitations")
        ),
        source_constraints=_constraints(
            item.get("source_constraints", []),
            "source_constraints",
        ),
    )


def parse_reusable_method(value: object) -> ReusableMethod:
    item = _mapping(value, "reusable_methods")
    return ReusableMethod(
        name=item.get("name"),
        description=item.get("description"),
        method_key=item.get("method_key"),
        evidence=tuple(
            _evidence(entry) for entry in _tuple(item.get("evidence", []), "method.evidence")
        ),
        applicable_boundaries=_constraints(
            item.get("applicable_boundaries", []),
            "method.applicable_boundaries",
        ),
    )


def _observation(value: object) -> InteractionObservation:
    item = dict(_mapping(value, "interaction_observations"))
    enum_fields = {
        "observation_type": InteractionObservationType,
        "metric": InteractionMetric,
        "relative_level": RelativePerformanceLevel,
        "numerator_metric": InteractionMetric,
        "denominator_metric": InteractionMetric,
        "maturity": DataMaturity,
    }
    for field_name, enum_type in enum_fields.items():
        if item.get(field_name) is not None:
            item[field_name] = enum_type(item[field_name])
    return InteractionObservation(**item)


class StructuredModelContentAnalyzer:
    """将模型 JSON 严格映射为阶段一领域对象。"""

    def __init__(self, client: JsonModelClient) -> None:
        self._client = client

    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        payload = {
            "account_id": content.account_id,
            "identity": {
                "platform_content_id": content.identity.platform_content_id,
                "external_url": content.identity.external_url,
            },
            "title": content.title,
            "transcript": content.transcript,
            "published_at": content.published_at.isoformat(),
            "captured_at": content.captured_at.isoformat(),
            "metrics": {
                "like_count": content.metrics.like_count,
                "comment_count": content.metrics.comment_count,
                "share_count": content.metrics.share_count,
                "favorite_count": content.metrics.favorite_count,
            },
        }
        raw = await self._client.complete_json(
            [
                {
                    "role": "system",
                    "content": _BASIC_RESPONSE_CONTRACT,
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            feature="content_analysis_basic",
        )
        item = _parse_json(raw)
        return BasicAnalysis(
            content=content,
            category=ContentCategory(item.get("category")),
            confidence=ConfidenceLevel(item.get("confidence")),
            opening=_opening(item.get("opening")),
            source_information=parse_source_information(item.get("source_information", {})),
            reusable_methods=tuple(
                parse_reusable_method(entry)
                for entry in _tuple(item.get("reusable_methods", []), "reusable_methods")
            ),
            topic=item.get("topic"),
            summary=item.get("summary"),
            structure=tuple(_tuple(item.get("structure", []), "structure")),
            persuasion_chain=tuple(
                _tuple(item.get("persuasion_chain", []), "persuasion_chain")
            ),
            interaction_observations=tuple(
                _observation(entry)
                for entry in _tuple(
                    item.get("interaction_observations", []),
                    "interaction_observations",
                )
            ),
            undetermined_reason=item.get("undetermined_reason"),
        )

    async def assess_project(
        self,
        analysis: BasicAnalysis,
        project_context: ProjectContextVersion,
    ) -> ProjectAssessment:
        payload = {
            "analysis": _json_value(analysis),
            "project_context": {
                "project_id": project_context.project_id,
                "context_version": project_context.version,
                "project_persona": project_context.project_persona,
                "target_users": project_context.target_users,
                "content_plan": project_context.content_plan,
                "operating_direction": project_context.operating_direction,
                "confirmed_facts": [
                    {"key": fact.key, "value": fact.value}
                    for fact in project_context.confirmed_facts
                ],
            },
        }
        raw = await self._client.complete_json(
            [
                {
                    "role": "system",
                    "content": _PROJECT_RESPONSE_CONTRACT,
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            feature="content_analysis_project",
        )
        item = _parse_json(raw)
        if type(item.get("is_fit")) is not bool or type(
            item.get("is_opportunity")
        ) is not bool:
            raise ValueError("项目适配与机会标记必须是原生布尔值")
        return ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=item["is_fit"],
            confidence=ConfidenceLevel(item.get("confidence")),
            conclusion=item.get("conclusion"),
            is_opportunity=item["is_opportunity"],
            priority=item.get("priority"),
            body_benchmark=item.get("body_benchmark"),
            body_benchmark_evidence=tuple(
                _evidence(entry)
                for entry in _tuple(
                    item.get("body_benchmark_evidence", []),
                    "body_benchmark_evidence",
                )
            ),
            body_benchmark_boundaries=_constraints(
                item.get("body_benchmark_boundaries", []),
                "body_benchmark_boundaries",
            ),
            value_signals=tuple(
                CandidateValueSignal(value)
                for value in _tuple(item.get("value_signals", []), "value_signals")
            ),
            cross_project_signals=tuple(
                CrossProjectSignal(value)
                for value in _tuple(
                    item.get("cross_project_signals", []),
                    "cross_project_signals",
                )
            ),
            cross_project_scenarios=_constraints(
                item.get("cross_project_scenarios", []),
                "cross_project_scenarios",
            ),
            fit_reasons=tuple(
                ProjectFitReason(
                    ProjectFitDimension(_mapping(entry, "fit_reasons").get("dimension")),
                    _mapping(entry, "fit_reasons").get("statement"),
                )
                for entry in _tuple(item.get("fit_reasons", []), "fit_reasons")
            ),
            limitations=tuple(_tuple(item.get("limitations", []), "limitations")),
            recommended_action=item.get("recommended_action"),
            decision_basis=tuple(
                _tuple(item.get("decision_basis", []), "decision_basis")
            ),
        )
