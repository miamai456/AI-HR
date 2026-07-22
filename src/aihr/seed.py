import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import DailyFunnelMetric


def _binomial(n: int, probability: float, rng: random.Random) -> int:
    return sum(rng.random() < probability for _ in range(n))


def seed_demo_metrics(session: Session, seed: int = 20260722) -> int:
    existing = session.scalar(select(func.count()).select_from(DailyFunnelMetric))
    if existing:
        return 0

    rng = random.Random(seed)
    start_date = date(2026, 1, 1)
    end_date = date(2026, 6, 30)
    job_categories = ["技术", "销售", "运营"]
    regions = ["华东", "华北", "华南"]
    sources = ["ai", "human"]
    rows: list[DailyFunnelMetric] = []

    current = start_date
    while current <= end_date:
        for source in sources:
            for job_category in job_categories:
                for region in regions:
                    recommended = rng.randint(28, 65)
                    contact_probability = 0.82 if source == "ai" else 0.78
                    if region == "华东" and date(2026, 5, 1) <= current <= date(2026, 5, 31):
                        contact_probability -= 0.15

                    reply_probability = 0.51 + (0.03 if source == "ai" else 0)
                    interview_probability = 0.45 + (0.05 if source == "ai" else 0)
                    if source == "ai" and job_category == "销售" and current >= date(2026, 4, 1):
                        interview_probability -= 0.13

                    offer_probability = 0.37 + (0.02 if job_category == "技术" else 0)
                    hire_probability = 0.69

                    contacted = _binomial(recommended, contact_probability, rng)
                    replied = _binomial(contacted, reply_probability, rng)
                    interviewed = _binomial(replied, interview_probability, rng)
                    offered = _binomial(interviewed, offer_probability, rng)
                    hired = _binomial(offered, hire_probability, rng)

                    rows.append(
                        DailyFunnelMetric(
                            metric_date=current,
                            source=source,
                            job_category=job_category,
                            region=region,
                            recommended=recommended,
                            contacted=contacted,
                            replied=replied,
                            interviewed=interviewed,
                            offered=offered,
                            hired=hired,
                            data_origin="synthetic",
                        )
                    )
        current += timedelta(days=1)

    session.add_all(rows)
    session.commit()
    return len(rows)


# Compatibility name retained for the initial scaffold tests and scripts.
seed_demo_data = seed_demo_metrics
