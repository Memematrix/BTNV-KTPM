import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.auth.middleware import CurrentUser, get_current_user
from src.common.database import get_db
from src.models import Orders
from src.schemas import OrderCreate, OrderResponse

router = APIRouter()
Database = Annotated[AsyncSession, Depends(get_db)]
Identity = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreate, db: Database, current_user: Identity):
    order = Orders(user_id=current_user.id, total_amount=payload.total_amount)
    db.add(order)
    await db.commit()
    return order


@router.get("", response_model=list[OrderResponse])
async def get_orders(db: Database, current_user: Identity, mine: bool = False):
    query = select(Orders).order_by(Orders.created_at.desc(), Orders.id)
    if mine or current_user.role != "admin":
        query = query.where(Orders.user_id == current_user.id)
    return (await db.scalars(query)).all()


async def owned_order(order_id: uuid.UUID, db: AsyncSession, current_user: CurrentUser) -> Orders:
    query = select(Orders).where(Orders.id == order_id)
    if current_user.role != "admin":
        query = query.where(Orders.user_id == current_user.id)
    order = await db.scalar(query)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: uuid.UUID, db: Database, current_user: Identity):
    return await owned_order(order_id, db, current_user)


@router.delete("/{order_id}", status_code=204)
async def delete_order(order_id: uuid.UUID, db: Database, current_user: Identity):
    order = await owned_order(order_id, db, current_user)
    if order.status != "pending" and current_user.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot delete an order that is already processed or paid")
    await db.delete(order)
    await db.commit()
