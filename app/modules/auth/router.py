from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.modules.auth.models import User, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = UserRole.ADMIN


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise credentials_error from error
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/bootstrap", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(payload: UserCreate, session: SessionDep) -> User:
    """Create the first administrator; permanently closes after any user exists."""
    if await session.scalar(select(func.count()).select_from(User)):
        raise HTTPException(status_code=409, detail="Bootstrap is already complete")
    user = User(
        email=payload.email.casefold(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/token", response_model=TokenRead)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> TokenRead:
    user = await session.scalar(select(User).where(User.email == form.username.casefold()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(str(user.id), {"role": user.role.value})
    return TokenRead(access_token=token)


@router.get("/me", response_model=UserRead)
async def current_user(user: CurrentUser) -> User:
    return user


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: SessionDep, actor: CurrentUser) -> User:
    if actor.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator role required")
    if await session.scalar(select(User.id).where(User.email == payload.email.casefold())):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(
        email=payload.email.casefold(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
