import random
from collections import defaultdict
from dataclasses import dataclass
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
from aihr.services.analysis_snapshots import bump_dataset_version, get_dataset_version

STAGES = ["recommended", "contacted", "replied", "interviewed", "offered", "hired"]
JOB_CATEGORIES = ["技术", "销售", "运营"]
REGIONS = ["华东", "华北", "华南"]
SOURCES = ["ai", "human"]
EDUCATION_LEVELS = ["大专", "本科", "硕士", "博士"]
SENIORITY_LEVELS = ["junior", "mid", "senior"]
SyntheticRow = dict[str, object]


@dataclass(frozen=True)
class SyntheticHiringConfig:
    seed: int = 20260722
    n_candidates: int = 80_000
    n_jobs: int = 1_500
    n_recommendations: int = 100_000
    start_date: date = date(2026, 1, 1)
    end_date: date = date(2026, 6, 30)
    as_of_date: date = date(2026, 7, 15)
    batch_id: str = "synthetic_demo_20260722"


def _chance(probability: float, rng: random.Random) -> bool:
    return rng.random() < max(0.0, min(1.0, probability))


def _random_datetime(day: date, rng: random.Random) -> datetime:
    return datetime.combine(day, time(hour=rng.randint(9, 18), minute=rng.randint(0, 59)))


def _stage_gap(stage: str, rng: random.Random, region: str, recommended_on: date) -> timedelta:
    is_east_china_delay = (
        stage == "contacted"
        and region == "华东"
        and date(2026, 5, 1) <= recommended_on <= date(2026, 5, 31)
    )
    if is_east_china_delay:
        return timedelta(days=rng.randint(3, 6), hours=rng.randint(1, 8))

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


def _score_for(source: str, recommended_on: date, rng: random.Random) -> float:
    base_score = 0.68 if source == "ai" else 0.48
    if source == "ai" and recommended_on >= date(2026, 4, 1):
        base_score += 0.12
    return round(max(0.01, min(0.99, rng.gauss(base_score, 0.12))), 4)


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
    config: SyntheticHiringConfig,
) -> tuple[
    list[SyntheticRow],
    list[SyntheticRow],
    list[SyntheticRow],
    list[SyntheticRow],
]:
    candidates = []
    for idx in range(1, config.n_candidates + 1):
        candidates.append(
            {
                "candidate_id": f"cand_{idx:05d}",
                "region": rng.choice(REGIONS),
                "experience_years": rng.randint(0, 15),
                "education_level": rng.choices(EDUCATION_LEVELS, weights=[1, 7, 3, 1], k=1)[0],
                "current_title": rng.choice(
                    ["工程师", "销售顾问", "运营专员", "产品经理", "数据分析师"]
                ),
            }
        )

    jobs = []
    job_idx = 1
    while len(jobs) < config.n_jobs:
        for category in JOB_CATEGORIES:
            for region in REGIONS:
                for seniority in SENIORITY_LEVELS:
                    if len(jobs) >= config.n_jobs:
                        break
                    jobs.append(
                        {
                            "job_id": f"job_{job_idx:05d}",
                            "job_category": category,
                            "region": region,
                            "seniority_level": seniority,
                            "opened_at": date(2025, 12, 1) + timedelta(days=rng.randint(0, 160)),
                        }
                    )
                    job_idx += 1

    recruiters = [
        {
            "recruiter_id": f"rec_{idx:03d}",
            "recruiter_name": f"Recruiter {idx:03d}",
            "region": region,
            "team": f"{region}招聘组",
        }
        for idx, region in enumerate(REGIONS * 4, start=1)
    ]

    model_versions = [
        {
            "model_version_id": "mv_human_rule",
            "model_version": "human_rule",
            "deployed_at": date(2025, 1, 1),
            "description": "Human recruiter sourced recommendation baseline",
        },
        {
            "model_version_id": "mv_ai_2026_q1",
            "model_version": "ai_ranker_2026_q1",
            "deployed_at": date(2026, 1, 1),
            "description": "AI ranker used in 2026 Q1",
        },
        {
            "model_version_id": "mv_ai_2026_q2",
            "model_version": "ai_ranker_2026_q2",
            "deployed_at": date(2026, 4, 1),
            "description": "AI ranker used from 2026 Q2",
        },
    ]
    return candidates, jobs, recruiters, model_versions


def _pick_candidate(candidates: list[dict], source: str, rng: random.Random) -> dict:
    if source == "ai":
        for _ in range(8):
            candidate = rng.choice(candidates)
            if candidate["experience_years"] >= 5:
                return candidate
    return rng.choice(candidates)


def seed_demo_metrics(
    session: Session,
    seed: int = 20260722,
    config: SyntheticHiringConfig | None = None,
) -> int:
    existing_recommendations = session.scalar(select(func.count()).select_from(Recommendation))
    if existing_recommendations:
        if get_dataset_version(session) == "unversioned":
            bump_dataset_version(session, reason="existing_hiring_facts")
            session.commit()
        return 0

    config = config or SyntheticHiringConfig(seed=seed)
    rng = random.Random(config.seed)
    candidates, jobs, recruiters, model_versions = _build_dimensions(rng, config)
    session.bulk_insert_mappings(Candidate, candidates)
    session.bulk_insert_mappings(Job, jobs)
    session.bulk_insert_mappings(Recruiter, recruiters)
    session.bulk_insert_mappings(ModelVersion, model_versions)
    session.flush()

    jobs_by_segment = defaultdict(list)
    for job in jobs:
        jobs_by_segment[(job["job_category"], job["region"])].append(job)
    recruiters_by_region = defaultdict(list)
    for recruiter in recruiters:
        recruiters_by_region[recruiter["region"]].append(recruiter)

    recommendations: list[dict] = []
    events: list[dict] = []
    daily_counts = defaultdict(lambda: dict.fromkeys(STAGES, 0))
    recommendation_idx = 1
    current = config.start_date

    while recommendation_idx <= config.n_recommendations:
        for source in SOURCES:
            for job_category in JOB_CATEGORIES:
                for region in REGIONS:
                    recommendation_count = rng.randint(28, 34)
                    for _ in range(recommendation_count):
                        if recommendation_idx > config.n_recommendations:
                            break
                        recommendation_id = f"reco_{recommendation_idx:07d}"
                        recommended_at = _random_datetime(current, rng)
                        candidate = _pick_candidate(candidates, source, rng)
                        job = rng.choice(jobs_by_segment[(job_category, region)])
                        recruiter = rng.choice(recruiters_by_region[region])
                        model_version_id = _model_version_for(current, source)
                        score = _score_for(source, current, rng)
                        recommendations.append(
                            {
                                "recommendation_id": recommendation_id,
                                "candidate_id": candidate["candidate_id"],
                                "job_id": job["job_id"],
                                "recruiter_id": recruiter["recruiter_id"],
                                "model_version_id": model_version_id,
                                "source": source,
                                "recommendation_score": score,
                                "recommended_at": recommended_at,
                            }
                        )

                        segment_key = (current, source, job_category, region)
                        daily_counts[segment_key]["recommended"] += 1
                        previous_at = recommended_at
                        stage_is_active = True
                        events.append(
                            {
                                "recommendation_id": recommendation_id,
                                "stage": "recommended",
                                "status": "completed",
                                "event_at": recommended_at,
                            }
                        )
                        probabilities = _stage_probabilities(source, job_category, region, current)
                        for stage in STAGES[1:]:
                            completed = stage_is_active and _chance(probabilities[stage], rng)
                            event_at = (
                                previous_at + _stage_gap(stage, rng, region, current)
                                if completed
                                else None
                            )
                            events.append(
                                {
                                    "recommendation_id": recommendation_id,
                                    "stage": stage,
                                    "status": "completed" if completed else "not_reached",
                                    "event_at": event_at,
                                }
                            )
                            if completed:
                                daily_counts[segment_key][stage] += 1
                                previous_at = event_at
                            else:
                                stage_is_active = False

                        recommendation_idx += 1
        current += timedelta(days=1)
        if current > config.end_date:
            current = config.start_date

    session.bulk_insert_mappings(Recommendation, recommendations)
    session.flush()
    session.bulk_insert_mappings(FunnelEvent, events)

    if not session.scalar(select(func.count()).select_from(DailyFunnelMetric)):
        session.bulk_insert_mappings(
            DailyFunnelMetric,
            [
                {
                    "metric_date": metric_date,
                    "source": source,
                    "job_category": job_category,
                    "region": region,
                    "metric_name": "daily_interview_rate",
                    "numerator": counts["interviewed"],
                    "denominator": counts["recommended"],
                    "rate": (
                        round(counts["interviewed"] / counts["recommended"], 6)
                        if counts["recommended"]
                        else 0.0
                    ),
                    "sample_size": counts["recommended"],
                    "period_start": metric_date,
                    "period_end": metric_date,
                    "recommended": counts["recommended"],
                    "contacted": counts["contacted"],
                    "replied": counts["replied"],
                    "interviewed": counts["interviewed"],
                    "offered": counts["offered"],
                    "hired": counts["hired"],
                    "data_origin": "synthetic_event_rollup",
                    "metric_version": "seed_v1",
                }
                for (metric_date, source, job_category, region), counts in daily_counts.items()
            ]
        )

    bump_dataset_version(session, reason=f"seed:{config.batch_id}")
    session.commit()
    return len(recommendations)


def _completed_stage_rate(session: Session, stage: str, **filters) -> float:
    query = session.query(Recommendation.recommendation_id).join(Job)
    if source := filters.get("source"):
        query = query.filter(Recommendation.source == source)
    if job_category := filters.get("job_category"):
        query = query.filter(Job.job_category == job_category)
    if region := filters.get("region"):
        query = query.filter(Job.region == region)
    if start_date := filters.get("start_date"):
        query = query.filter(
            Recommendation.recommended_at >= datetime.combine(start_date, time.min)
        )
    if end_date := filters.get("end_date"):
        query = query.filter(Recommendation.recommended_at <= datetime.combine(end_date, time.max))

    recommendation_ids = query.subquery()
    denominator = session.query(func.count()).select_from(recommendation_ids).scalar() or 0
    if not denominator:
        return 0.0

    numerator = (
        session.query(func.count(FunnelEvent.event_id))
        .join(
            recommendation_ids,
            FunnelEvent.recommendation_id == recommendation_ids.c.recommendation_id,
        )
        .filter(FunnelEvent.stage == stage, FunnelEvent.status == "completed")
        .scalar()
        or 0
    )
    return numerator / denominator


def _average_contact_delay(
    session: Session,
    region: str,
    start_date: date,
    end_date: date,
) -> float:
    rows = (
        session.query(Recommendation.recommended_at, FunnelEvent.event_at)
        .join(Job, Recommendation.job_id == Job.job_id)
        .join(FunnelEvent, Recommendation.recommendation_id == FunnelEvent.recommendation_id)
        .filter(
            Job.region == region,
            Recommendation.recommended_at >= datetime.combine(start_date, time.min),
            Recommendation.recommended_at <= datetime.combine(end_date, time.max),
            FunnelEvent.stage == "contacted",
            FunnelEvent.status == "completed",
        )
        .all()
    )
    if not rows:
        return 0.0
    total_days = sum(
        (event_at - recommended_at).total_seconds() / 86_400
        for recommended_at, event_at in rows
    )
    return total_days / len(rows)


def detect_synthetic_scenarios(
    session: Session,
    as_of_date: date = date(2026, 7, 15),
) -> dict[str, bool]:
    ai_experience = (
        session.query(func.avg(Candidate.experience_years))
        .join(Recommendation, Candidate.candidate_id == Recommendation.candidate_id)
        .filter(Recommendation.source == "ai")
        .scalar()
        or 0
    )
    human_experience = (
        session.query(func.avg(Candidate.experience_years))
        .join(Recommendation, Candidate.candidate_id == Recommendation.candidate_id)
        .filter(Recommendation.source == "human")
        .scalar()
        or 0
    )

    sales_q1 = _completed_stage_rate(
        session,
        "interviewed",
        source="ai",
        job_category="销售",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    sales_q2 = _completed_stage_rate(
        session,
        "interviewed",
        source="ai",
        job_category="销售",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 6, 30),
    )

    east_april_delay = _average_contact_delay(session, "华东", date(2026, 4, 1), date(2026, 4, 30))
    east_may_delay = _average_contact_delay(session, "华东", date(2026, 5, 1), date(2026, 5, 31))

    ai_q1_score = (
        session.query(func.avg(Recommendation.recommendation_score))
        .filter(
            Recommendation.source == "ai",
            Recommendation.recommended_at >= datetime(2026, 1, 1),
            Recommendation.recommended_at <= datetime(2026, 3, 31, 23, 59, 59),
        )
        .scalar()
        or 0
    )
    ai_q2_score = (
        session.query(func.avg(Recommendation.recommendation_score))
        .filter(
            Recommendation.source == "ai",
            Recommendation.recommended_at >= datetime(2026, 4, 1),
            Recommendation.recommended_at <= datetime(2026, 6, 30, 23, 59, 59),
        )
        .scalar()
        or 0
    )

    immature_cutoff = datetime.combine(as_of_date - timedelta(days=30), time.min)
    immature_count = (
        session.query(func.count(Recommendation.recommendation_id))
        .filter(Recommendation.recommended_at > immature_cutoff)
        .scalar()
        or 0
    )

    return {
        "selection_bias": ai_experience - human_experience >= 1.0,
        "model_version_degradation": sales_q1 - sales_q2 >= 0.04,
        "recruiter_contact_delay": east_may_delay - east_april_delay >= 2.0,
        "feature_drift": ai_q2_score - ai_q1_score >= 0.08,
        "immature_cohort": immature_count > 0,
    }


# Compatibility name retained for the initial scaffold tests and scripts.
seed_demo_data = seed_demo_metrics
