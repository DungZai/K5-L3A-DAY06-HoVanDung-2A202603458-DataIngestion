"""Read and validate the manifested snapshot, preserving source boundaries."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraph boundaries."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def load_corpus(root: Path) -> list[DocumentPage]:
    manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    units = {}
    for source in manifest["sources"]:
        for unit in source["units"]:
            key = (source["source_id"], unit["page"])
            if key in units:
                raise ValueError(f"Đơn vị bị lặp trong manifest: {key}")
            units[key] = unit

    pages = []
    seen = set()
    seen_digests = set()
    corpus = root / manifest["corpus_path"]
    with corpus.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                row = json.loads(line)
                key = (row["document_id"], row["page"])
                unit = units[key]
                content = normalize_text(row["text"])
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                if key in seen or digest in seen_digests or not content:
                    raise ValueError(f"Đơn vị rỗng hoặc trùng nội dung: {key}")
                if digest != unit["sha256"] or len(content) != unit["character_count"]:
                    raise ValueError(f"Nội dung không khớp checksum/số ký tự: {key}")
                for field in ("source", "title", "section"):
                    if not row[field] or row[field] != unit[field]:
                        raise ValueError(f"{field} không khớp manifest: {key}")
                pages.append(
                    DocumentPage(key[0], row["source"], key[1], content, {
                        "section": row["section"],
                        "title": row["title"],
                    })
                )
                seen.add(key)
                seen_digests.add(digest)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"{corpus.name}:{line_number}: {error}") from error

    if seen != set(units) or len(pages) < 30:
        raise ValueError("Corpus phải khớp manifest và có ít nhất 30 đơn vị nguồn.")
    if len({page.metadata["section"] for page in pages}) < 2:
        raise ValueError("Corpus cần ít nhất hai phạm vi section để đánh giá filter.")
    return pages
