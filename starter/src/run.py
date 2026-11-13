"""Run ingestion and holdout evaluation from the project root."""

import argparse
import csv
import hashlib
import json
import logging
import platform
import re
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from statistics import median
from time import perf_counter
from zoneinfo import ZoneInfo

from .chunking import by_paragraph, fixed_size
from .evaluation import evaluate_query, load_questions, summarize
from .ingestion import load_corpus

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
CACHE = ROOT / ".lab-cache"
CONFIG = ROOT / "artifacts/strategies.json"
LOGGER = logging.getLogger("day6")


class LabFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        time = datetime.fromtimestamp(record.created, ZoneInfo("Asia/Ho_Chi_Minh"))
        return time.isoformat(timespec="seconds")


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _fingerprint() -> dict[str, str]:
    paths = [
        CONFIG, ROOT / "data/manifest.json", ROOT / "data/corpus.jsonl",
        ROOT / "benchmark/questions.json", ROOT / "benchmark/coherence_anchors.json",
        ROOT / "starter/requirements.txt",
    ]
    paths.extend(sorted(Path(__file__).parent.glob("*.py")))
    return {
        path.relative_to(ROOT).as_posix():
            hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        for path in paths if path.name != "audit.py"
    }


def _load_anchors(pages) -> list[dict]:
    anchors = _read_json(ROOT / "benchmark/coherence_anchors.json")
    source_units = {(page.document_id, page.page): page for page in pages}
    identifiers = set()
    positions = set()
    for anchor in anchors:
        key = (anchor["source_id"], anchor["page"])
        words = anchor["quote"].split()
        pattern = r"\s+".join(re.escape(word) for word in words)
        matches = list(re.finditer(pattern, source_units[key].text)) if words else []
        if len(matches) != 1 or not anchor["id"] or anchor["id"] in identifiers:
            raise ValueError(f"Anchor phải có ID và vị trí duy nhất: {anchor}")
        anchor["start_char"], anchor["end_char"] = matches[0].span()
        position = (*key, anchor["start_char"])
        if position in positions:
            raise ValueError(f"Anchor trùng vị trí nguồn: {anchor}")
        identifiers.add(anchor["id"])
        positions.add(position)
    if len(anchors) < 10:
        raise ValueError("Cần ít nhất 10 vị trí audit coherence.")
    return anchors


def _sample_coherence(anchors: list[dict], strategies: dict, by_index: dict) -> None:
    samples = []
    for strategy, config in strategies.items():
        for anchor in anchors:
            left, right = anchor["start_char"], anchor["end_char"]
            candidates = [
                chunk for chunk in by_index[config["index"]]
                if (chunk.document_id, chunk.page) == (anchor["source_id"], anchor["page"])
                and chunk.metadata["start_char"] < right and chunk.metadata["end_char"] > left
            ]
            # Prefer maximum anchor coverage, then use the earliest span to break ties.
            def order(chunk):
                start, end = chunk.metadata["start_char"], chunk.metadata["end_char"]
                return (min(right, end) - max(left, start), -start)

            selected = max(candidates, key=order)
            samples.append({
                **anchor, "strategy": strategy, "chunk_id": selected.chunk_id,
                "source": selected.source, "chunk_start_char": selected.metadata["start_char"],
                "chunk_end_char": selected.metadata["end_char"], "text": selected.text,
            })
    _write_jsonl(RESULTS / "coherence_samples.jsonl", samples)


def _distribution(lengths: list[int]) -> dict:
    return {
        "min": min(lengths), "median": median(lengths), "max": max(lengths),
        "mean": round(sum(lengths) / len(lengths), 2), "total": sum(lengths),
    }


def _build_indexes(pages, strategies: dict, embedder, store) -> tuple[dict, dict]:
    chunks_by_index, stats = {}, {}
    for config in strategies.values():
        index = config["index"]
        if index in chunks_by_index:
            continue
        started = perf_counter()
        chunks = []
        for page in pages:
            if config["chunking"] == "fixed":
                chunks.extend(fixed_size(page, config["size"], config["overlap"]))
            else:
                chunks.extend(by_paragraph(page, config["size"]))
        texts = [chunk.text for chunk in chunks]
        vectors = embedder.embed_documents(texts)
        store.replace(index, chunks, vectors)
        elapsed = perf_counter() - started
        count = store.count(index)
        if count != len(chunks):
            raise RuntimeError(f"Index {index} có {count} thay vì {len(chunks)} chunk.")

        repeated_at = perf_counter()
        store.replace(index, chunks, vectors)
        repeated_count = store.count(index)
        if repeated_count != count:
            raise RuntimeError(f"Nạp lại index {index} làm đổi số chunk.")
        stats[index] = {
            "count": count,
            "characters": _distribution([len(text) for text in texts]),
            "tokens_with_special": _distribution(embedder.token_counts(texts)),
            "ingest_seconds": round(elapsed, 4),
            "reload_seconds_reusing_vectors": round(perf_counter() - repeated_at, 4),
            "count_after_same_version_reload": repeated_count,
            "api_cost_usd": 0,
        }
        chunks_by_index[index] = chunks
        LOGGER.info("Index %s: %s chunks, %.3fs, reload %s", index, count, elapsed, repeated_count)
    return chunks_by_index, stats


def _retrieve(questions: list[dict], split: str, config: dict, embedder, store) -> list[dict]:
    traces = []
    for question in questions:
        if question["split"] != split:
            continue
        vector = embedder.embed_query(question["question"])
        for strategy, options in config["strategies"].items():
            filters = question.get("filter") if options["filter"] else None
            started = perf_counter()
            hits = store.search(options["index"], vector, config["top_k"], filters)
            elapsed = (perf_counter() - started) * 1000
            traces.append({
                **evaluate_query(question, hits), "strategy": strategy,
                "applied_filter": filters, "search_ms_excluding_embedding": round(elapsed, 3),
            })
    return traces


def _write_metrics(rows: list[dict]) -> None:
    path = RESULTS / "retrieval_metrics.csv"
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _runtime(embedder) -> dict:
    return {
        "python": platform.python_version(), "system": platform.system(),
        "provider": embedder.provider, "model": embedder.model_name,
        "model_revision": embedder.model_revision, "dimensions": embedder.dimensions,
        "model_repository": embedder.model_repository, "query_prefix": embedder.query_prefix,
        "max_tokens": embedder.max_tokens, "batch_size": embedder.batch_size,
        "qdrant_client": version("qdrant-client"), "onnxruntime": version("onnxruntime"),
        "tokenizers": version("tokenizers"), "numpy": version("numpy"),
        "distance": "cosine", "search": "exact",
    }


def run(phase: str) -> None:
    pages = load_corpus(ROOT)
    questions = load_questions(ROOT, pages)
    anchors = _load_anchors(pages)
    LOGGER.info("Verified %s source units, %s questions and %s anchors",
                len(pages), len(questions), len(anchors))
    if phase == "validate":
        return

    from .embeddings import LocalEmbedder
    from .store import QdrantStore

    config = _read_json(CONFIG)
    fingerprint = _fingerprint()
    embedder = LocalEmbedder(CACHE / "models")
    runtime = _runtime(embedder)
    selection_path = RESULTS / "selection.json"

    if phase == "dev":
        with QdrantStore(CACHE / "qdrant", embedder.dimensions) as store:
            chunks, stats = _build_indexes(pages, config["strategies"], embedder, store)
    else:
        selection = _read_json(selection_path)
        if selection["fingerprint"] != fingerprint or selection["runtime"] != runtime:
            raise RuntimeError("Dữ liệu, code hoặc runtime đã đổi sau khi chốt dev. Chạy lại dev.")
        stats = _read_json(RESULTS / "index_stats.json")["indexes"]

    with QdrantStore(CACHE / "qdrant", embedder.dimensions) as store:
        for index, index_stats in stats.items():
            if store.count(index) != index_stats["count"]:
                raise RuntimeError(f"Index {index} không khớp số chunk đã nạp.")
        traces = _retrieve(questions, phase, config, embedder, store)
    rows = summarize(traces)
    _write_jsonl(RESULTS / f"{phase}_traces.jsonl", traces)
    if phase == "dev":
        _sample_coherence(anchors, config["strategies"], chunks)
        _write_json(RESULTS / "index_stats.json", {"recorded_at": _timestamp(), **runtime, "indexes": stats})
        selected = min(rows, key=lambda row: (
            -row["evidence_hit_at_3"], -row["hit_at_1"], row["strategy"]
        ))["strategy"]
        _write_metrics(rows)
        _write_json(selection_path, {
            "selected_at": _timestamp(), "selected_strategy": selected,
            "selection_policy": config["selection"], "dev_metrics": rows,
            "fingerprint": fingerprint, "runtime": runtime,
        })
        LOGGER.info("Selected %s using dev only", selected)
    else:
        _write_metrics(selection["dev_metrics"] + rows)
        _write_json(RESULTS / "test_run.json", {
            "run_at": _timestamp(), "selected_strategy_from_dev": selection["selected_strategy"],
            "selection_timestamp": selection["selected_at"], "test_metrics": rows,
        })
    for row in rows:
        LOGGER.info("%s %s: Hit@1 %s/%s, Evidence Hit@3 %s/%s", row["strategy"], phase,
                    row["hit_at_1"], row["questions"], row["evidence_hit_at_3"], row["questions"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("validate", "dev", "test"), required=True)
    args = parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    formatter = LabFormatter("%(asctime)s %(levelname)s %(message)s")
    handlers = [logging.StreamHandler(), logging.FileHandler(
        RESULTS / "pipeline.log", encoding="utf-8"
    )]
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers)
    try:
        run(args.phase)
    except Exception:
        LOGGER.exception("Pipeline failed during %s", args.phase)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
