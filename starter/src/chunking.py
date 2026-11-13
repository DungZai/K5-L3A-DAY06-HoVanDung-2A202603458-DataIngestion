"""Chunk text without losing its offsets into the normalized source unit."""

import re
from uuid import NAMESPACE_URL, uuid5

from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, start: int, end: int) -> Chunk:
    text = page.text[start:end]
    start += len(text) - len(text.lstrip())
    end -= len(text) - len(text.rstrip())
    chunk_id = str(uuid5(NAMESPACE_URL, f"{page.source}#{page.page}:{start}:{end}"))
    return Chunk(
        chunk_id, page.document_id, page.source, page.page, page.text[start:end],
        {**page.metadata, "start_char": start, "end_char": end},
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError("Chunk size must be positive and greater than overlap.")
    chunks = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        if page.text[start:end].strip():
            chunks.append(_chunk(page, start, end))
        if end == len(page.text):
            break
    return chunks


def _paragraph_spans(text: str):
    start = 0
    for separator in re.finditer(r"\n\n+|\n(?=#{1,6} )", text):
        if start < separator.start():
            yield start, separator.start()
        start = separator.end()
    if start < len(text):
        yield start, len(text)


def _split_long_paragraph(text: str, start: int, end: int, size: int):
    while end - start > size:
        window = text[start:start + size]
        boundaries = list(re.finditer(r"[.!?](?=\s)|\n", window))
        whitespace = list(re.finditer(r"\s", window))
        choices = boundaries or whitespace
        stop = start + (choices[-1].end() if choices else size)
        if text[start:stop].strip():
            yield start, stop
        start = stop
        while start < end and text[start].isspace():
            start += 1
    if start < end:
        yield start, end


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    if max_size < 1:
        raise ValueError("Chunk size must be positive.")
    chunks = []
    start = end = 0
    for left, right in _paragraph_spans(page.text):
        begins_heading = bool(re.match(r"#{1,6} ", page.text[left:right]))
        for block_start, block_end in _split_long_paragraph(
            page.text, left, right, max_size
        ):
            if end > start and (begins_heading or block_end - start > max_size):
                chunks.append(_chunk(page, start, end))
                start = end = block_start
            if start == end:
                start = block_start
            end = block_end
            begins_heading = False
    if end > start:
        chunks.append(_chunk(page, start, end))
    return chunks
