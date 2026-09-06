"""内容分析日报和周报的确定性渲染与飞书文档幂等投递。"""
import json
from typing import Mapping, Protocol, Any

from .executor import DeliveryIdentity
from .runtime_contract import (
    AccountExecution,
    ContentAnalysisTaskEnvelope,
    DeliveryScope,
    ProjectExecution,
    WeeklyBatchFinalizeExecution,
)


class FeishuDocumentGateway(Protocol):
    """飞书文档创建和指定业务区块更新边界。"""

    async def create_document(
        self,
        *,
        root_ref: str,
        relative_directory: str,
        document_key: str,
        title: str,
        section_key: str,
        markdown: str,
    ) -> DeliveryIdentity: ...

    async def update_document(
        self,
        *,
        document_id: str,
        document_key: str,
        title: str,
        section_key: str,
        markdown: str,
    ) -> DeliveryIdentity: ...


def _text_list(value: object, *, field: str = "statement") -> str:
    if not isinstance(value, list) or not value:
        return "无"
    texts = []
    for item in value:
        if isinstance(item, Mapping):
            text = item.get(field)
        else:
            text = item
        if text is not None and str(text).strip():
            texts.append(str(text))
    return "；".join(texts) or "无"


def _opportunity_markdown(
    items: object,
    *,
    library_keys: set[str],
) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["无"]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("日报机会结构无效")
        analysis = item.get("analysis")
        assessment = item.get("assessment")
        if not isinstance(analysis, Mapping) or not isinstance(assessment, Mapping):
            raise ValueError("日报机会缺少分析或项目判断")
        content = analysis.get("content")
        if not isinstance(content, Mapping):
            raise ValueError("日报机会缺少原始内容")
        identity = content.get("identity") if isinstance(content.get("identity"), Mapping) else {}
        metrics = content.get("metrics") if isinstance(content.get("metrics"), Mapping) else {}
        opening = analysis.get("opening") if isinstance(analysis.get("opening"), Mapping) else {}
        source = analysis.get("source_information")
        source = source if isinstance(source, Mapping) else {}
        stable_key = str(item.get("stable_key") or "")
        source_link = (
            identity.get("external_url")
            or content.get("operations_review_url")
            or identity.get("platform_content_id")
            or "无可用链接或作品编号"
        )
        lines.extend(
            (
                f"### {index}. {analysis.get('topic') or content.get('title') or '未命名机会'}",
                f"- 原始来源：{source_link}",
                f"- 发布时间/采集时间：{content.get('published_at') or '未知'} / {content.get('captured_at') or '未知'}",
                "- 当前互动：点赞 {like}、评论 {comment}、分享 {share}、收藏 {favorite}".format(
                    like=metrics.get("like_count"),
                    comment=metrics.get("comment_count"),
                    share=metrics.get("share_count"),
                    favorite=metrics.get("favorite_count"),
                ),
                f"- 主分类：{analysis.get('category') or 'undetermined'}",
                f"- 项目适配理由：{_text_list(assessment.get('fit_reasons'))}",
                f"- 选题：{analysis.get('topic') or '无法判断'}",
                f"- 开头：状态 {opening.get('status') or '未知'}；片段 {opening.get('fragment') or '无'}；原因 {opening.get('unavailable_reason') or '无'}",
                f"- 内容结构：{_text_list(analysis.get('structure'), field='')}",
                f"- 转化说服链：{_text_list(analysis.get('persuasion_chain'), field='')}",
                f"- 互动观察：{json.dumps(analysis.get('interaction_observations') or [], ensure_ascii=False, sort_keys=True)}",
                f"- 可复用方法：{_text_list(analysis.get('reusable_methods'), field='description')}",
                f"- 来源事实：{_text_list(source.get('facts'))}",
                f"- 来源判断：{_text_list(source.get('judgments'))}",
                f"- 来源假设：{_text_list(source.get('assumptions'))}",
                f"- 来源限制：{_text_list(source.get('limitations'))}",
                f"- 来源适用边界：{_text_list(source.get('source_constraints'))}",
                f"- 推荐动作：{assessment.get('recommended_action') or '无'}",
                f"- 判断依据：{_text_list(assessment.get('decision_basis'), field='')}",
                f"- 数据成熟度/可信程度：{analysis.get('data_maturity') or '未知'} / {assessment.get('confidence') or analysis.get('confidence') or '未知'}",
                "- 项目内容库入库状态："
                + (
                    "已入库或本次入库"
                    if item.get("in_library") is True or stable_key in library_keys
                    else "未入库"
                ),
            )
        )
    return lines


def _daily_markdown(
    envelope: ContentAnalysisTaskEnvelope,
    result_id: int,
    payload: Mapping[str, Any],
) -> str:
    project_id = envelope.execution.project_id
    report = payload.get("reports", {}).get(project_id)
    if not isinstance(report, Mapping):
        raise ValueError("日报结构化结果缺少当前项目")
    overview = report.get("daily_overview") or {}
    persona = report.get("persona_opportunities") or []
    qianchuan = report.get("qianchuan_opportunities") or []
    library = report.get("library_candidates") or []
    cross = report.get("cross_project_candidates") or []
    syncs = report.get("sync_results") or []
    manual_opening_supplements = payload.get("manual_opening_supplements") or []
    metadata = payload.get("run_metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    library_keys = {
        str(item.get("stable_key"))
        for item in library
        if isinstance(item, Mapping) and item.get("stable_key")
    }
    checked_accounts = "、".join(
        str(item.get("account_id"))
        for item in syncs
        if isinstance(item, Mapping) and item.get("account_id")
    ) or "无"
    categories = overview.get("categories") if isinstance(overview.get("categories"), Mapping) else {}
    interactions = overview.get("interactions") if isinstance(overview.get("interactions"), Mapping) else {}
    no_content = report.get("no_content_summary")
    no_content = no_content if isinstance(no_content, Mapping) else None
    limitation_codes = metadata.get("limitation_codes")
    limitation_codes = (
        [str(item) for item in limitation_codes]
        if isinstance(limitation_codes, list)
        else []
    )
    project_name = metadata.get("project_name")
    project_label = (
        f"{project_name}（{project_id}）"
        if isinstance(project_name, str) and project_name.strip()
        else project_id
    )
    lines = [
        f"# 项目 {project_label} 内容分析日报",
        "",
        "## 运行元信息",
        f"- 项目：{project_label}（上下文版本 {report.get('context_version') or '未知'}）",
        f"- 业务日期：{metadata.get('business_date') or envelope.business_date.isoformat()}",
        f"- 分析窗口：[ {metadata.get('window_start') or envelope.window_start.isoformat()}，{metadata.get('window_end') or envelope.window_end.isoformat()} )，北京时间",
        f"- 运行类型/任务编号：{metadata.get('run_type') or envelope.run_type.value} / {metadata.get('task_no') or envelope.task_no}",
        f"- 生成时间：{metadata.get('generated_at') or '未知'}",
        f"- 关系表/内容表读取时间：{metadata.get('relation_read_at') or '未知'} / {metadata.get('content_read_at') or '未知'}",
        f"- 数据完整性：{'完整' if metadata.get('data_complete') is True else '受限'}",
        f"- 平台结构化结果入口：内部结果 {result_id}",
        "",
        "## 1. 日报摘要",
        str(report.get("summary") or "暂无摘要"),
        "",
        "## 2. 当日内容概览",
        f"- 发布内容：{overview.get('content_count', 0)}",
        f"- 分类：人设 {categories.get('persona', 0)}、千川 {categories.get('qianchuan', 0)}、无法判断 {categories.get('undetermined', 0)}",
        f"- 互动概览：{json.dumps(interactions, ensure_ascii=False, sort_keys=True)}",
        f"- 已检查账号：{checked_accounts}",
        f"- 人设机会：{len(persona)}",
        f"- 千川机会：{len(qianchuan)}",
        f"- 内容库新增：{len(library)}",
        f"- 跨项目机会新增：{len(cross)}",
        f"- 人工千川开头补标：{len(manual_opening_supplements)}",
        *(
            (
                f"- 内容源读取成功：{'是' if no_content.get('read_succeeded') is True else '否'}",
                f"- 无内容覆盖窗口：{json.dumps(no_content.get('coverage_window') or {}, ensure_ascii=False, sort_keys=True)}",
                f"- 读取完成时间：{no_content.get('read_completed_at') or '未知'}",
            )
            if no_content is not None
            else ()
        ),
        "",
        "## 3. 近3日业务状态变化",
        *_opportunity_markdown(report.get("previous_two_day_changes"), library_keys=library_keys),
        "",
        "## 4. 人设内容机会",
        *_opportunity_markdown(persona, library_keys=library_keys),
        "",
        "## 5. 千川内容机会",
        *_opportunity_markdown(qianchuan, library_keys=library_keys),
        "",
        "## 6. 跨项目机会",
        *(
            [
                f"- {item.get('method', {}).get('name') or item.get('method', {}).get('method_key') or '未命名方法'}：适用场景 {_text_list(item.get('scenarios'), field='')}；来源 {json.dumps(item.get('sources') or [], ensure_ascii=False, sort_keys=True)}"
                for item in cross
                if isinstance(item, Mapping)
            ]
            or ["无"]
        ),
        "",
        "## 7. 数据与限制说明",
        f"- 关系问题：{_text_list(report.get('relation_issues'), field='')}",
        f"- 数据限制：{_text_list(report.get('data_issues'), field='')}",
        f"- 限制代码：{'、'.join(limitation_codes) if limitation_codes else '无'}",
        f"- 本次内容库新增：{len(library)}；本项目跨项目机会新增或更新：{len(cross)}",
    ]
    return "\n".join(lines)


def _mark_test(markdown: str) -> str:
    return "# 【测试结果，不生效】\n\n" + markdown


def _weekly_batch_markdown(
    execution: WeeklyBatchFinalizeExecution,
    payload: Mapping[str, Any],
) -> str:
    batch_summary = payload.get("batch_summary")
    batch_summary = batch_summary if isinstance(batch_summary, Mapping) else {}
    metadata = payload.get("run_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    lines = [
            "# 公司级账号基准周报",
            "",
            "## 公司级周批汇总",
            f"批次：{execution.weekly_batch_id}",
            f"统计窗口：{metadata.get('window_start') or '未知'} 至 {metadata.get('window_end') or '未知'}",
            f"汇总时间：{metadata.get('generated_at') or '未知'}",
            f"纳入项目：{'、'.join(str(item) for item in batch_summary.get('selected_project_ids', [])) or '无'}",
            f"去重账号：{batch_summary.get('account_count', execution.batch_size)}",
            f"成功账号：{batch_summary.get('success_account_count', 0)}",
            f"无内容账号：{batch_summary.get('no_content_account_count', 0)}",
            f"失败账号：{batch_summary.get('failed_account_count', 0)}",
            f"待处理账号：{batch_summary.get('pending_account_count', 0)}",
            f"可计算账号：{batch_summary.get('calculable_account_count', 0)}",
            f"不可计算原因：{batch_summary.get('unavailable_reason') or '无'}",
            f"失败说明：{json.dumps(batch_summary.get('failures') or [], ensure_ascii=False, sort_keys=True)}",
            "",
            "## 每账号基准",
    ]
    account_results = batch_summary.get("account_results")
    account_results = account_results if isinstance(account_results, list) else []
    if not account_results:
        lines.append("本批次没有账号实例。")
    for item in account_results:
        if not isinstance(item, Mapping):
            continue
        sample_count = item.get("sample_count")
        calculable = type(sample_count) is int and sample_count > 0
        status_label = {
            "success": "成功",
            "no_content": "无内容",
            "failed": "失败",
        }.get(item.get("status"), "未知")
        lines.extend(
            (
                f"### 账号 {item.get('account_hash') or item.get('sec_uid') or '未知'}",
                f"状态：{status_label}",
                f"关联项目：{'、'.join(str(value) for value in item.get('project_ids', [])) or '无'}",
                f"样本数：{sample_count if calculable else '不可计算'}",
                f"平均点赞：{item.get('mean_likes') if calculable else '不可计算'}",
                f"中位点赞：{item.get('median_likes') if calculable else '不可计算'}",
                f"最高点赞：{item.get('maximum_likes') if calculable else '不可计算'}",
                f"最低点赞：{item.get('minimum_likes') if calculable else '不可计算'}",
                f"基准更新时间：{item.get('baseline_updated_at') or '无'}",
                f"账号终态时间：{item.get('updated_at') or '未知'}",
                f"不可计算原因：{item.get('unavailable_reason') or '无'}",
                "",
            )
        )
    return "\n".join(lines)


def _weekly_markdown(execution: AccountExecution, payload: Mapping[str, Any]) -> str:
    baseline = payload.get("baseline")
    values = baseline.get("baseline") if isinstance(baseline, Mapping) else None
    project_ids = payload.get("project_ids")
    if not isinstance(project_ids, list) or not project_ids:
        raise ValueError("周报结构化结果缺少实际关联项目")
    lines = [
        f"# 账号 {execution.sec_uid} 周度分析",
        "",
        f"批次位置：{execution.batch_position}/{execution.batch_size}",
        f"关联项目：{'、'.join(str(item) for item in project_ids)}",
        f"窗口内容：{payload.get('content_count', 0)}",
        f"分析失败：{payload.get('analysis_failure_count', 0)}",
        f"统计窗口：{baseline.get('window_start') or '未知'} 至 {baseline.get('window_end') or '未知'}"
        if isinstance(baseline, Mapping)
        else "统计窗口：未知",
        f"更新时间：{baseline.get('updated_at') or '未知'}"
        if isinstance(baseline, Mapping)
        else "更新时间：未知",
        "",
        "## 当前账号基准",
    ]
    if isinstance(values, Mapping):
        lines.extend(
            (
                f"平均点赞：{values.get('mean')}",
                f"中位点赞：{values.get('median')}",
                f"样本数：{values.get('sample_size')}",
                f"最高点赞：{values.get('maximum')}",
                f"最低点赞：{values.get('minimum')}",
            )
        )
    else:
        lines.append("人设点赞基准：不可计算")
        if isinstance(baseline, Mapping):
            lines.append(
                f"不可计算原因：{baseline.get('unavailable_reason') or '未提供'}"
            )
    return "\n".join(lines)


class WeeklyReportPartiallyDeliveredError(RuntimeError):
    """周报已有稳定文档，但汇总或账号区块尚未全部更新。"""

    def __init__(self, identity: DeliveryIdentity) -> None:
        super().__init__("飞书周报区块未完整更新")
        self.delivery_identity = identity


class FeishuReportDelivery:
    """新文档走创建，已有稳定文档身份走区块更新。"""

    def __init__(self, gateway: FeishuDocumentGateway) -> None:
        self._gateway = gateway

    async def deliver(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        result_id: int,
        payload: Mapping[str, Any],
        identity: DeliveryIdentity | None,
    ) -> DeliveryIdentity:
        if identity is not None and (
            identity.document_key != envelope.idempotency.document_key
        ):
            raise ValueError("已有 document_key 与任务不一致")
        execution = envelope.execution
        if isinstance(execution, ProjectExecution):
            metadata = payload.get("run_metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            project_name = metadata.get("project_name")
            project_label = (
                f"{project_name}（{execution.project_id}）"
                if isinstance(project_name, str) and project_name.strip()
                else execution.project_id
            )
            title = f"项目 {project_label} 内容分析日报 {envelope.business_date.isoformat()}"
            section_key = f"project:{execution.project_id}"
            markdown = _daily_markdown(envelope, result_id, payload)
        elif isinstance(execution, AccountExecution):
            title = f"内容分析周报 {envelope.business_date.isoformat()}"
            section_key = f"account:{execution.sec_uid}"
            markdown = _weekly_markdown(execution, payload)
        elif isinstance(execution, WeeklyBatchFinalizeExecution):
            title = f"内容分析周报 {envelope.business_date.isoformat()}"
            section_key = "batch-summary"
            markdown = _weekly_batch_markdown(execution, payload)
        else:  # pragma: no cover - 信封闭集已在运行合同校验
            raise ValueError("周任务执行对象不受支持")
        if envelope.delivery_target.scope is DeliveryScope.TEST:
            title = f"【测试】{title}"
            markdown = _mark_test(markdown)
        if isinstance(execution, AccountExecution):
            try:
                if identity is None or not identity.document_id:
                    return await self._gateway.create_document(
                        root_ref=envelope.delivery_target.report_root_ref,
                        relative_directory=envelope.delivery_target.relative_directory,
                        document_key=envelope.idempotency.document_key,
                        title=title,
                        section_key=section_key,
                        markdown=markdown,
                    )
                return await self._gateway.update_document(
                    document_id=identity.document_id,
                    document_key=envelope.idempotency.document_key,
                    title=title,
                    section_key=section_key,
                    markdown=markdown,
                )
            except Exception as exc:
                partial_identity = getattr(exc, "delivery_identity", None) or identity
                if isinstance(partial_identity, DeliveryIdentity):
                    raise WeeklyReportPartiallyDeliveredError(
                        partial_identity
                    ) from exc
                raise
        if identity is None or not identity.document_id:
            return await self._gateway.create_document(
                root_ref=envelope.delivery_target.report_root_ref,
                relative_directory=envelope.delivery_target.relative_directory,
                document_key=envelope.idempotency.document_key,
                title=title,
                section_key=section_key,
                markdown=markdown,
            )
        return await self._gateway.update_document(
            document_id=identity.document_id,
            document_key=envelope.idempotency.document_key,
            title=title,
            section_key=section_key,
            markdown=markdown,
        )
