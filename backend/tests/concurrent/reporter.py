"""
并发测试 Markdown 报告生成器。
用法：在测试文件末尾调用 REPORT.record(...)，
pytest session finish 时调用 REPORT.write()。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median, quantiles
from typing import Optional


@dataclass
class TestResult:
    category: str          # "isolation" | "race" | "perf"
    case_id: str           # "ISO-001", "RACE-001", "PERF-login" …
    description: str
    passed: bool
    detail: str = ""       # 失败原因 or 性能数据


@dataclass
class PerfResult:
    endpoint: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float      # 0.0 ~ 1.0
    p95_threshold_ms: float
    p99_threshold_ms: float

    @property
    def verdict(self) -> str:
        if self.error_rate > 0:
            return "❌ FAIL (error_rate > 0)"
        if self.p99_ms > self.p99_threshold_ms:
            return "❌ FAIL (P99 超阈值)"
        if self.p95_ms > self.p95_threshold_ms:
            return "⚠️ WARN (P95 超阈值)"
        return "✅ 通过"


class Reporter:
    def __init__(self):
        self._results: list[TestResult] = []
        self._perf: list[PerfResult] = []
        self._concurrent_users: int = int(os.getenv("CONCURRENT_USERS", "20"))
        self._base_url: str = os.getenv("TEST_BASE_URL", "http://localhost:8000")

    def record(self, result: TestResult) -> None:
        self._results.append(result)

    def record_perf(self, pr: PerfResult) -> None:
        self._perf.append(pr)
        self._results.append(TestResult(
            category="perf",
            case_id=f"PERF-{pr.endpoint.replace('/', '-').strip('-')}",
            description=pr.endpoint,
            passed=pr.verdict.startswith("✅"),
            detail=f"P50={pr.p50_ms:.0f}ms P95={pr.p95_ms:.0f}ms P99={pr.p99_ms:.0f}ms err={pr.error_rate:.1%}",
        ))

    def calc_perf(self, endpoint: str, latencies: list[float],
                  errors: int, p95_thr: float, p99_thr: float) -> PerfResult:
        """从原始延迟列表计算 P50/P95/P99，写入报告。"""
        total = len(latencies) + errors
        sorted_lat = sorted(latencies)
        p50 = median(sorted_lat) if sorted_lat else 0.0
        qs = quantiles(sorted_lat, n=100) if len(sorted_lat) >= 2 else [0.0] * 99
        p95 = qs[94] if len(qs) > 94 else (sorted_lat[-1] if sorted_lat else 0.0)
        p99 = qs[98] if len(qs) > 98 else (sorted_lat[-1] if sorted_lat else 0.0)
        error_rate = errors / total if total > 0 else 0.0
        pr = PerfResult(endpoint, p50, p95, p99, error_rate, p95_thr, p99_thr)
        self.record_perf(pr)
        return pr

    def write(self, path: Optional[str] = None) -> Path:
        if path is None:
            base = Path(__file__).parents[3]  # mcn-platform root
            path = base / "docs" / "tests" / "M1" / "MCN_M1_Concurrent_Test_Report.md"
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self._render(), encoding="utf-8")
        print(f"\n[reporter] 报告已写入 {out}")
        return out

    def _render(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        isolation = [r for r in self._results if r.category == "isolation"]
        race = [r for r in self._results if r.category == "race"]
        perf_results = [r for r in self._results if r.category == "perf"]

        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed

        verdict = "✅ 通过" if failed == 0 else f"❌ 不通过（{failed} 项失败）"

        lines = [
            "# MCN Platform · M1 并发多用户测试报告",
            "",
            f"**测试日期：** {now}  ",
            f"**并发用户数：** {self._concurrent_users}  ",
            f"**测试环境：** {self._base_url}  ",
            "",
            "---",
            "",
            "## 一、数据隔离",
            "",
            "| 编号 | 场景 | 结论 | 说明 |",
            "|------|------|------|------|",
        ]
        for r in isolation:
            icon = "✅" if r.passed else "❌"
            lines.append(f"| {r.case_id} | {r.description} | {icon} | {r.detail} |")

        lines += [
            "",
            "## 二、竞态条件",
            "",
            "| 编号 | 场景 | 结论 | 说明 |",
            "|------|------|------|------|",
        ]
        for r in race:
            icon = "✅" if r.passed else "❌"
            lines.append(f"| {r.case_id} | {r.description} | {icon} | {r.detail} |")

        lines += [
            "",
            "## 三、性能基线",
            "",
            "| 接口 | P50 | P95 | P99 | 错误率 | 结论 |",
            "|------|-----|-----|-----|--------|------|",
        ]
        for pr in self._perf:
            lines.append(
                f"| `{pr.endpoint}` | {pr.p50_ms:.0f}ms | {pr.p95_ms:.0f}ms "
                f"| {pr.p99_ms:.0f}ms | {pr.error_rate:.1%} | {pr.verdict} |"
            )

        lines += [
            "",
            "---",
            "",
            "## 汇总",
            "",
            "| 统计 | 值 |",
            "|------|-----|",
            f"| 总计 | {total} 项 |",
            f"| 通过 | {passed} 项 |",
            f"| 失败 | {failed} 项 |",
            f"| 并发用户数 | {self._concurrent_users} |",
            "",
            f"**测试结论：{verdict}**",
        ]
        return "\n".join(lines) + "\n"


# 全局单例，供所有测试文件 import
REPORT = Reporter()
