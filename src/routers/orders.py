from decimal import Decimal
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.common.auth.middleware import CurrentUser, get_current_user
from src.common.database import get_db
from src.schemas import OrderCreate, OrderResponse
from src import models

router = APIRouter()


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreate, db: Annotated[AsyncSession, Depends(get_db)], current_user: CurrentUser = Depends(get_current_user),):
    new_order = models.Orders(
        user_id=current_user.id,
        total_amount=0,
    )

    db.add(new_order)
    await db.commit()

    return new_order


@router.get("", response_model=list[OrderResponse])
async def get_orders(db: Annotated[AsyncSession, Depends(get_db)], current_user: CurrentUser = Depends(get_current_user),):
    query = (
        select(models.Orders)
        .order_by(models.Orders.created_at.desc())
    )
    if current_user.role != "admin":
        query = query.where(models.Orders.user_id == current_user.id)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser = Depends(get_current_user),
):
    query = (
        select(models.Orders)
        .where(models.Orders.id == order_id)
    )
    if current_user.role != "admin":
        query = query.where(models.Orders.user_id == current_user.id)

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)], current_user: CurrentUser = Depends(get_current_user),):
    query = select(models.Orders).where(models.Orders.id == order_id)
    if current_user.role != "admin":
        query = query.where(models.Orders.user_id == current_user.id)

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.status != "pending" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Cannot delete an order that is already processed or paid"
        )


    await db.delete(order)
    await db.commit()
