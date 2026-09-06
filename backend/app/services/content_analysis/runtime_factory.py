"""从部署环境装配内容分析执行侧，不读取页面级输入表配置。"""
import os
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .executor import ContentAnalysisExecutor
from .feishu_adapter import FeishuContentReader, FeishuContentTableConfig
from .feishu_client import FeishuAppCredentials, HttpxFeishuReadonlyClient
from .feishu_document_gateway import HttpxFeishuDocumentGateway
from .feishu_relation import FeishuRelationReader, FeishuRelationTableConfig
from .model_analyzer import (
    StructuredModelContentAnalyzer,
    YunwuContentAnalysisModelClient,
)
from .persistence import SqlContentAnalysisStore
from .project_context import SqlProjectContextReader
from .report_delivery import FeishuReportDelivery
from .task_config_adapter import ContentAnalysisTaskConfigAdapter


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ContentAnalysisRuntimeConfig:
    """固定输入表、应用凭据、模型和系统账号的部署配置。"""

    credentials: FeishuAppCredentials
    content_table: FeishuContentTableConfig
    relation_table: FeishuRelationTableConfig
    model_id: str
    model_provider: str
    system_user_id: int

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, str] = os.environ,
    ) -> "ContentAnalysisRuntimeConfig":
        names = {
            "app_id": "CONTENT_ANALYSIS_FEISHU_APP_ID",
            "app_secret": "CONTENT_ANALYSIS_FEISHU_APP_SECRET",
            "content_app": "CONTENT_ANALYSIS_FEISHU_CONTENT_APP_TOKEN",
            "content_table": "CONTENT_ANALYSIS_FEISHU_CONTENT_TABLE_ID",
            "relation_app": "CONTENT_ANALYSIS_FEISHU_RELATION_APP_TOKEN",
            "relation_table": "CONTENT_ANALYSIS_FEISHU_RELATION_TABLE_ID",
            "model_id": "CONTENT_ANALYSIS_MODEL_ID",
            "model_provider": "CONTENT_ANALYSIS_MODEL_PROVIDER",
            "system_user_id": "CONTENT_ANALYSIS_SYSTEM_USER_ID",
        }
        loaded = {key: values.get(name, "").strip() for key, name in names.items()}
        if any(not value for value in loaded.values()):
            raise ValueError("内容分析运行配置不完整")
        try:
            system_user_id = int(loaded["system_user_id"])
        except ValueError as exc:
            raise ValueError("内容分析运行配置中的系统账号无效") from exc
        if system_user_id <= 0:
            raise ValueError("内容分析运行配置中的系统账号无效")
        return cls(
            credentials=FeishuAppCredentials(
                loaded["app_id"],
                loaded["app_secret"],
            ),
            content_table=FeishuContentTableConfig(
                loaded["content_app"],
                loaded["content_table"],
            ),
            relation_table=FeishuRelationTableConfig(
                loaded["relation_app"],
                loaded["relation_table"],
            ),
            model_id=loaded["model_id"],
            model_provider=loaded["model_provider"],
            system_user_id=system_user_id,
        )


def build_content_analysis_executor(
    session: AsyncSession,
    http: httpx.AsyncClient,
    config: ContentAnalysisRuntimeConfig,
) -> ContentAnalysisTaskConfigAdapter:
    """使用一次调用独占的会话与客户端装配执行操作。"""
    feishu = HttpxFeishuReadonlyClient(http, config.credentials)
    analyzer = StructuredModelContentAnalyzer(
        YunwuContentAnalysisModelClient(
            session,
            model_id=config.model_id,
            provider=config.model_provider,
            user_id=config.system_user_id,
        )
    )
    clock = lambda: datetime.now(SHANGHAI)
    executor = ContentAnalysisExecutor(
        relation_reader=FeishuRelationReader(
            feishu,
            config.relation_table,
            clock=clock,
        ),
        content_reader=FeishuContentReader(
            feishu,
            config.content_table,
            clock=clock,
        ),
        context_reader=SqlProjectContextReader(session),
        analyzer=analyzer,
        store=SqlContentAnalysisStore(session, clock=clock),
        delivery=FeishuReportDelivery(HttpxFeishuDocumentGateway(http, feishu)),
        system_user_id=config.system_user_id,
        clock=clock,
    )
    return ContentAnalysisTaskConfigAdapter(executor)


def _runtime_unavailable_result(
    _raw_envelope: object,
    *,
    delivery_only: bool = False,
) -> dict:
    relation = {"status": "skipped"}
    if delivery_only:
        return {
            "failure_stage": "delivery",
            "feishu_relation": relation,
            "internal_result": {"status": "skipped"},
            "delivery": {
                "status": "failed",
                "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
            },
        }
    return {
        "failure_stage": "internal_result",
        "feishu_relation": relation,
        "internal_result": {
            "status": "failed",
            "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        },
        "delivery": {"status": "skipped"},
    }


async def _rollback_and_close_session(session: AsyncSession) -> None:
    try:
        await session.rollback()
    finally:
        await session.close()


class ContentAnalysisRuntimeProvider:
    """为每次任务调用创建并释放独立数据库与网络资源。"""

    def __init__(
        self,
        *,
        config_loader: Callable[[], ContentAnalysisRuntimeConfig],
        session_factory: Callable[[], AsyncSession],
        http_factory: Callable[[], httpx.AsyncClient],
    ) -> None:
        self._config_loader = config_loader
        self._session_factory = session_factory
        self._http_factory = http_factory
        self._closed = False

    async def _invoke(self, operation: str, *args) -> dict:
        if self._closed:
            return _runtime_unavailable_result(
                args[0] if args else None,
                delivery_only=operation == "redeliver",
            )
        try:
            config = self._config_loader()
            async with AsyncExitStack() as resources:
                session = self._session_factory()
                resources.push_async_callback(_rollback_and_close_session, session)
                http = self._http_factory()
                resources.push_async_callback(http.aclose)
                adapter = build_content_analysis_executor(session, http, config)
                if operation == "execute":
                    return await adapter.execute(args[0])
                return await adapter.redeliver(args[0], args[1], args[2])
        except Exception:
            return _runtime_unavailable_result(
                args[0] if args else None,
                delivery_only=operation == "redeliver",
            )

    async def aclose(self) -> None:
        """停止接受新调用；单次调用资源已由各自上下文负责关闭。"""
        self._closed = True

    async def execute(self, raw_envelope: dict) -> dict:
        return await self._invoke("execute", raw_envelope)

    async def redeliver(
        self,
        raw_envelope: dict,
        internal_result_id: str,
        delivery_identity: str,
    ) -> dict:
        return await self._invoke(
            "redeliver",
            raw_envelope,
            internal_result_id,
            delivery_identity,
        )


def build_content_analysis_runtime_provider(
    values: Mapping[str, str] = os.environ,
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    http_factory: Callable[[], httpx.AsyncClient] | None = None,
) -> ContentAnalysisRuntimeProvider:
    """构造可长期注册的入口；资源只在单次调用开始后创建。"""
    if session_factory is None:
        from app.core.database import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    if http_factory is None:
        http_factory = lambda: httpx.AsyncClient(
            base_url="https://open.feishu.cn",
            timeout=30.0,
        )
    return ContentAnalysisRuntimeProvider(
        config_loader=lambda: ContentAnalysisRuntimeConfig.from_mapping(values),
        session_factory=session_factory,
        http_factory=http_factory,
    )
