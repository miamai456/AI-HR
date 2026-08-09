import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import AnalysisContextSnapshot, SystemDataVersion

DATASET_VERSION_KEY = "hiring_facts"


def get_dataset_version(session: Session) -> str:
    state = session.get(SystemDataVersion, DATASET_VERSION_KEY)
    return state.version if state is not None else "unversioned"


def bump_dataset_version(session: Session, *, reason: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    version = f"{timestamp}-{uuid4().hex[:12]}"
    state = session.get(SystemDataVersion, DATASET_VERSION_KEY)
    if state is None:
        session.add(
            SystemDataVersion(
                key=DATASET_VERSION_KEY,
                version=version,
                reason=reason,
            )
        )
    else:
        state.version = version
        state.reason = reason
    session.flush()
    return version


def analysis_scope_key(filters: dict[str, Any]) -> str:
    normalized = {key: value for key, value in filters.items() if value is not None}
    serialized = json.dumps(normalized, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


class DatabaseAnalysisSnapshotStore:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get(self, filters: dict[str, Any], dataset_version: str) -> dict | None:
        with self.session_factory() as session:
            snapshot = session.get(AnalysisContextSnapshot, analysis_scope_key(filters))
            if snapshot is None or snapshot.dataset_version != dataset_version:
                return None
            return json.loads(snapshot.payload_json)

    def set(
        self,
        filters: dict[str, Any],
        dataset_version: str,
        value: dict,
    ) -> None:
        scope_key = analysis_scope_key(filters)
        normalized = {key: item for key, item in filters.items() if item is not None}
        with self.session_factory() as session:
            snapshot = session.get(AnalysisContextSnapshot, scope_key)
            filters_json = json.dumps(normalized, sort_keys=True, default=str)
            payload_json = json.dumps(value, ensure_ascii=False, default=str)
            if snapshot is None:
                session.add(
                    AnalysisContextSnapshot(
                        scope_key=scope_key,
                        dataset_version=dataset_version,
                        filters_json=filters_json,
                        payload_json=payload_json,
                    )
                )
            else:
                snapshot.dataset_version = dataset_version
                snapshot.filters_json = filters_json
                snapshot.payload_json = payload_json
            session.commit()

    def status(self, dataset_version: str) -> dict[str, Any]:
        with self.session_factory() as session:
            current_count = session.scalar(
                select(func.count())
                .select_from(AnalysisContextSnapshot)
                .where(AnalysisContextSnapshot.dataset_version == dataset_version)
            )
            total_count = session.scalar(
                select(func.count()).select_from(AnalysisContextSnapshot)
            )
            latest_refresh = session.scalar(
                select(func.max(AnalysisContextSnapshot.refreshed_at)).where(
                    AnalysisContextSnapshot.dataset_version == dataset_version
                )
            )
        return {
            "current_snapshots": int(current_count or 0),
            "stale_snapshots": int(total_count or 0) - int(current_count or 0),
            "latest_refresh_at": latest_refresh,
        }
