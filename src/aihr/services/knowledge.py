from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeChunk:
    source_id: str
    title: str
    text: str
    score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(value: str) -> set[str]:
    lowered = value.lower()
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    words.update(chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0)))
    return {token for token in words if token}


class DocumentRetriever:
    def __init__(self, docs_root: Path, document_names: tuple[str, ...] | None = None) -> None:
        names = document_names or (
            "metric_dictionary.md",
            "架构与数据流.md",
            "运行与验证.md",
            "03_数据模型详解.md",
        )
        self.chunks = self._load(docs_root, names)

    @staticmethod
    def _load(root: Path, names: tuple[str, ...]) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        candidates = [path for path in root.rglob("*.md") if path.name in names]
        for path in candidates:
            title = path.stem
            section = "overview"
            lines: list[str] = []

            def add_chunk(section_name: str, section_lines: list[str], source_path: Path) -> None:
                section_text = "\n".join(section_lines).strip()
                if section_text:
                    relative = source_path.relative_to(root).as_posix()
                    anchor = re.sub(
                        r"[^a-z0-9\u4e00-\u9fff]+", "-", section_name.lower()
                    ).strip("-")
                    chunks.append(
                        KnowledgeChunk(f"{relative}#{anchor}", section_name, section_text[:1800])
                    )

            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("#"):
                    add_chunk(section, lines, path)
                    lines.clear()
                    section = line.lstrip("#").strip() or title
                else:
                    lines.append(line)
            add_chunk(section, lines, path)
        return chunks

    def search(self, query: str, top_k: int = 3, min_score: float = 0.15) -> list[KnowledgeChunk]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored = []
        for chunk in self.chunks:
            tokens = _tokens(f"{chunk.title} {chunk.text}")
            overlap = len(query_tokens & tokens)
            score = overlap / max(len(query_tokens), 1)
            if score >= min_score:
                scored.append(KnowledgeChunk(chunk.source_id, chunk.title, chunk.text, score))
        return sorted(scored, key=lambda item: (-item.score, item.source_id))[:top_k]
