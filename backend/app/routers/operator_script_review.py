"""
app/routers/operator_script_review.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/operator/qianchuan-script-review/review  — 非流式脚本预审
"""
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import error_response, success_response
from app.middlewares.auth import get_current_user
from app.models.qianchuan_script_review import QianchuanScriptReviewConfig
from app.models.user import User
from app.services.workspace_prompt import resolve_prompt

router = APIRouter(prefix="/operator/qianchuan-script-review", tags=["operator-qianchuan-script-review"])

_DEFAULT_DIRECT_PROMPT = """\
你是千川脚本审核员。对比原版脚本和仿写脚本，按以下维度审核：
1. 产品名称/昵称是否正确替换
2. 价格、数量等数字是否替换
3. 核心卖点是否体现
4. 结构和字数是否保持

严格按以下 JSON 格式返回（不加任何其他文字）：
{{"rating":"pass","must_fix":[{{"type":"类型","quote":"原文引用","fix":"修改建议"}}],"suggestions":["建议"],"passed":["通过项"]}}

rating 只能是 pass（可上线）/ minor（小改可上线）/ fail（需大改）

原版脚本：
{original_script}

仿写脚本：
{adapted_script}

产品信息：
{product_info}"""

_DEFAULT_VALUE_PROMPT = """\
你是价值观内容审核员。对比原版脚本和仿写脚本，按以下维度审核：
1. 情绪强度是否足够（焦虑型或诱惑型）
2. 是否有信息差/钩子
3. 结构和字数是否保持
4. 是否没有出现产品名

严格按以下 JSON 格式返回（不加任何其他文字）：
{{"rating":"pass","must_fix":[{{"type":"类型","quote":"原文引用","fix":"修改建议"}}],"suggestions":["建议"],"passed":["通过项"]}}

原版脚本：
{original_script}

仿写脚本：
{adapted_script}"""


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


async def _call_review_ai(prompt: str, model_id: str) -> str:
    """调 AI（非流式），返回原始文本（由 router 解析 JSON）。"""
    async with AsyncSessionLocal() as db:
        return await yunwu_adapter.chat(
            messages=[{"role": "user", "content": prompt}],
            db=db,
            model_id=model_id,
            feature="qianchuan_script_review",
        )


async def _resolve_model_id(config: QianchuanScriptReviewConfig | None, db: AsyncSession) -> str:
    if config is None or config.ai_model_id is None:
        return "claude-sonnet-4-6"
    from sqlalchemy import text as sa_text
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else "claude-sonnet-4-6"


class ReviewRequest(BaseModel):
    script_type: Literal["direct", "value"]
    original_script: str
    adapted_script: str
    product: Optional[dict] = None
    kol_id: int | None = None


@router.post("/review")
async def review_script(
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    config = (await db.execute(
        select(QianchuanScriptReviewConfig)
        .where(QianchuanScriptReviewConfig.config_key == "default")
        .where(QianchuanScriptReviewConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()

    model_id = await _resolve_model_id(config, db)

    if body.script_type == "direct":
        kol_prompt = await resolve_prompt(body.kol_id, "script-review", "direct_prompt", db)
        template = kol_prompt or (config.direct_prompt if config and config.direct_prompt else _DEFAULT_DIRECT_PROMPT)
        product_info = ""
        if body.product:
            product_info = "\n".join(f"{k}: {v}" for k, v in body.product.items())
        prompt = template.format(
            original_script=body.original_script,
            adapted_script=body.adapted_script,
            product_info=product_info,
        )
    else:
        kol_prompt = await resolve_prompt(body.kol_id, "script-review", "value_prompt", db)
        template = kol_prompt or (config.value_prompt if config and config.value_prompt else _DEFAULT_VALUE_PROMPT)
        prompt = template.format(
            original_script=body.original_script,
            adapted_script=body.adapted_script,
        )

    raw = await _call_review_ai(prompt, model_id)

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # 尝试提取嵌在 markdown 代码块中的 JSON
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                return error_response("INTERNAL_ERROR", f"AI 返回格式解析失败: {raw[:200]}")
        else:
            return error_response("INTERNAL_ERROR", f"AI 返回格式解析失败: {raw[:200]}")

    return success_response(data={
        "rating": result.get("rating"),
        "must_fix": result.get("must_fix", []),
        "suggestions": result.get("suggestions", []),
        "passed": result.get("passed", []),
    })
