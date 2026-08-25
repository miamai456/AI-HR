import json
from pathlib import Path

from aihr.config import get_settings
from aihr.services.document_store import create_document_store
from aihr.services.knowledge import DocumentRetriever


def main() -> None:
    settings = get_settings()
    store = create_document_store(
        mongo_url=settings.mongo_url,
        database_name=settings.mongo_database,
    )
    if store.backend_name != "mongodb":
        raise SystemExit(f"MongoDB is required for indexing: {store.health().detail}")

    docs_root = Path(__file__).resolve().parents[1] / "docs"
    retriever = DocumentRetriever(docs_root)
    for chunk in retriever.chunks:
        store.save(
            document_type="knowledge_chunk",
            source_id=chunk.source_id,
            title=chunk.title,
            content=chunk.text,
            metadata={"source": "repository_docs", "format": "markdown"},
        )

    print(
        json.dumps(
            {
                "status": "indexed",
                "backend": store.backend_name,
                "documents": len(retriever.chunks),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
