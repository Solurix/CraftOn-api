"""Debug-only data seeding: create random approved users + open jobs.

Non-production helper for manual testing — the router guards this behind fake
auth mode (dev/CI). Not a business feature; data is intentionally random.
"""

from __future__ import annotations

import datetime
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contractor_profile import ContractorProfile
from app.models.enums import JobStatus, UserStatus, UserType, WorkerClass
from app.models.job import Job
from app.models.user import User
from app.models.worker_profile import WorkerProfile

_TRADES = ["大工", "鳶", "電気工", "配管", "内装", "左官", "塗装", "鉄筋", "型枠", "解体"]
_FIRST = ["太郎", "健", "翔", "誠", "大輔", "拓也", "和也", "隆", "勇", "学"]
_LAST = ["山田", "佐藤", "鈴木", "田中", "高橋", "渡辺", "伊藤", "中村", "小林", "加藤"]
_COMPANIES = ["山田建設", "佐藤工務店", "東京リフォーム", "みらい建築", "大和工業", "桜井組"]
_PREFS = ["Tokyo", "Kanagawa", "Saitama", "Chiba"]


def _phone() -> str:
    return "+8190" + "".join(random.choice("0123456789") for _ in range(8))


def _credentials(phone: str) -> tuple[str, str]:
    """Derive a unique (username, email) pair from a seeded phone number."""
    handle = "seed" + phone.lstrip("+")
    return handle, f"{handle}@seed.local"


def seed_random_data(
    db: Session, *, workers: int = 5, contractors: int = 3, jobs: int = 10
) -> dict[str, int]:
    """Create N approved contractors/workers and K open jobs. Returns counts."""
    contractor_users: list[User] = []
    for _ in range(contractors):
        company = random.choice(_COMPANIES)
        phone = _phone()
        username, email = _credentials(phone)
        user = User(
            phone_number=phone,
            username=username,
            email=email,
            user_type=UserType.CONTRACTOR,
            status=UserStatus.APPROVED,
            display_name=company,
        )
        db.add(user)
        db.flush()
        db.add(
            ContractorProfile(
                user_id=user.id,
                company_name=company,
                contact_person=random.choice(_LAST),
                prefecture=random.choice(_PREFS),
            )
        )
        contractor_users.append(user)

    for _ in range(workers):
        name = f"{random.choice(_LAST)} {random.choice(_FIRST)}"
        phone = _phone()
        username, email = _credentials(phone)
        user = User(
            phone_number=phone,
            username=username,
            email=email,
            user_type=UserType.WORKER,
            status=UserStatus.APPROVED,
            display_name=name,
        )
        db.add(user)
        db.flush()
        db.add(
            WorkerProfile(
                user_id=user.id,
                nationality="JP",
                worker_class=random.choice(list(WorkerClass)),
                trades=random.sample(_TRADES, k=random.randint(1, 3)),
                years_experience=random.randint(0, 20),
            )
        )

    # Jobs need a contractor: prefer the ones just seeded, else any existing.
    posters = contractor_users or list(
        db.scalars(select(User).where(User.user_type == UserType.CONTRACTOR)).all()
    )
    jobs_created = 0
    for _ in range(jobs):
        if not posters:
            break
        poster = random.choice(posters)
        work_date = datetime.date.today() + datetime.timedelta(
            days=random.randint(1, 30)
        )
        db.add(
            Job(
                contractor_id=poster.id,
                trades=random.sample(_TRADES, k=random.randint(1, 2)),
                work_date=work_date,
                start_time=datetime.time(8, 0),
                end_time=datetime.time(17, 0),
                prefecture=random.choice(_PREFS),
                daily_wage=random.randrange(12000, 30000, 1000),
                headcount=random.randint(1, 3),
                status=JobStatus.OPEN,
            )
        )
        jobs_created += 1

    db.commit()
    return {"workers": workers, "contractors": contractors, "jobs": jobs_created}
