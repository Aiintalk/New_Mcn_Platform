from passlib.context import CryptContext
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_initial_data() -> None:
    """
    Ensure an admin account exists on startup.

    If no user with username=INITIAL_ADMIN_USERNAME exists (not soft-deleted),
    create it with the configured initial password.
    password_changed_at is intentionally left NULL so the admin must change
    their password on first login.
    """
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(User).where(
                    User.username == settings.initial_admin_username,
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            return  # admin already exists, nothing to do

        admin = User(
            username=settings.initial_admin_username,
            real_name="系统管理员",
            password_hash=pwd_context.hash(settings.initial_admin_password),
            role="admin",
            status="enabled",
            password_changed_at=None,  # force change on first login
        )
        session.add(admin)
        await session.commit()
