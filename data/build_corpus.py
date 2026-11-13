"""Rebuild the normalized Pro Git corpus from a pinned upstream archive."""

import argparse
import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile


REVISION = "a013e3230a1207cfa5ae94d28ba7d2021063c337"
UPSTREAM = "https://github.com/progit/progit2"
ARCHIVE_URL = f"https://codeload.github.com/progit/progit2/zip/{REVISION}"
BOOK_URL = "https://git-scm.com/book/en/v2"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/3.0/"
SOURCE_ID = "pro-git-2e"
ACCESSED_AT = "2026-11-13"
CHAPTERS = {"01", "02", "03", "07", "08", "10"}
MIN_CHARACTERS = 1500
DATA_DIR = Path(__file__).resolve().parent
HEADING = re.compile(r"^(={3,6})\s+(.+)$")
INDEX_TERM = re.compile(r"\(\(\(.+?\)\)\)")
CONTROL_LINE = re.compile(
    r"^(?:\[\[.+\]\]|\[(?:source|cols=|options=)[^\]]*\]|(?:image|include)::.+)$"
)
ADMONITION = re.compile(r"^\[(NOTE|TIP|WARNING|IMPORTANT|CAUTION)\]$")
HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_CREDENTIALS = re.compile(r"(https?://)[^:/@\s]+:[^/@\s]+@")


def normalize_source(source: str) -> str:
    """Preserve prose, headings, and inline examples without rendering media."""
    lines = unicodedata.normalize("NFC", source).splitlines()
    normalized = []
    in_example = False
    for index, original in enumerate(lines):
        line = HORIZONTAL_WHITESPACE.sub(" ", original).strip()
        if line == "----":
            in_example = not in_example
            normalized.append("```")
            continue
        if in_example:
            normalized.append(line)
            continue
        if CONTROL_LINE.fullmatch(line):
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if line.startswith(".") and next_line.startswith("image::"):
            continue
        if heading := HEADING.fullmatch(line):
            level, title = heading.groups()
            line = f"{'#' * (len(level) - 2)} {title}"
        if admonition := ADMONITION.fullmatch(line):
            line = f"{admonition.group(1)}:"
        if line in {"====", "****", "____"}:
            line = ""
        normalized.append(INDEX_TERM.sub("", line).strip())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(normalized)).strip()
    return EMAIL.sub("[redacted email]", text)


def extract_units(archive: ZipFile) -> tuple[list[dict], list[dict], list[dict]]:
    corpus, units, excluded = [], [], []
    for name in sorted(archive.namelist()):
        path = PurePosixPath(name)
        if len(path.parts) != 5 or path.parts[0] != f"progit2-{REVISION}":
            continue
        _, root, chapter, section_dir, _ = path.parts
        if root != "book" or section_dir != "sections" or path.suffix != ".asc":
            continue
        if chapter.split("-", 1)[0] not in CHAPTERS:
            continue
        source_path = PurePosixPath(*path.parts[1:]).as_posix()
        text = normalize_source(archive.read(name).decode("utf-8"))
        if len(text) < MIN_CHARACTERS:
            excluded.append({"source_path": source_path, "character_count": len(text)})
            continue
        if path.stem == "credentials":
            text = URL_CREDENTIALS.sub(r"\1", text).replace("s3cre7", "[redacted password]")
        title = text.splitlines()[0].lstrip("#").strip()
        page = f"{chapter}/{path.stem}"
        metadata = {
            "source": f"{UPSTREAM}/blob/{REVISION}/{source_path}",
            "page": page,
            "title": title,
            "section": chapter,
        }
        corpus.append({"document_id": SOURCE_ID, **metadata, "text": text})
        units.append({
            **metadata,
            "source_path": source_path,
            "character_count": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    if len(corpus) < 30:
        raise ValueError("Expected at least 30 substantive sections in the pinned archive")
    return corpus, units, excluded


def build_manifest(units: list[dict], excluded: list[dict]) -> dict:
    character_count = sum(unit["character_count"] for unit in units)
    return {
        "corpus_path": "data/corpus.jsonl",
        "total_units": len(units),
        "total_characters": character_count,
        "unit_counting_rule": (
            "One distinct upstream AsciiDoc section under book/<chapter>/sections is "
            "one traceable unit. Keep core Git chapters 01, 02, 03, 07, 08 and 10, "
            "and require at least 1500 normalized characters per section. "
            "Exclude front matter, appendices, summaries, other chapters, and images."
        ),
        "normalization": (
            "UTF-8 and NFC; trim lines, collapse horizontal whitespace and repeated blank "
            "lines; preserve paragraph, heading and inline example boundaries; convert "
            "headings to Markdown; omit source directives, external includes, image "
            "references/captions, internal anchors and index terms. Redact email addresses "
            "and sample credentials from command examples. Inline AsciiDoc may remain."
        ),
        "rebuild": "python data/build_corpus.py",
        "archive_url": ARCHIVE_URL,
        "sha256_definition": "SHA-256 of normalized text encoded in UTF-8, without a trailing LF.",
        "metadata_fields": {
            "document_id": "String, lab identifier of the upstream edition.",
            "source": "String, pinned upstream URL for an individual section.",
            "page": "String, stable chapter-slug/section-filename identifier.",
            "title": "String, top-level heading in the upstream section file.",
            "section": "String, upstream chapter directory used for metadata filtering.",
        },
        "sources": [{
            "source_id": SOURCE_ID,
            "title": "Pro Git, 2nd Edition",
            "authors": ["Scott Chacon", "Ben Straub"],
            "publisher": "Apress",
            "publication_year": 2014,
            "source_path_or_url": BOOK_URL,
            "license_or_permission": "CC BY-NC-SA 3.0 Unported",
            "license_url": LICENSE_URL,
            "upstream_license_url": f"{UPSTREAM}/blob/{REVISION}/LICENSE.asc",
            "accessed_at": ACCESSED_AT,
            "snapshot": REVISION,
            "unit_count": len(units),
            "character_count": character_count,
            "units": units,
            "excluded_short_units": excluded,
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an existing copy of the pinned ZIP.")
    args = parser.parse_args()
    if args.archive:
        source = args.archive.read_bytes()
    else:
        with urlopen(ARCHIVE_URL, timeout=60) as response:
            source = response.read()
    with ZipFile(io.BytesIO(source)) as archive:
        corpus, units, excluded = extract_units(archive)
        license_path = f"progit2-{REVISION}/LICENSE.asc"
        license_notice = archive.read(license_path).decode("utf-8").strip()
    manifest = build_manifest(units, excluded)
    (DATA_DIR / "corpus.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in corpus),
        encoding="utf-8",
        newline="\n",
    )
    (DATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (DATA_DIR / "LICENSE-ProGit.txt").write_text(
        "Pro Git, Second Edition, by Scott Chacon and Ben Straub (Apress, 2014)\n"
        f"{BOOK_URL}\n{UPSTREAM}/tree/{REVISION}\n\n"
        f"{license_notice}\n\n"
        "The lab corpus selects and normalizes sections from this snapshot.\n"
        "The corpus and excerpts reproduced in the benchmark and results retain this license.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {len(units)} source units ({manifest['total_characters']:,} characters).")


if __name__ == "__main__":
    main()
