from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from datetime import datetime

from app.models.news import NewsCreate, NewsRead
from app.db.session import get_db
from app.db import crud

router = APIRouter(prefix="/news", tags=["news"])

@router.get("/", response_model=list[NewsRead])
async def get_news(
	skip: int = 0,
	limit: int = 50,
	symbol: Optional[str] = Query(None),
	source: Optional[str] = Query(None),
	date_from: Optional[datetime] = Query(None),
	date_to: Optional[datetime] = Query(None),
	db: AsyncSession = Depends(get_db)
):
	try:
		result = await crud.get_news(
			db, skip=skip, limit=limit,
			symbol=symbol, source=source,
			date_from=date_from, date_to=date_to
		)
		return result
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.post("/", response_model=NewsRead)
async def create_news(news: NewsCreate, db: AsyncSession = Depends(get_db)):
	try:
		new_news = await crud.create_news(db, **news.dict())
		return new_news
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.delete("/{news_id}")
async def delete_news(news_id: int, db: AsyncSession = Depends(get_db)):
	deleted = await crud.delete_news(db, news_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="News not found")
	return {"detail": "News deleted"}

@router.delete("/old")
async def delete_old_news(days: int = 30, db: AsyncSession = Depends(get_db)):
	count = await crud.delete_old_news(db, days)
	return {"detail": f"{count} old news deleted"}
