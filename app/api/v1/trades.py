"""Trade catalog endpoints: public list for pickers + admin management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import admin_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.trade import (
    CustomTradeOut,
    TradeCreateIn,
    TradeMergeIn,
    TradeMergeOut,
    TradeOut,
    TradeUpdateIn,
)
from app.services import trades as trades_service

router = APIRouter(tags=["trades"])


@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    """Active trades for the pickers. Available to any signed-in user (the
    onboarding form runs before approval)."""
    return [TradeOut.model_validate(t) for t in trades_service.list_trades(db)]


@router.get("/admin/trades", response_model=list[TradeOut])
def admin_list_trades(
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    return [
        TradeOut.model_validate(t)
        for t in trades_service.list_trades(db, include_inactive=True)
    ]


@router.post(
    "/admin/trades",
    response_model=TradeOut,
    status_code=201,
    responses={409: {"model": ErrorResponse}},
)
def admin_create_trade(
    payload: TradeCreateIn,
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> TradeOut:
    return TradeOut.model_validate(trades_service.create_trade(db, payload))


@router.patch(
    "/admin/trades/{trade_id}",
    response_model=TradeOut,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def admin_update_trade(
    trade_id: uuid.UUID,
    payload: TradeUpdateIn,
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> TradeOut:
    return TradeOut.model_validate(trades_service.update_trade(db, trade_id, payload))


@router.get("/admin/trades/custom", response_model=list[CustomTradeOut])
def admin_custom_trades(
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> list[CustomTradeOut]:
    """Free-text trade values users invented (not in the catalog), with usage
    counts — the merge worklist."""
    return trades_service.custom_trades(db)


@router.post(
    "/admin/trades/merge",
    response_model=TradeMergeOut,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def admin_merge_trade(
    payload: TradeMergeIn,
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> TradeMergeOut:
    workers, jobs, canonical = trades_service.merge_trade(
        db, payload.from_name, payload.into_trade_id
    )
    return TradeMergeOut(
        workers_updated=workers, jobs_updated=jobs, canonical_name=canonical
    )
