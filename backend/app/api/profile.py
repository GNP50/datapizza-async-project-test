from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.services.database import get_db
from app.models import UserProfile, User
from app.core.security import get_current_user


router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


class UserProfileResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str | None
    bio: str | None
    avatar_url: str | None
    company: str | None
    location: str | None
    website: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    company: str | None = None
    location: str | None = None
    website: str | None = None


@router.get("", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        # Create default profile if it doesn't exist
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    return UserProfileResponse(
        id=str(profile.id),
        user_id=str(profile.user_id),
        email=current_user.email,
        full_name=profile.full_name,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        company=profile.company,
        location=profile.location,
        website=profile.website,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


@router.patch("", response_model=UserProfileResponse)
async def update_user_profile(
    profile_update: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        # Create profile if it doesn't exist
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    # Update only provided fields
    update_data = profile_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return UserProfileResponse(
        id=str(profile.id),
        user_id=str(profile.user_id),
        email=current_user.email,
        full_name=profile.full_name,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        company=profile.company,
        location=profile.location,
        website=profile.website,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )
