#!/usr/bin/env python3
"""
旧版千川复盘报告迁移脚本。

将 /opt/qianchuan-review/reports/ 下的 JSON 文件批量导入新系统 outputs 表。
旧报告无用户归属，统一归到 admin 管理员账号（username='admin'）。

用法：
    cd backend
    source .venv/bin/activate
    python scripts/migrate_qianchuan_reports.py --reports-dir /opt/qianchuan-review/reports/

可选参数：
    --reports-dir   旧报告目录（默认 /opt/qianchuan-review/reports/）
    --dry-run       只打印，不写库
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


async def migrate(reports_dir: Path, dry_run: bool) -> None:
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app.core.database import AsyncSessionLocal
    from app.models.output import Output
    from app.models.user import User
    from sqlalchemy import select

    report_files = sorted(reports_dir.glob("*.json"))
    if not report_files:
        print(f"[WARN] 目录 {reports_dir} 下没有找到 JSON 文件")
        return

    async with AsyncSessionLocal() as db:
        admin = (await db.execute(
            select(User).where(User.username == "admin")
        )).scalar_one_or_none()
        if admin is None:
            print("[ERROR] 找不到 username='admin' 的账号，迁移中止")
            return
        admin_id = admin.id
        print(f"[INFO] admin 账号 id={admin_id}，共找到 {len(report_files)} 个报告文件")

        migrated = 0
        skipped = 0
        for path in report_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[WARN] 无法解析 {path.name}：{e}")
                skipped += 1
                continue

            report_text = data.get("report", "")
            scripts = data.get("scripts", [])
            excel_data = data.get("excelData", [])
            created_at_str = data.get("createdAt")

            script_count = len(scripts)
            has_excel = len(excel_data) > 0
            excel_label = "含投放数据" if has_excel else "仅脚本"
            title = f"千川复盘_{script_count}条素材_{excel_label}_迁移记录"

            try:
                created_at = (
                    datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if created_at_str
                    else datetime.now(timezone.utc)
                )
            except Exception:
                created_at = datetime.now(timezone.utc)

            if dry_run:
                print(f"[DRY-RUN] 将导入：{title}，{len(report_text)} 字，时间={created_at.isoformat()}")
                migrated += 1
                continue

            output = Output(
                title=title,
                tool_code="qianchuan-review",
                tool_name="千川脚本复盘",
                content=report_text,
                content_json={"script_count": script_count, "has_excel": has_excel},
                word_count=len(report_text),
                created_by=admin_id,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(output)
            migrated += 1

        if not dry_run and migrated > 0:
            await db.commit()

    mode = "[DRY-RUN]" if dry_run else "[DONE]"
    print(f"{mode} 迁移完成：成功 {migrated} 条，跳过 {skipped} 条")


def main():
    parser = argparse.ArgumentParser(description="千川复盘旧数据迁移脚本")
    parser.add_argument(
        "--reports-dir",
        default="/opt/qianchuan-review/reports/",
        help="旧报告 JSON 目录（默认 /opt/qianchuan-review/reports/）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir)
    if not reports_dir.exists():
        print(f"[ERROR] 目录不存在：{reports_dir}")
        sys.exit(1)

    asyncio.run(migrate(reports_dir, args.dry_run))


if __name__ == "__main__":
    main()
