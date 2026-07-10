"""Trade catalog services: listing, admin CRUD, and merging free-text values.

Profiles and jobs store trades as plain strings; the catalog (``trades``)
defines the canonical Japanese names plus English labels for the pickers.
Admins can see which free-text values users invented and merge them into a
canonical trade — every occurrence on worker profiles and jobs is rewritten.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.job import Job
from app.models.trade import Trade
from app.models.worker_profile import WorkerProfile
from app.schemas.trade import CustomTradeOut, TradeCreateIn, TradeUpdateIn


def list_trades(db: Session, *, include_inactive: bool = False) -> list[Trade]:
    stmt = select(Trade).order_by(Trade.sort_order, Trade.name_ja)
    if not include_inactive:
        stmt = stmt.where(Trade.active.is_(True))
    return list(db.scalars(stmt))


def create_trade(db: Session, payload: TradeCreateIn) -> Trade:
    clash = db.scalar(select(Trade).where(Trade.name_ja == payload.name_ja))
    if clash is not None:
        raise errors.conflict("trade_exists", "error.trade.exists")
    trade = Trade(
        name_ja=payload.name_ja.strip(),
        name_en=payload.name_en.strip(),
        sort_order=payload.sort_order,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def update_trade(db: Session, trade_id: uuid.UUID, payload: TradeUpdateIn) -> Trade:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise errors.not_found()
    data = payload.model_dump(exclude_unset=True)
    if "name_ja" in data and data["name_ja"] != trade.name_ja:
        clash = db.scalar(select(Trade).where(Trade.name_ja == data["name_ja"]))
        if clash is not None:
            raise errors.conflict("trade_exists", "error.trade.exists")
        # Renaming the canonical value rewrites stored occurrences too, so
        # profiles/jobs never point at a stale name.
        _replace_everywhere(db, trade.name_ja, data["name_ja"])
    for field, value in data.items():
        setattr(trade, field, value)
    db.commit()
    db.refresh(trade)
    return trade


def custom_trades(db: Session) -> list[CustomTradeOut]:
    """Distinct free-text trade values on profiles/jobs that aren't catalog
    entries, with usage counts — the admin's merge worklist."""
    catalog = {t.name_ja for t in db.scalars(select(Trade))} | {
        t.name_en for t in db.scalars(select(Trade))
    }

    def counts(column: object, table: type) -> dict[str, int]:
        rows = db.execute(
            select(func.unnest(column).label("t"), func.count())
            .select_from(table)
            .group_by("t")
        ).all()
        return {str(name): int(count) for name, count in rows}

    worker_counts = counts(WorkerProfile.trades, WorkerProfile)
    job_counts = counts(Job.trades, Job)
    names = (set(worker_counts) | set(job_counts)) - catalog
    return sorted(
        (
            CustomTradeOut(
                name=n,
                worker_count=worker_counts.get(n, 0),
                job_count=job_counts.get(n, 0),
            )
            for n in names
        ),
        key=lambda c: -(c.worker_count + c.job_count),
    )


def merge_trade(
    db: Session, from_name: str, into_trade_id: uuid.UUID
) -> tuple[int, int, str]:
    trade = db.get(Trade, into_trade_id)
    if trade is None:
        raise errors.not_found()
    if from_name == trade.name_ja:
        raise errors.bad_request("merge_self", "error.trade.merge_self")
    workers, jobs = _replace_everywhere(db, from_name, trade.name_ja)
    db.commit()
    return workers, jobs, trade.name_ja


def _replace_everywhere(db: Session, from_name: str, to_name: str) -> tuple[int, int]:
    """Rewrite ``from_name`` → ``to_name`` in every trades array (deduplicated,
    order-preserving). Row counts are small at this stage, so a Python pass is
    clearer and safer than array_replace SQL (which can leave duplicates)."""

    def rewrite(values: list[str]) -> list[str]:
        out: list[str] = []
        for v in values:
            v2 = to_name if v == from_name else v
            if v2 not in out:
                out.append(v2)
        return out

    workers = 0
    for wp in db.scalars(
        select(WorkerProfile).where(WorkerProfile.trades.contains([from_name]))
    ):
        wp.trades = rewrite(wp.trades)
        workers += 1
    jobs = 0
    for job in db.scalars(select(Job).where(Job.trades.contains([from_name]))):
        job.trades = rewrite(job.trades)
        jobs += 1
    return workers, jobs
