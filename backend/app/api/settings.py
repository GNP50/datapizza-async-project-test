from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.services.database import get_db
from app.models import UserSettings, User
from app.core.security import get_current_user


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class UserSettingsResponse(BaseModel):
    id: str
    user_id: str
    theme: str
    language: str
    notifications_enabled: bool
    email_notifications: bool
    compact_mode: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    theme: str | None = None
    language: str | None = None
    notifications_enabled: bool | None = None
    email_notifications: bool | None = None
    compact_mode: bool | None = None


@router.get("", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's settings."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        # Create default settings if they don't exist
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return UserSettingsResponse(
        id=str(settings.id),
        user_id=str(settings.user_id),
        theme=settings.theme,
        language=settings.language,
        notifications_enabled=settings.notifications_enabled,
        email_notifications=settings.email_notifications,
        compact_mode=settings.compact_mode,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat(),
    )


@router.patch("", response_model=UserSettingsResponse)
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's settings."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        # Create settings if they don't exist
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    # Update only provided fields
    update_data = settings_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    await db.commit()
    await db.refresh(settings)

    return UserSettingsResponse(
        id=str(settings.id),
        user_id=str(settings.user_id),
        theme=settings.theme,
        language=settings.language,
        notifications_enabled=settings.notifications_enabled,
        email_notifications=settings.email_notifications,
        compact_mode=settings.compact_mode,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat(),
    )
