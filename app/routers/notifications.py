from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.models import DeviceTokenModel

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class DeviceTokenRegisterRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    device_token: str = Field(min_length=32, max_length=512)
    platform: str = Field(default="ios", pattern="^(ios)$")


class DeviceTokenResponse(BaseModel):
    id: str
    user_id: str
    platform: str
    device_token: str
    is_active: bool


@router.post("/device-tokens", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_device_token(
    payload: DeviceTokenRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> DeviceTokenResponse:
    existing = await session.scalar(
        select(DeviceTokenModel).where(DeviceTokenModel.device_token == payload.device_token)
    )
    if existing is None:
        record = DeviceTokenModel(
            user_id=payload.user_id.strip(),
            platform=payload.platform,
            device_token=payload.device_token.strip(),
            is_active=True,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return DeviceTokenResponse(
            id=str(record.id),
            user_id=record.user_id,
            platform=record.platform,
            device_token=record.device_token,
            is_active=record.is_active,
        )

    existing.user_id = payload.user_id.strip()
    existing.platform = payload.platform
    existing.is_active = True
    await session.commit()
    await session.refresh(existing)
    return DeviceTokenResponse(
        id=str(existing.id),
        user_id=existing.user_id,
        platform=existing.platform,
        device_token=existing.device_token,
        is_active=existing.is_active,
    )


@router.get("/device-tokens", response_model=list[DeviceTokenResponse])
async def list_device_tokens(
    user_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[DeviceTokenResponse]:
    rows = (
        await session.execute(
            select(DeviceTokenModel)
            .where(DeviceTokenModel.user_id == user_id)
            .where(DeviceTokenModel.is_active == True)  # noqa: E712
            .order_by(DeviceTokenModel.created_at.desc())
        )
    ).scalars().all()
    return [
        DeviceTokenResponse(
            id=str(row.id),
            user_id=row.user_id,
            platform=row.platform,
            device_token=row.device_token,
            is_active=row.is_active,
        )
        for row in rows
    ]


@router.delete("/device-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_device_token(
    token_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    token = await session.scalar(
        select(DeviceTokenModel).where(DeviceTokenModel.id == token_id)
    )
    if token is None:
        raise HTTPException(status_code=404, detail="Device token not found")
    token.is_active = False
    await session.commit()


@router.delete("/device-tokens", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_token_by_value(
    device_token: str = Query(..., min_length=32),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(
        delete(DeviceTokenModel).where(DeviceTokenModel.device_token == device_token)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Device token not found")
    await session.commit()
