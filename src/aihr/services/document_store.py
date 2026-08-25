import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")
NATIONAL_ID_PATTERN = re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3}[\dXx])(?!\d)")


def redact_sensitive_text(content: str) -> str:
    content = EMAIL_PATTERN.sub(r"\1***\2", content)
    content = PHONE_PATTERN.sub(r"\1****\3", content)
    return NATIONAL_ID_PATTERN.sub(r"\1********\3", content)


def redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {key: redact_sensitive_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_value(item) for item in value)
    return value


@dataclass(frozen=True)
class RecruitmentDocument:
    document_id: str
    document_type: str
    source_id: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class DocumentSearchResult:
    document: RecruitmentDocument
    score: int


@dataclass(frozen=True)
class DocumentStoreHealth:
    status: str
    backend: str
    detail: str = ""


class DocumentStore(Protocol):
    backend_name: str

    def save(
        self,
        *,
        document_type: str,
        source_id: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> RecruitmentDocument: ...

    def get(self, document_id: str) -> RecruitmentDocument | None: ...

    def search(
        self,
        query: str,
        *,
        document_type: str | None = None,
        limit: int = 10,
    ) -> list[DocumentSearchResult]: ...

    def health(self) -> DocumentStoreHealth: ...


class InMemoryDocumentStore:
    backend_name = "memory"

    def __init__(self, *, health_status: str = "available", detail: str = "") -> None:
        self._documents: dict[str, RecruitmentDocument] = {}
        self._health_status = health_status
        self._health_detail = detail

    def save(
        self,
        *,
        document_type: str,
        source_id: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> RecruitmentDocument:
        now = datetime.now(timezone.utc)
        existing = next(
            (
                document
                for document in self._documents.values()
                if document.document_type == document_type and document.source_id == source_id
            ),
            None,
        )
        document = RecruitmentDocument(
            document_id=existing.document_id if existing else str(uuid4()),
            document_type=document_type,
            source_id=source_id,
            title=redact_sensitive_text(title),
            content=redact_sensitive_text(content),
            metadata=redact_sensitive_value(dict(metadata or {})),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._documents[document.document_id] = document
        return document

    def get(self, document_id: str) -> RecruitmentDocument | None:
        return self._documents.get(document_id)

    def search(
        self,
        query: str,
        *,
        document_type: str | None = None,
        limit: int = 10,
    ) -> list[DocumentSearchResult]:
        terms = {term.lower() for term in re.findall(r"[\w-]+", query) if len(term) > 1}
        matches: list[DocumentSearchResult] = []
        for document in self._documents.values():
            if document_type and document.document_type != document_type:
                continue
            searchable = f"{document.title} {document.content}".lower()
            score = sum(term in searchable for term in terms)
            if score:
                matches.append(DocumentSearchResult(document=document, score=score))
        matches.sort(key=lambda result: (-result.score, result.document.document_id))
        return matches[: max(1, min(limit, 100))]

    def health(self) -> DocumentStoreHealth:
        return DocumentStoreHealth(
            status=self._health_status,
            backend=self.backend_name,
            detail=self._health_detail,
        )


class MongoDocumentStore:
    backend_name = "mongodb"

    def __init__(self, client: Any, database_name: str) -> None:
        self._client = client
        self._collection = client[database_name]["recruitment_documents"]
        client.admin.command("ping")
        self._collection.create_index("document_id", unique=True)
        self._collection.create_index([("document_type", 1), ("source_id", 1)], unique=True)
        self._collection.create_index("expires_at", expireAfterSeconds=0)
        self._collection.create_index([("title", "text"), ("content", "text")])

    def save(
        self,
        *,
        document_type: str,
        source_id: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> RecruitmentDocument:
        from pymongo import ReturnDocument

        now = datetime.now(timezone.utc)
        candidate = RecruitmentDocument(
            document_id=str(uuid4()),
            document_type=document_type,
            source_id=source_id,
            title=redact_sensitive_text(title),
            content=redact_sensitive_text(content),
            metadata=redact_sensitive_value(dict(metadata or {})),
            created_at=now,
            updated_at=now,
        )
        payload = _document_to_dict(candidate)
        insert_fields = {
            "document_id": payload.pop("document_id"),
            "created_at": payload.pop("created_at"),
        }
        if document_type in {"conversation", "tool_audit"}:
            payload["expires_at"] = now + timedelta(days=180)
        stored = self._collection.find_one_and_update(
            {"document_type": document_type, "source_id": source_id},
            {"$set": payload, "$setOnInsert": insert_fields},
            upsert=True,
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        return _document_from_dict(stored)

    def get(self, document_id: str) -> RecruitmentDocument | None:
        payload = self._collection.find_one({"document_id": document_id}, {"_id": 0})
        return _document_from_dict(payload) if payload else None

    def search(
        self,
        query: str,
        *,
        document_type: str | None = None,
        limit: int = 10,
    ) -> list[DocumentSearchResult]:
        filters: dict[str, Any] = {"$text": {"$search": query}}
        if document_type:
            filters["document_type"] = document_type
        cursor = self._collection.find(
            filters,
            {"_id": 0, "score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})])
        results = []
        for payload in cursor.limit(max(1, min(limit, 100))):
            score = int(round(payload.pop("score", 0)))
            results.append(DocumentSearchResult(_document_from_dict(payload), score))
        return results

    def health(self) -> DocumentStoreHealth:
        try:
            self._client.admin.command("ping")
        except Exception as exc:
            return DocumentStoreHealth("degraded", self.backend_name, str(exc))
        return DocumentStoreHealth("available", self.backend_name)


def create_document_store(
    *,
    mongo_url: str,
    database_name: str,
    client_factory: Callable[..., Any] | None = None,
) -> DocumentStore:
    if not mongo_url:
        return InMemoryDocumentStore(health_status="optional", detail="MongoDB is not configured")
    try:
        if client_factory is None:
            from pymongo import MongoClient

            client_factory = MongoClient
        client = client_factory(mongo_url, serverSelectionTimeoutMS=2_000)
        return MongoDocumentStore(client, database_name)
    except Exception as exc:
        return InMemoryDocumentStore(health_status="degraded", detail=str(exc))


def _document_to_dict(document: RecruitmentDocument) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "document_type": document.document_type,
        "source_id": document.source_id,
        "title": document.title,
        "content": document.content,
        "metadata": document.metadata,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _document_from_dict(payload: dict[str, Any]) -> RecruitmentDocument:
    return RecruitmentDocument(
        document_id=payload["document_id"],
        document_type=payload["document_type"],
        source_id=payload["source_id"],
        title=payload["title"],
        content=payload["content"],
        metadata=payload.get("metadata", {}),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )
