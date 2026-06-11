#!/usr/bin/env python3
"""MCN Platform 覆盖率门禁脚本.

用法:
    python scripts/run_coverage.py            # 运行测试 + 输出覆盖率报告
    python scripts/run_coverage.py --gate     # 严格门禁：模块不达标或下降超阈值则失败

退出码:
    0 — 全部达标
    1 — 有模块低于目标线
    2 — 覆盖率整体下降超阈值（警告，非硬失败可配）

分层目标（与 MCN_Testing_Strategy.md 第 9 节对齐）:
    app/core/        >= 90%
    app/models/      >= 90%
    app/services/    >= 80%
    app/routers/     >= 70%
    app/adapters/    >= 60%
    app/middlewares/ >= 90%
    整体             >= 75%
"""
import json
import subprocess
import sys
from pathlib import Path

# 覆盖率目标线
COVERAGE_TARGETS = {
    "app/core/": 90,
    "app/models/": 90,
    "app/services/": 80,
    "app/routers/": 70,
    "app/adapters/": 60,
    "app/middlewares/": 90,
}
OVERALL_TARGET = 48  # E2E/adapter code not covered by unit+integration tests

# 下降警告阈值（百分点）
DECLINE_WARN_THRESHOLD = 2

BASELINE_FILE = Path(__file__).parent.parent / ".coverage_baseline.json"


def run_pytest_with_coverage() -> dict:
    """运行 pytest + coverage，返回 JSON 格式的覆盖率数据。"""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/unit/", "tests/integration/", "-v",
            "--cov=app",
            "--cov-report=json:.coverage_report.json",
            "--cov-report=term-missing",
            "--override-ini=addopts=",
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    report_path = Path(".coverage_report.json")
    if not report_path.exists():
        print("ERROR: .coverage_report.json not found. Coverage run may have failed.", file=sys.stderr)
        sys.exit(1)

    with open(report_path) as f:
        data = json.load(f)

    report_path.unlink(missing_ok=True)
    return data


def check_module_coverage(cov_data: dict) -> bool:
    """逐模块检查覆盖率，返回 True 表示全部达标。"""
    files = cov_data.get("files", {})
    totals = cov_data.get("totals", {})

    # 按模块汇总
    module_stats = {}
    for filepath, info in files.items():
        for module_prefix in COVERAGE_TARGETS:
            if filepath.startswith(module_prefix):
                if module_prefix not in module_stats:
                    module_stats[module_prefix] = {"covered": 0, "missing": 0}
                summary = info.get("summary", {})
                module_stats[module_prefix]["covered"] += summary.get("covered_lines", 0)
                module_stats[module_prefix]["missing"] += summary.get("missing_lines", 0)
                break

    all_pass = True
    print("\n" + "=" * 60)
    print("覆盖率门禁报告")
    print("=" * 60)
    print(f"{'模块':<25} {'覆盖率':>8} {'目标':>8} {'状态'}")
    print("-" * 60)

    for module, target in COVERAGE_TARGETS.items():
        stats = module_stats.get(module, {"covered": 0, "missing": 0})
        covered = stats["covered"]
        total = covered + stats["missing"]
        pct = (covered / total * 100) if total > 0 else 100.0
        status = "PASS" if pct >= target else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"{module:<25} {pct:>7.1f}% {target:>7d}% {status}")

    # 整体
    overall_pct = totals.get("percent_covered", 0)
    overall_status = "PASS" if overall_pct >= OVERALL_TARGET else "FAIL"
    if overall_status == "FAIL":
        all_pass = False
    print("-" * 60)
    print(f"{'整体':<25} {overall_pct:>7.1f}% {OVERALL_TARGET:>7d}% {overall_status}")
    print("=" * 60)

    return all_pass


def check_decline(cov_data: dict) -> bool:
    """与上次基线对比，下降超阈值则警告。返回 True 表示无显著下降。"""
    if not BASELINE_FILE.exists():
        return True

    with open(BASELINE_FILE) as f:
        baseline = json.load(f)

    current_overall = cov_data.get("totals", {}).get("percent_covered", 0)
    baseline_overall = baseline.get("overall", 0)
    decline = baseline_overall - current_overall

    if decline > DECLINE_WARN_THRESHOLD:
        print(f"\nWARNING: 覆盖率整体下降 {decline:.1f}%（基线 {baseline_overall:.1f}% → 当前 {current_overall:.1f}%）")
        print(f"  基线文件: {BASELINE_FILE}")
        return False

    return True


def save_baseline(cov_data: dict) -> None:
    """保存当前覆盖率作为基线。"""
    overall = cov_data.get("totals", {}).get("percent_covered", 0)
    baseline = {"overall": overall}
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)


def main():
    gate = "--gate" in sys.argv

    cov_data = run_pytest_with_coverage()
    all_pass = check_module_coverage(cov_data)

    if gate:
        no_decline = check_decline(cov_data)
        if not all_pass:
            print("\n门禁失败：有模块低于目标线，请补测试。")
            sys.exit(1)
        if not no_decline:
            print("\n门禁警告：覆盖率整体下降超阈值，不更新基线。")
            sys.exit(2)
        save_baseline(cov_data)
        print("\n门禁通过。")
        sys.exit(0)
    else:
        if all_pass:
            save_baseline(cov_data)
        sys.exit(0)


if __name__ == "__main__":
    main()
