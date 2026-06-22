# app/api/routes_backtest.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional

from app.db.session import get_session
from app.db import crud
from app.utils.security import get_current_user
from app.utils.logger import (
	logger,
	log_order_error,
)

router = APIRouter(prefix="/api", tags=["Backtest"])

# ---------- Backtest Reports ----------
@router.get("/backtest/reports")
async def get_backtest_reports(
	skip: int = Query(0, ge=0),
	limit: int = Query(100, le=1000),
	symbol: Optional[str] = None,
	strategy: Optional[str] = None,
	user_id: Optional[int] = None,
	date_from: Optional[str] = None,
	date_to: Optional[str] = None,
	db: AsyncSession = Depends(get_session),
	current_user: dict = Depends(get_current_user)
):
	try:
		return await crud.get_backtest_reports_paginated(
			db=db,
			skip=skip,
			limit=limit,
			symbol=symbol,
			strategy=strategy,
			user_id=user_id,
			date_from=date_from,
			date_to=date_to
		)
	except SQLAlchemyError as e:
		log_order_error("get_backtest_reports", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# ---------- Trades ----------
@router.get("/backtest/trades")
async def get_trades(
	skip: int = Query(0, ge=0),
	limit: int = Query(100, le=1000),
	symbol: Optional[str] = None,
	status: Optional[str] = None,
	date_from: Optional[str] = None,
	date_to: Optional[str] = None,
	db: AsyncSession = Depends(get_session),
	current_user: dict = Depends(get_current_user)
):
	try:
		return await crud.get_trades(
			db=db,
			skip=skip,
			limit=limit,
			symbol=symbol,
			status=status,
			date_from=date_from,
			date_to=date_to
		)
	except SQLAlchemyError as e:
		log_order_error("get_trades", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# ---------- Risk Logs ----------
@router.get("/risk/logs")
async def get_risk_logs(
	skip: int = Query(0, ge=0),
	limit: int = Query(100, le=1000),
	symbol: Optional[str] = None,
	reason: Optional[str] = None,
	date_from: Optional[str] = None,
	date_to: Optional[str] = None,
	sentiment: Optional[float] = None,
	profit_loss_min: Optional[float] = None,
	profit_loss_max: Optional[float] = None,
	db: AsyncSession = Depends(get_session),
	current_user: dict = Depends(get_current_user)
):
	try:
		return await crud.get_risk_logs(
			db=db,
			skip=skip,
			limit=limit,
			symbol=symbol,
			reason=reason,
			date_from=date_from,
			date_to=date_to,
			sentiment=sentiment,
			profit_loss_min=profit_loss_min,
			profit_loss_max=profit_loss_max
		)
	except SQLAlchemyError as e:
		log_order_error("get_risk_logs", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
