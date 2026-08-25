from aihr.services.document_store import InMemoryDocumentStore, create_document_store


def test_saved_recruitment_document_is_retrievable_with_sensitive_data_redacted() -> None:
    store = InMemoryDocumentStore()

    saved = store.save(
        document_type="resume",
        source_id="candidate-42",
        title="Data engineer resume for zhangsan@example.com",
        content=(
            "Candidate Zhang San, phone 13812345678, email zhangsan@example.com, "
            "national id 110105199001011234. Skilled in Python and SQL."
        ),
        metadata={
            "postgres_candidate_id": 42,
            "region": "Shanghai",
            "contacts": ["13812345678", {"email": "zhangsan@example.com"}],
        },
    )
    retrieved = store.get(saved.document_id)

    assert retrieved is not None
    assert retrieved.source_id == "candidate-42"
    assert retrieved.metadata["postgres_candidate_id"] == 42
    assert "zhangsan@example.com" not in retrieved.title
    assert retrieved.metadata["contacts"] == ["138****5678", {"email": "z***@example.com"}]
    assert "13812345678" not in retrieved.content
    assert "zhangsan@example.com" not in retrieved.content
    assert "110105199001011234" not in retrieved.content
    assert "138****5678" in retrieved.content
    assert "z***@example.com" in retrieved.content
    assert "110105********1234" in retrieved.content


def test_search_returns_ranked_documents_and_honors_document_type() -> None:
    store = InMemoryDocumentStore()
    store.save(
        document_type="resume",
        source_id="candidate-1",
        title="Python data engineer",
        content="Python SQL Spark data warehouse",
    )
    store.save(
        document_type="job",
        source_id="job-1",
        title="Data engineer role",
        content="Hiring a Python and SQL data engineer",
    )
    store.save(
        document_type="resume",
        source_id="candidate-2",
        title="Frontend engineer",
        content="React TypeScript CSS",
    )

    results = store.search("Python SQL", document_type="resume", limit=2)

    assert len(results) == 1
    assert results[0].document.source_id == "candidate-1"
    assert results[0].score == 2


def test_configured_mongodb_failure_falls_back_with_degraded_health() -> None:
    def unavailable_client(_url: str, **_kwargs):
        raise OSError("connection refused")

    store = create_document_store(
        mongo_url="mongodb://mongo:27017",
        database_name="aihr_documents",
        client_factory=unavailable_client,
    )

    health = store.health()
    assert store.backend_name == "memory"
    assert health.status == "degraded"
    assert health.backend == "memory"
    assert "connection refused" in health.detail


def test_saving_same_source_updates_document_without_creating_a_duplicate() -> None:
    store = InMemoryDocumentStore()
    first = store.save(
        document_type="knowledge_chunk",
        source_id="metric_dictionary.md#hire-rate",
        title="Hire rate",
        content="Old definition",
    )

    updated = store.save(
        document_type="knowledge_chunk",
        source_id="metric_dictionary.md#hire-rate",
        title="Hire rate definition",
        content="Hires divided by mature recommendations",
    )

    assert updated.document_id == first.document_id
    assert updated.title == "Hire rate definition"
    assert store.search("mature recommendations", limit=10)[0].document == updated
