#!/usr/bin/env python3
"""
素材库旧数据迁移脚本。

将旧架构 Ai_Toolbox/material-library-web/data/personas/<name>/{soul.md,content-plan.md}
下的 markdown 文件导入新系统 kols 表的 persona / content_plan 字段。

匹配方式：按 kols.name 文本匹配（旧架构子目录名即红人名）。
安全策略：仅当 kols.persona / kols.content_plan 为 NULL 时写入，已有数据不覆盖。

用法：
    cd backend
    source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
    python scripts/migrate_material_library.py \\
        --data-dir "/path/to/Ai_Toolbox/material-library-web/data/personas"

可选参数：
    --data-dir   旧 personas 目录（必填）
    --dry-run    只打印，不写库
    --overwrite  覆盖已有 persona/content_plan（默认仅填 NULL）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


# 旧架构目录名是按中文创建的，Windows 默认 GBK，跨平台可能出现编码错乱。
# 这里返回多种解码方式找到红人名（外层逐一尝试匹配 kols.name）。
def _decode_persona_dirname_candidates(name: str) -> list[str]:
    """返回多种编码还原后的候选红人名（含原样）。"""
    # 1. 原样（Linux/macOS UTF-8）
    candidates = [name]
    # 2. UTF-8 字节被当 GBK 解码后存储（Windows 文件系统典型错乱），反向还原
    try:
        restored = name.encode("gbk").decode("utf-8")
        candidates.append(restored)
    except Exception:
        pass
    # 3. UTF-8 字节被当 latin-1 解码，反向还原
    try:
        candidates.append(name.encode("latin-1").decode("utf-8"))
    except Exception:
        pass
    # 4. GBK 字节被当 UTF-8 解码（反向）
    try:
        candidates.append(name.encode("utf-8").decode("gbk"))
    except Exception:
        pass
    # 去重保留顺序
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


async def migrate(data_dir: Path, dry_run: bool, overwrite: bool) -> None:
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.kol import Kol

    persona_dirs = sorted([p for p in data_dir.iterdir() if p.is_dir()])
    if not persona_dirs:
        print(f"[WARN] 目录 {data_dir} 下没有找到任何子目录")
        return

    print(f"[INFO] 扫描到 {len(persona_dirs)} 个红人目录：{[p.name for p in persona_dirs]}")

    migrated_persona = 0
    migrated_plan = 0
    skipped_no_match = 0
    skipped_has_data = 0

    async with AsyncSessionLocal() as db:
        for persona_path in persona_dirs:
            dirname = persona_path.name
            possible_names = _decode_persona_dirname_candidates(dirname)

            # 查询匹配的 kol（按可能的名字逐一尝试）
            kol = None
            for name in possible_names:
                kol = (
                    await db.execute(select(Kol).where(Kol.name == name))
                ).scalar_one_or_none()
                if kol is not None:
                    break

            if kol is None:
                print(f"[SKIP] 目录 '{dirname}' 未匹配到 kols 记录（尝试名：{possible_names}）")
                skipped_no_match += 1
                continue

            # 处理 soul.md → kols.persona
            soul_path = persona_path / "soul.md"
            if soul_path.exists():
                try:
                    soul_text = soul_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    soul_text = soul_path.read_text(encoding="gbk")

                if kol.persona and not overwrite:
                    print(f"[SKIP] {kol.name} 已有 persona，跳过（用 --overwrite 覆盖）")
                    skipped_has_data += 1
                elif soul_text.strip():
                    print(
                        f"[{'DRY-RUN' if dry_run else 'OK'}] {kol.name}: persona 写入 "
                        f"({len(soul_text)} 字符)"
                    )
                    if not dry_run:
                        kol.persona = soul_text
                    migrated_persona += 1

            # 处理 content-plan.md → kols.content_plan
            plan_path = persona_path / "content-plan.md"
            if plan_path.exists():
                try:
                    plan_text = plan_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    plan_text = plan_path.read_text(encoding="gbk")

                if kol.content_plan and not overwrite:
                    print(f"[SKIP] {kol.name} 已有 content_plan，跳过（用 --overwrite 覆盖）")
                    skipped_has_data += 1
                elif plan_text.strip():
                    print(
                        f"[{'DRY-RUN' if dry_run else 'OK'}] {kol.name}: content_plan 写入 "
                        f"({len(plan_text)} 字符)"
                    )
                    if not dry_run:
                        kol.content_plan = plan_text
                    migrated_plan += 1

        if not dry_run and (migrated_persona > 0 or migrated_plan > 0):
            await db.commit()

    mode = "[DRY-RUN]" if dry_run else "[DONE]"
    print(
        f"{mode} 迁移完成：persona 写入 {migrated_persona} 条，"
        f"content_plan 写入 {migrated_plan} 条，"
        f"未匹配 {skipped_no_match}，已有数据跳过 {skipped_has_data}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="素材库旧数据迁移脚本")
    parser.add_argument(
        "--data-dir",
        required=True,
        help="旧 personas 目录（如 .../Ai_Toolbox/material-library-web/data/personas）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已有 persona/content_plan（默认仅填 NULL）",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[ERROR] 目录不存在：{data_dir}")
        sys.exit(1)

    asyncio.run(migrate(data_dir, args.dry_run, args.overwrite))


if __name__ == "__main__":
    main()
