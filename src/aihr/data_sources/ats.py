"""Import a privacy-preserving, authorized ATS CSV export.

The adapter deliberately accepts an export rather than guessing at a vendor
API. It verifies an authorization ticket, hashes external identifiers before
storage, validates referential integrity, and commits atomically.
"""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from aihr.models import FunnelEvent, Recommendation

RECOMMENDATION_COLUMNS = {
    "recommendation_id",
    "candidate_id",
    "job_id",
    "recruiter_id",
    "model_version_id",
    "source",
    "recommendation_score",
    "recommended_at",
}
EVENT_COLUMNS = {"recommendation_id", "stage", "status", "event_at"}
VALID_SOURCES = {"ai", "human"}
VALID_STAGES = {"contacted", "replied", "interviewed", "offered", "hired"}
VALID_STATUSES = {"completed", "skipped"}


class ATSImportError(ValueError):
    """Raised when an ATS export is not authorized or is malformed."""


@dataclass(frozen=True)
class ATSImportReport:
    source_system: str
    recommendations_read: int
    events_read: int
    recommendations_inserted: int
    events_inserted: int
    external_ids_hashed: bool = True


def _authorization_check(ticket: str | None) -> None:
    expected = os.getenv("AIHR_ATS_IMPORT_AUTHORIZATION")
    if not expected or not ticket or not hashlib.sha256(ticket.encode()).hexdigest() == expected:
        raise ATSImportError("ATS 导入未授权：请配置 AIHR_ATS_IMPORT_AUTHORIZATION")


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = sorted(required - columns)
        if missing:
            raise ATSImportError(f"{path.name} 缺少字段: {', '.join(missing)}")
        return list(reader)


def _external_id(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:32]


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ATSImportError(f"{field} 不是有效的 ISO 时间: {value}") from exc


def import_ats_csv(
    session: Session,
    recommendations_path: str | Path,
    events_path: str | Path,
    *,
    authorization_ticket: str | None,
    source_system: str = "authorized_ats",
    hash_salt: str | None = None,
) -> ATSImportReport:
    """Atomically import recommendations and funnel events from an ATS export."""

    _authorization_check(authorization_ticket)
    salt = hash_salt or os.getenv("AIHR_ATS_HASH_SALT")
    if not salt:
        raise ATSImportError("ATS 导入缺少 AIHR_ATS_HASH_SALT，拒绝写入未脱敏标识")

    recommendation_rows = _read_csv(Path(recommendations_path), RECOMMENDATION_COLUMNS)
    event_rows = _read_csv(Path(events_path), EVENT_COLUMNS)
    recommendation_ids: set[str] = set()
    recommendations: list[Recommendation] = []
    for row in recommendation_rows:
        if row["source"] not in VALID_SOURCES:
            raise ATSImportError(f"source 无效: {row['source']}")
        recommendation_id = _external_id(row["recommendation_id"], salt)
        if recommendation_id in recommendation_ids:
            raise ATSImportError(f"推荐记录重复: {row['recommendation_id']}")
        recommendation_ids.add(recommendation_id)
        try:
            score = float(row["recommendation_score"])
        except ValueError as exc:
            raise ATSImportError("recommendation_score 必须是数字") from exc
        recommendations.append(
            Recommendation(
                recommendation_id=recommendation_id,
                candidate_id=_external_id(row["candidate_id"], salt),
                job_id=_external_id(row["job_id"], salt),
                recruiter_id=_external_id(row["recruiter_id"], salt),
                model_version_id=_external_id(row["model_version_id"], salt),
                source=row["source"],
                recommendation_score=score,
                recommended_at=_parse_datetime(row["recommended_at"], "recommended_at"),
                data_origin=source_system,
            )
        )

    events: list[FunnelEvent] = []
    for row in event_rows:
        recommendation_id = _external_id(row["recommendation_id"], salt)
        if recommendation_id not in recommendation_ids:
            raise ATSImportError(f"事件找不到推荐记录: {row['recommendation_id']}")
        if row["stage"] not in VALID_STAGES or row["status"] not in VALID_STATUSES:
            raise ATSImportError(f"事件阶段或状态无效: {row['stage']}/{row['status']}")
        events.append(
            FunnelEvent(
                recommendation_id=recommendation_id,
                stage=row["stage"],
                status=row["status"],
                event_at=_parse_datetime(row["event_at"], "event_at") if row["event_at"] else None,
                data_origin=source_system,
            )
        )

    session.add_all(recommendations + events)
    session.commit()
    return ATSImportReport(
        source_system,
        len(recommendation_rows),
        len(event_rows),
        len(recommendations),
        len(events),
    )
