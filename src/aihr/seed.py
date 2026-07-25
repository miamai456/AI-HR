import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import (
    Candidate,
    DailyFunnelMetric,
    FunnelEvent,
    Job,
    ModelVersion,
    Recommendation,
    Recruiter,
)

STAGES = ["recommended", "contacted", "replied", "interviewed", "offered", "hired"]
JOB_CATEGORIES = ["技术", "销售", "运营"]
REGIONS = ["华东", "华北", "华南"]
SOURCES = ["ai", "human"]
EDUCATION_LEVELS = ["大专", "本科", "硕士", "博士"]
SENIORITY_LEVELS = ["junior", "mid", "senior"]


def _chance(probability: float, rng: random.Random) -> bool:
    return rng.random() < max(0.0, min(1.0, probability))


def _random_datetime(day: date, rng: random.Random) -> datetime:
    return datetime.combine(day, time(hour=rng.randint(9, 18), minute=rng.randint(0, 59)))


def _stage_gap(stage: str, rng: random.Random) -> timedelta:
    ranges = {
        "contacted": (0, 2),
        "replied": (1, 5),
        "interviewed": (3, 18),
        "offered": (5, 25),
        "hired": (10, 45),
    }
    low, high = ranges[stage]
    return timedelta(days=rng.randint(low, high), hours=rng.randint(1, 8))


def _model_version_for(recommended_on: date, source: str) -> str:
    if source == "human":
        return "mv_human_rule"
    if recommended_on < date(2026, 4, 1):
        return "mv_ai_2026_q1"
    return "mv_ai_2026_q2"


def _stage_probabilities(source: str, job_category: str, region: str, recommended_on: date) -> dict:
    contact = 0.82 if source == "ai" else 0.78
    if region == "华东" and date(2026, 5, 1) <= recommended_on <= date(2026, 5, 31):
        contact -= 0.15

    reply = 0.51 + (0.03 if source == "ai" else 0)
    interview = 0.45 + (0.05 if source == "ai" else 0)
    if source == "ai" and job_category == "销售" and recommended_on >= date(2026, 4, 1):
        interview -= 0.13

    offer = 0.37 + (0.02 if job_category == "技术" else 0)
    hire = 0.69
    return {
        "contacted": contact,
        "replied": reply,
        "interviewed": interview,
        "offered": offer,
        "hired": hire,
    }


def _build_dimensions(
    rng: random.Random,
) -> tuple[list[Candidate], list[Job], list[Recruiter], list[ModelVersion]]:
    candidates = [
        Candidate(
            candidate_id=f"cand_{idx:05d}",
            region=rng.choice(REGIONS),
            experience_years=rng.randint(0, 15),
            education_level=rng.choices(EDUCATION_LEVELS, weights=[1, 7, 3, 1], k=1)[0],
            current_title=rng.choice(["工程师", "销售顾问", "运营专员", "产品经理", "数据分析师"]),
        )
        for idx in range(1, 5001)
    ]

    jobs = []
    job_idx = 1
    for category in JOB_CATEGORIES:
        for region in REGIONS:
            for seniority in SENIORITY_LEVELS:
                for _ in range(3):
                    jobs.append(
                        Job(
                            job_id=f"job_{job_idx:04d}",
                            job_category=category,
                            region=region,
                            seniority_level=seniority,
                            opened_at=date(2025, 12, 1) + timedelta(days=rng.randint(0, 160)),
                        )
                    )
                    job_idx += 1

    recruiters = [
        Recruiter(
            recruiter_id=f"rec_{idx:03d}",
            recruiter_name=f"Recruiter {idx:03d}",
            region=region,
            team=f"{region}招聘组",
        )
        for idx, region in enumerate(REGIONS * 4, start=1)
    ]

    model_versions = [
        ModelVersion(
            model_version_id="mv_human_rule",
            model_version="human_rule",
            deployed_at=date(2025, 1, 1),
            description="Human recruiter sourced recommendation baseline",
        ),
        ModelVersion(
            model_version_id="mv_ai_2026_q1",
            model_version="ai_ranker_2026_q1",
            deployed_at=date(2026, 1, 1),
            description="AI ranker used in 2026 Q1",
        ),
        ModelVersion(
            model_version_id="mv_ai_2026_q2",
            model_version="ai_ranker_2026_q2",
            deployed_at=date(2026, 4, 1),
            description="AI ranker used from 2026 Q2",
        ),
    ]
    return candidates, jobs, recruiters, model_versions


def seed_demo_metrics(session: Session, seed: int = 20260722) -> int:
    existing_recommendations = session.scalar(select(func.count()).select_from(Recommendation))
    if existing_recommendations:
        return 0

    rng = random.Random(seed)
    candidates, jobs, recruiters, model_versions = _build_dimensions(rng)
    session.add_all([*candidates, *jobs, *recruiters, *model_versions])
    session.flush()

    jobs_by_segment = defaultdict(list)
    for job in jobs:
        jobs_by_segment[(job.job_category, job.region)].append(job)
    recruiters_by_region = defaultdict(list)
    for recruiter in recruiters:
        recruiters_by_region[recruiter.region].append(recruiter)

    recommendations: list[Recommendation] = []
    events: list[FunnelEvent] = []
    daily_counts = defaultdict(lambda: dict.fromkeys(STAGES, 0))
    recommendation_idx = 1
    current = date(2026, 1, 1)

    while current <= date(2026, 6, 30):
        for source in SOURCES:
            for job_category in JOB_CATEGORIES:
                for region in REGIONS:
                    recommendation_count = rng.randint(1, 3)
                    for _ in range(recommendation_count):
                        recommendation_id = f"reco_{recommendation_idx:07d}"
                        recommended_at = _random_datetime(current, rng)
                        candidate = rng.choice(candidates)
                        job = rng.choice(jobs_by_segment[(job_category, region)])
                        recruiter = rng.choice(recruiters_by_region[region])
                        model_version_id = _model_version_for(current, source)
                        base_score = 0.68 if source == "ai" else 0.48
                        score = round(max(0.01, min(0.99, rng.gauss(base_score, 0.12))), 4)
                        recommendations.append(
                            Recommendation(
                                recommendation_id=recommendation_id,
                                candidate_id=candidate.candidate_id,
                                job_id=job.job_id,
                                recruiter_id=recruiter.recruiter_id,
                                model_version_id=model_version_id,
                                source=source,
                                recommendation_score=score,
                                recommended_at=recommended_at,
                            )
                        )

                        segment_key = (current, source, job_category, region)
                        daily_counts[segment_key]["recommended"] += 1
                        previous_at = recommended_at
                        stage_is_active = True
                        events.append(
                            FunnelEvent(
                                recommendation_id=recommendation_id,
                                stage="recommended",
                                status="completed",
                                event_at=recommended_at,
                            )
                        )
                        probabilities = _stage_probabilities(source, job_category, region, current)
                        for stage in STAGES[1:]:
                            completed = stage_is_active and _chance(probabilities[stage], rng)
                            event_at = previous_at + _stage_gap(stage, rng) if completed else None
                            events.append(
                                FunnelEvent(
                                    recommendation_id=recommendation_id,
                                    stage=stage,
                                    status="completed" if completed else "not_reached",
                                    event_at=event_at,
                                )
                            )
                            if completed:
                                daily_counts[segment_key][stage] += 1
                                previous_at = event_at
                            else:
                                stage_is_active = False

                        recommendation_idx += 1
        current += timedelta(days=1)

    session.add_all(recommendations)
    session.flush()
    session.add_all(events)

    if not session.scalar(select(func.count()).select_from(DailyFunnelMetric)):
        session.add_all(
            [
                DailyFunnelMetric(
                    metric_date=metric_date,
                    source=source,
                    job_category=job_category,
                    region=region,
                    recommended=counts["recommended"],
                    contacted=counts["contacted"],
                    replied=counts["replied"],
                    interviewed=counts["interviewed"],
                    offered=counts["offered"],
                    hired=counts["hired"],
                    data_origin="synthetic_event_rollup",
                )
                for (metric_date, source, job_category, region), counts in daily_counts.items()
            ]
        )

    session.commit()
    return len(recommendations)


# Compatibility name retained for the initial scaffold tests and scripts.
seed_demo_data = seed_demo_metrics
