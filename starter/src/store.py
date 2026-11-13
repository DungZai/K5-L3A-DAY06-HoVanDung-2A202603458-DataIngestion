"""Persistent local Qdrant collections and exact cosine search."""

from importlib.metadata import version
from math import isfinite
from pathlib import Path
import re
from typing import Any, Self
from uuid import NAMESPACE_URL, uuid4, uuid5

from qdrant_client import QdrantClient, models

from .models import Chunk


class QdrantStore:
    version = version("qdrant-client")
    metric = "cosine"
    search_mode = "exact"

    def __init__(self, path: Path, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("Vector dimensions must be positive")
        self.dimensions = dimensions
        self.client = QdrantClient(path=str(path))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.client.close()

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.dimensions:
            raise ValueError(f"Expected {self.dimensions} vector dimensions, got {len(vector)}")
        if not all(isfinite(value) for value in vector) or not any(vector):
            raise ValueError("Cosine search needs a finite nonzero vector")

    @staticmethod
    def _alias(strategy: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", strategy):
            raise ValueError(f"Invalid strategy name {strategy!r}")
        return f"day06_{strategy}"

    def replace(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Publish a complete collection once all its points have been written."""
        alias = self._alias(strategy)
        if len(chunks) != len(vectors):
            raise ValueError("Expected one vector for each chunk")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError(f"Duplicate chunk IDs for {strategy}")

        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._validate_vector(vector)
            points.append(
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"day06/{strategy}/{chunk.chunk_id}")),
                    vector=vector,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "source": chunk.source,
                        "page": chunk.page,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                    },
                )
            )

        collection = f"{alias}.{uuid4().hex}"
        self.client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=self.dimensions, distance=models.Distance.COSINE),
        )
        try:
            if points:
                self.client.upsert(collection_name=collection, points=points, wait=True)
        except Exception:
            self.client.delete_collection(collection)
            raise

        operations = []
        if self.client.collection_exists(alias):
            operations.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)
            )
        )
        self.client.update_collection_aliases(operations)
        # Remove superseded snapshots and unpublished snapshots left by a prior interruption.
        for item in self.client.get_collections().collections:
            if item.name.startswith(f"{alias}.") and item.name != collection:
                self.client.delete_collection(item.name)

    def count(self, strategy: str) -> int:
        return self.client.count(collection_name=self._alias(strategy), exact=True).count

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_vector(query_vector)
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query_filter = None
        if filters:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(key=f"metadata.{key}", match=models.MatchValue(value=value))
                    for key, value in filters.items()
                ]
            )
        response = self.client.query_points(
            collection_name=self._alias(strategy),
            query=query_vector,
            query_filter=query_filter,
            search_params=models.SearchParams(exact=True),
            limit=top_k,
            with_payload=True,
        )
        return [dict(hit.payload or {}, score=hit.score) for hit in response.points]
