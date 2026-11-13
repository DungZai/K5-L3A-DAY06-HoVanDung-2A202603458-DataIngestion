"""Validate gold annotations and measure retrieval of complete evidence."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import DocumentPage


def _fold(text: str) -> str:
    return " ".join(text.split())


def _gold(question: dict[str, Any]) -> list[dict[str, Any]]:
    return [question, *question.get("alternatives", [])]


def load_questions(root: Path, pages: list[DocumentPage]) -> list[dict[str, Any]]:
    path = root / "benchmark/questions.json"
    questions = json.loads(path.read_text(encoding="utf-8"))
    sources = {(page.document_id, page.page): page for page in pages}
    sections = {page.metadata["section"] for page in pages}
    identifiers = set()
    splits = defaultdict(int)
    filtered = defaultdict(int)
    for row in questions:
        question_id = row["id"]
        split = row["split"]
        if question_id in identifiers or not question_id or split not in ("dev", "test"):
            raise ValueError(f"ID trùng/rỗng hoặc split không hợp lệ: {question_id}")
        identifiers.add(question_id)
        splits[split] += 1
        for key in ("question", "expected_answer"):
            if not row[key].strip():
                raise ValueError(f"{question_id} thiếu {key}")
        filters = row.get("filter")
        if filters:
            if set(filters) != {"section"} or filters["section"] not in sections:
                raise ValueError(f"{question_id} có filter không hợp lệ: {filters}")
            filtered[split] += 1
        compatible_gold = False
        for evidence in _gold(row):
            source = sources[(evidence["gold_source_id"], evidence["gold_page"])]
            quote = _fold(evidence["evidence_quote"])
            if not quote or quote not in _fold(source.text):
                raise ValueError(f"Evidence không có trong trang nguồn: {question_id}")
            if not filters or filters["section"] == source.metadata["section"]:
                compatible_gold = True
        if not compatible_gold:
            raise ValueError(f"Filter loại mọi trang gold: {question_id}")
    if splits["dev"] < 15 or splits["test"] < 5:
        raise ValueError("Benchmark cần tối thiểu 15 dev và 5 test.")
    if sum(filtered.values()) < 3 or filtered["test"] < 1:
        raise ValueError("Benchmark cần tối thiểu 3 câu có filter, gồm ít nhất 1 test.")
    return questions


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    scored_hits = []
    for rank, hit in enumerate(hits, start=1):
        text = _fold(hit["text"])
        evidence_hit = any(
            hit["document_id"] == evidence["gold_source_id"]
            and hit["page"] == evidence["gold_page"]
            and _fold(evidence["evidence_quote"]) in text
            for evidence in _gold(question)
        )
        scored_hits.append({**hit, "rank": rank, "evidence_hit": evidence_hit})
    return {
        **question,
        "filter": question.get("filter"),
        "hits": scored_hits,
        "hit_at_1": bool(scored_hits and scored_hits[0]["evidence_hit"]),
        "evidence_hit_at_3": any(hit["evidence_hit"] for hit in scored_hits[:3]),
    }


def summarize(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = defaultdict(list)
    for trace in traces:
        groups[(trace["strategy"], trace["split"])].append(trace)
    return [
        {
            "strategy": strategy,
            "split": split,
            "questions": len(rows),
            "hit_at_1": sum(row["hit_at_1"] for row in rows),
            "evidence_hit_at_3": sum(row["evidence_hit_at_3"] for row in rows),
        }
        for (strategy, split), rows in sorted(groups.items())
    ]
