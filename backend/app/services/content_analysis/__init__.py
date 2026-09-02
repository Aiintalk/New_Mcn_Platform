"""内容分析阶段一的纯领域内核。"""

from .analyzer import ContentAnalyzer, ProjectAssessment, enforce_analysis_boundaries
from .deterministic import (
    deduplicate_contents,
    derive_windows,
    normalize_play_count,
    persona_like_baseline,
    qianchuan_top_three,
)
from .engine import (
    AccountSyncResult,
    ContentAnalysisEngine,
    CrossProjectCandidate,
    EngineResult,
    InteractionOverview,
    LibraryCandidate,
    MetricSummary,
    ProjectDailyReport,
    ReportItem,
    SavedBusinessState,
)
from .domain import (
    AnalysisWindows,
    BasicAnalysis,
    ContentCategory,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    LikeBaseline,
)

__all__ = [
    "AnalysisWindows",
    "AccountSyncResult",
    "BasicAnalysis",
    "ContentAnalysisEngine",
    "ContentAnalyzer",
    "ContentCategory",
    "ContentIdentity",
    "ContentRecord",
    "ContentSource",
    "EngagementMetrics",
    "LikeBaseline",
    "CrossProjectCandidate",
    "EngineResult",
    "InteractionOverview",
    "LibraryCandidate",
    "MetricSummary",
    "ProjectAssessment",
    "ProjectDailyReport",
    "ReportItem",
    "SavedBusinessState",
    "deduplicate_contents",
    "derive_windows",
    "enforce_analysis_boundaries",
    "normalize_play_count",
    "persona_like_baseline",
    "qianchuan_top_three",
]
