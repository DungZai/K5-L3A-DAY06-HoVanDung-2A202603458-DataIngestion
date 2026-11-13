"""Validate and summarize the recorded qualitative review labels."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean


def read_indexed_jsonl(path: Path, key_fields: tuple[str, ...]) -> dict:
    rows = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = tuple(row[field] for field in key_fields)
            if key in rows:
                raise ValueError(f"{path.name}: duplicate record for {key}")
            rows[key] = row
    return rows


def read_labels(path: Path, key_fields: tuple[str, ...], expected_keys: set) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = {}
        for row in csv.DictReader(handle):
            key = tuple(row[field] for field in key_fields)
            if key in rows:
                raise ValueError(f"{path.name}: duplicate label for {key}")
            if not row["reason"].strip():
                raise ValueError(f"{path.name}: missing reason for {key}")
            rows[key] = row

    if rows.keys() != expected_keys:
        missing = sorted(expected_keys - rows.keys())
        extra = sorted(rows.keys() - expected_keys)
        raise ValueError(f"{path.name}: missing {missing}, unexpected {extra}")
    return rows


def scores_for_strategy(labels, strategy):
    scores = [int(row["score"]) for key, row in labels.items() if key[0] == strategy]
    if any(score not in (0, 1, 2) for score in scores):
        raise ValueError(f"{strategy}: scores must be 0, 1, or 2")
    return scores


def filter_compliance(traces, strategy):
    filtered = [trace for key, trace in traces.items() if key[0] == strategy and trace["filter"]]
    compliant = sum(
        bool(trace["hits"])
        and all(
            all(hit["metadata"].get(field) == value for field, value in trace["filter"].items())
            for hit in trace["hits"]
        )
        for trace in filtered
    )
    return {"correct": compliant, "total": len(filtered)} if filtered else None


def summarize_audits(results_dir: Path) -> dict:
    trace_key = ("strategy", "id")
    dev = read_indexed_jsonl(results_dir / "dev_traces.jsonl", trace_key)
    test = read_indexed_jsonl(results_dir / "test_traces.jsonl", trace_key)
    strategies = sorted({strategy for strategy, _ in test})
    if len(strategies) < 3 or set(strategies) != {strategy for strategy, _ in dev}:
        raise ValueError("Dev and test traces must contain the same three or more strategies")

    for traces, split, minimum in ((dev, "dev", 15), (test, "test", 5)):
        questions = {question_id for _, question_id in traces}
        if len(questions) < minimum or traces.keys() != {(s, q) for s in strategies for q in questions}:
            raise ValueError(f"Every strategy must cover the same {minimum} or more {split} questions")

    coherence_samples = read_indexed_jsonl(results_dir / "coherence_samples.jsonl", trace_key)
    anchors = {anchor for _, anchor in coherence_samples}
    if len(anchors) < 10 or coherence_samples.keys() != {(s, a) for s in strategies for a in anchors}:
        raise ValueError("Coherence must cover the same 10 or more source anchors per strategy")
    coherence = read_labels(
        results_dir / "coherence_audit.csv", ("strategy", "anchor_id"), set(coherence_samples)
    )
    for key, row in coherence.items():
        if row["chunk_id"] != coherence_samples[key]["chunk_id"]:
            raise ValueError(f"Coherence: wrong chunk ID for {key}")

    grounding = read_labels(results_dir / "grounding_audit.csv", ("strategy", "question_id"), set(test))
    expected_hits = {
        (strategy, question_id, str(rank)): hit["chunk_id"]
        for (strategy, question_id), trace in test.items()
        for rank, hit in enumerate(trace["hits"], start=1)
    }
    metadata = read_labels(
        results_dir / "metadata_audit.csv", ("strategy", "question_id", "rank"), set(expected_hits)
    )
    fields = ("source_ok", "page_ok", "section_ok")
    for key, row in metadata.items():
        if row["chunk_id"] != expected_hits[key]:
            raise ValueError(f"Metadata: wrong chunk ID for {key}")
        if any(row[field] not in ("0", "1") for field in fields):
            raise ValueError(f"Metadata: each field must be marked 0 or 1 for {key}")

    summary = {}
    for strategy in strategies:
        coherence_scores = scores_for_strategy(coherence, strategy)
        grounding_scores = scores_for_strategy(grounding, strategy)
        grounding_counts = Counter(grounding_scores)
        metadata_rows = [row for key, row in metadata.items() if key[0] == strategy]
        summary[strategy] = {
            "coherence": {"mean": mean(coherence_scores), "total": len(coherence_scores)},
            "metadata_test": {
                "correct": sum(all(row[field] == "1" for field in fields) for row in metadata_rows),
                "total": len(metadata_rows),
            },
            "filter_compliance": {
                "dev": filter_compliance(dev, strategy),
                "test": filter_compliance(test, strategy),
            },
            "grounding_test": {
                "counts": {str(score): grounding_counts[score] for score in range(3)},
                "mean": mean(grounding_scores),
                "total": len(grounding_scores),
            },
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Validate and summarize the recorded audit labels.")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    try:
        summary = summarize_audits(args.results_dir)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(status=1, message=f"Audit error: {exc}\n")
    output_path = args.results_dir / "audit_summary.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
