"""Trade catalog schemas (admin-managed, multilingual)."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name_ja: str
    name_en: str
    active: bool
    sort_order: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class TradeCreateIn(BaseModel):
    name_ja: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class TradeUpdateIn(BaseModel):
    name_ja: str | None = Field(default=None, min_length=1, max_length=120)
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None
    sort_order: int | None = None


class CustomTradeOut(BaseModel):
    """A free-text trade value found on profiles/jobs that isn't in the catalog."""

    name: str
    worker_count: int
    job_count: int


class TradeMergeIn(BaseModel):
    """Merge a free-text trade value into a catalog trade: every occurrence on
    worker profiles and jobs is rewritten to the catalog trade's canonical
    name (deduplicated)."""

    from_name: str = Field(min_length=1, max_length=200)
    into_trade_id: uuid.UUID


class TradeMergeOut(BaseModel):
    workers_updated: int
    jobs_updated: int
    canonical_name: str
