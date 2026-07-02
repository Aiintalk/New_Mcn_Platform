"""
app/routers/operator_qianchuan_collection.py

千川爆文合集接口（operator / admin 鉴权）：
  GET    /api/tools/qianchuan-collection/personas               — 达人列表（含脚本数量）
  POST   /api/tools/qianchuan-collection/personas               — 新建达人
  DELETE /api/tools/qianchuan-collection/personas/{persona_name} — 软删除达人（级联软删脚本）
  GET    /api/tools/qianchuan-collection/scripts                — 脚本列表（支持 pool/persona_name/q/page/page_size）
  POST   /api/tools/qianchuan-collection/scripts                — 新增脚本
  DELETE /api/tools/qianchuan-collection/scripts/{script_id}    — 软删除脚本
  POST   /api/tools/qianchuan-collection/parse-file             — 文件解析，返回文本
"""
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy import func as sa_func, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.qianchuan_collection import QianchuanCollectionPersona, QianchuanCollectionScript
from app.models.user import User
from app.services.file_parser import parse_qianchuan_review_file

router = APIRouter(prefix="/tools/qianchuan-collection", tags=["qianchuan-collection"])


# ---------------------------------------------------------------------------
# 鉴权守卫
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# GET /personas
# ---------------------------------------------------------------------------

@router.get("/personas")
async def get_personas(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """获取达人列表（含脚本数量，排除已软删除）。"""
    rows = await db.execute(sa_text(
        """
        SELECT p.name,
               COUNT(s.id) FILTER (WHERE s.is_deleted = false) AS script_count
        FROM   qianchuan_collection_personas p
        LEFT JOIN qianchuan_collection_scripts s ON s.persona_name = p.name
        WHERE  p.is_deleted = false
        GROUP  BY p.name
        ORDER  BY p.name
        """
    ))
    personas = [{"name": row[0], "script_count": int(row[1])} for row in rows.fetchall()]
    return success_response(data={"personas": personas})


# ---------------------------------------------------------------------------
# POST /personas
# ---------------------------------------------------------------------------

class CreatePersonaBody(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("达人名称不能为空")
        if len(v) > 100:
            raise ValueError("达人名称不能超过 100 个字符")
        return v


@router.post("/personas")
async def create_persona(
    body: CreatePersonaBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新建达人分组。"""
    # 检查是否重名（is_deleted=false 的记录）
    exists = await db.execute(sa_text(
        "SELECT 1 FROM qianchuan_collection_personas WHERE name = :name AND is_deleted = false LIMIT 1"
    ), {"name": body.name})
    if exists.fetchone():
        raise HTTPException(
            status_code=409,
            detail={"code": "PERSONA_EXISTS", "message": f"达人「{body.name}」已存在"},
        )

    persona = QianchuanCollectionPersona(name=body.name)
    db.add(persona)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="collection_persona_create",
        target_type="qianchuan_collection_persona",
        target_id=persona.id,
        detail={"name": body.name},
    ))
    await db.commit()
    return success_response(data={"name": body.name})


# ---------------------------------------------------------------------------
# DELETE /personas/{persona_name}
# ---------------------------------------------------------------------------

@router.delete("/personas/{persona_name}")
async def delete_persona(
    persona_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删除达人（同时软删该达人下所有脚本）。"""
    # 检查达人是否存在
    persona_row = await db.execute(sa_text(
        "SELECT id FROM qianchuan_collection_personas WHERE name = :name AND is_deleted = false LIMIT 1"
    ), {"name": persona_name})
    persona = persona_row.fetchone()
    if not persona:
        raise HTTPException(
            status_code=404,
            detail={"code": "PERSONA_NOT_FOUND", "message": f"达人「{persona_name}」不存在"},
        )

    # 软删达人
    await db.execute(sa_text(
        "UPDATE qianchuan_collection_personas SET is_deleted = true WHERE name = :name"
    ), {"name": persona_name})
    # 级联软删该达人下的脚本
    await db.execute(sa_text(
        "UPDATE qianchuan_collection_scripts SET is_deleted = true WHERE persona_name = :name"
    ), {"name": persona_name})

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="collection_persona_delete",
        target_type="qianchuan_collection_persona",
        target_id=persona[0],
        detail={"name": persona_name},
    ))
    await db.commit()
    return success_response(data={"ok": True})


# ---------------------------------------------------------------------------
# GET /scripts
# ---------------------------------------------------------------------------

@router.get("/scripts")
async def get_scripts(
    pool: str = Query(..., description="global 或 persona"),
    persona_name: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """获取脚本列表，支持分页和筛选。"""
    if pool not in ("global", "persona"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "pool 必须为 global 或 persona"},
        )
    if pool == "persona" and not persona_name:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "persona 模式下 persona_name 必填"},
        )

    # 构建过滤条件
    conditions = ["pool = :pool", "is_deleted = false"]
    params: dict = {"pool": pool}

    if pool == "persona" and persona_name:
        conditions.append("persona_name = :persona_name")
        params["persona_name"] = persona_name

    if q and q.strip():
        conditions.append("(title ILIKE :q OR content ILIKE :q)")
        params["q"] = f"%{q.strip()}%"

    where_clause = " AND ".join(conditions)

    # 总数
    total_row = await db.execute(
        sa_text(f"SELECT COUNT(*) FROM qianchuan_collection_scripts WHERE {where_clause}"),
        params,
    )
    total = total_row.scalar() or 0

    # 分页数据
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    rows = await db.execute(
        sa_text(
            f"""
            SELECT id, pool, persona_name, title, content, likes, source, source_account, script_date, created_at
            FROM   qianchuan_collection_scripts
            WHERE  {where_clause}
            ORDER  BY id DESC
            LIMIT  :limit OFFSET :offset
            """
        ),
        params,
    )

    scripts = [
        {
            "id": row[0],
            "pool": row[1],
            "persona_name": row[2],
            "title": row[3],
            "content": row[4],
            "likes": row[5],
            "source": row[6],
            "source_account": row[7],
            "script_date": row[8].isoformat() if row[8] else None,
            "created_at": row[9].isoformat() if row[9] else None,
        }
        for row in rows.fetchall()
    ]

    return success_response(data={
        "scripts": scripts,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ---------------------------------------------------------------------------
# POST /scripts
# ---------------------------------------------------------------------------

class CreateScriptBody(BaseModel):
    pool: str
    persona_name: Optional[str] = None
    title: str
    content: str
    likes: Optional[int] = None
    source: Optional[str] = None
    source_account: Optional[str] = None
    script_date: Optional[str] = None  # ISO date string YYYY-MM-DD

    @field_validator("pool")
    @classmethod
    def pool_valid(cls, v: str) -> str:
        if v not in ("global", "persona"):
            raise ValueError("pool 必须为 global 或 persona")
        return v

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("标题不能为空")
        return v

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("内容不能为空")
        return v


@router.post("/scripts")
async def create_script(
    body: CreateScriptBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新增脚本。"""
    if body.pool == "persona":
        if not body.persona_name or not body.persona_name.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INPUT", "message": "persona 模式下 persona_name 必填"},
            )
        # 检查达人存在
        persona_row = await db.execute(sa_text(
            "SELECT 1 FROM qianchuan_collection_personas WHERE name = :name AND is_deleted = false LIMIT 1"
        ), {"name": body.persona_name})
        if not persona_row.fetchone():
            raise HTTPException(
                status_code=400,
                detail={"code": "PERSONA_NOT_FOUND", "message": f"达人「{body.persona_name}」不存在"},
            )

    # 处理 script_date
    script_date_val: Optional[date] = None
    if body.script_date:
        try:
            script_date_val = date.fromisoformat(body.script_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INPUT", "message": "script_date 格式错误，请使用 YYYY-MM-DD"},
            )
    else:
        script_date_val = date.today()

    script = QianchuanCollectionScript(
        pool=body.pool,
        persona_name=body.persona_name if body.pool == "persona" else None,
        title=body.title.strip(),
        content=body.content.strip(),
        likes=body.likes,
        source=body.source,
        source_account=body.source_account,
        script_date=script_date_val,
    )
    db.add(script)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="collection_script_create",
        target_type="qianchuan_collection_script",
        target_id=script.id,
        detail={"pool": body.pool, "persona_name": body.persona_name, "title": body.title[:50]},
    ))
    await db.commit()
    return success_response(data={"id": script.id})


# ---------------------------------------------------------------------------
# PUT /scripts/{script_id}
# ---------------------------------------------------------------------------

class UpdateScriptBody(BaseModel):
    title: str
    content: str
    likes: Optional[int] = None
    source: Optional[str] = None
    source_account: Optional[str] = None
    script_date: Optional[str] = None


@router.put("/scripts/{script_id}")
async def update_script(
    script_id: int,
    body: UpdateScriptBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """编辑脚本的标题、内容及元数据。"""
    if not body.title.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "标题不能为空"})
    if not body.content.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "内容不能为空"})

    row = await db.execute(sa_text(
        "SELECT id FROM qianchuan_collection_scripts WHERE id = :id AND is_deleted = false LIMIT 1"
    ), {"id": script_id})
    if not row.fetchone():
        raise HTTPException(
            status_code=404,
            detail={"code": "SCRIPT_NOT_FOUND", "message": "脚本不存在或已删除"},
        )

    await db.execute(sa_text(
        """UPDATE qianchuan_collection_scripts
           SET title = :title, content = :content, likes = :likes,
               source = :source, source_account = :source_account,
               script_date = :script_date, updated_at = now()
           WHERE id = :id"""
    ), {
        "id": script_id,
        "title": body.title.strip(),
        "content": body.content.strip(),
        "likes": body.likes,
        "source": body.source or None,
        "source_account": body.source_account or None,
        "script_date": body.script_date or None,
    })
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="collection_script_update",
        target_type="qianchuan_collection_script",
        target_id=script_id,
        detail={"title": body.title},
    ))
    await db.commit()
    return success_response(data={"ok": True})


# ---------------------------------------------------------------------------
# DELETE /scripts/{script_id}
# ---------------------------------------------------------------------------

@router.delete("/scripts/{script_id}")
async def delete_script(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删除脚本。"""
    row = await db.execute(sa_text(
        "SELECT id FROM qianchuan_collection_scripts WHERE id = :id AND is_deleted = false LIMIT 1"
    ), {"id": script_id})
    if not row.fetchone():
        raise HTTPException(
            status_code=404,
            detail={"code": "SCRIPT_NOT_FOUND", "message": "脚本不存在或已删除"},
        )

    await db.execute(sa_text(
        "UPDATE qianchuan_collection_scripts SET is_deleted = true WHERE id = :id"
    ), {"id": script_id})
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="collection_script_delete",
        target_type="qianchuan_collection_script",
        target_id=script_id,
        detail={"script_id": script_id},
    ))
    await db.commit()
    return success_response(data={"ok": True})


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    _: User = Depends(require_operator),
):
    """上传文件，解析返回文本。支持 .txt / .md / .docx / .pdf。"""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("txt", "md", "docx", "pdf"):
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": f"不支持的文件格式: .{ext}（支持 .txt / .md / .docx / .pdf）"},
        )
    try:
        text = await parse_qianchuan_review_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        ) from e
    return success_response(data={"text": text, "filename": file.filename})
