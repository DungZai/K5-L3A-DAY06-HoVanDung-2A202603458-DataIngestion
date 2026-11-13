"""CPU inference for the pinned quantized BGE model."""

import argparse
from hashlib import file_digest
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


MODEL_REPO = "Qdrant/bge-small-en-v1.5-onnx-Q"
MODEL_REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"
MODEL_FILES = {
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "model_optimized.onnx": "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431",
}
DEFAULT_CACHE = Path(".lab-cache/models")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _verified(path: Path, sha256: str) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest() == sha256


def download_model(cache_dir: Path) -> Path:
    """Fetch and verify the immutable snapshot without using an API key."""
    folder = cache_dir / MODEL_REVISION
    folder.mkdir(parents=True, exist_ok=True)
    for name, sha256 in MODEL_FILES.items():
        target = folder / name
        if _verified(target, sha256):
            continue
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
        with NamedTemporaryFile(dir=folder, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            if not _verified(temporary, sha256):
                raise ValueError(f"Unexpected SHA-256 for {name}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return folder


class LocalEmbedder:
    model_name = "BAAI/bge-small-en-v1.5"
    model_repository = MODEL_REPO
    model_revision = MODEL_REVISION
    provider = "ONNX Runtime CPU"
    dimensions = 384
    max_tokens = 512
    query_prefix = QUERY_PREFIX
    batch_size = 16

    def __init__(self, cache_dir: Path = DEFAULT_CACHE) -> None:
        folder = cache_dir / self.model_revision
        for name, sha256 in MODEL_FILES.items():
            if not _verified(folder / name, sha256):
                raise ValueError(
                    f"Missing or invalid model file {folder / name}. "
                    "Run python -m starter.src.embeddings --cache-dir "
                    f'"{cache_dir}" first.'
                )

        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        pad_token = "[PAD]"
        self.pad_id = self.tokenizer.token_to_id(pad_token)
        if self.pad_id is None:
            raise ValueError(f"Model tokenizer has no {pad_token} token")

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(folder / "model_optimized.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_names = {node.name for node in self.session.get_inputs()}

    def token_counts(self, texts: list[str]) -> list[int]:
        """Count model tokens with special tokens, excluding padding."""
        return [len(item.ids) for item in self.tokenizer.encode_batch(texts)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size]))
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self._embed_batch([self.query_prefix + question])[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        encoded = self.tokenizer.encode_batch(texts)
        longest = max(len(item.ids) for item in encoded)
        if longest > self.max_tokens:
            raise ValueError(f"Model received {longest} tokens, limit is {self.max_tokens}")

        def padded(values: list[int], pad: int) -> list[int]:
            return values + [pad] * (longest - len(values))

        batch = {
            "input_ids": [padded(item.ids, self.pad_id) for item in encoded],
            "attention_mask": [padded(item.attention_mask, 0) for item in encoded],
            "token_type_ids": [padded(item.type_ids, 0) for item in encoded],
        }
        inputs = {
            name: np.asarray(batch[name], dtype=np.int64) for name in self.input_names
        }
        hidden = self.session.run(["last_hidden_state"], inputs)[0]
        cls = hidden[:, 0, :]
        norms = np.linalg.norm(cls, axis=1, keepdims=True)
        if (
            cls.shape != (len(texts), self.dimensions)
            or not np.isfinite(cls).all()
            or (norms == 0).any()
        ):
            raise ValueError("Embedding model returned invalid vectors")
        return (cls / norms).tolist()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the pinned BGE model")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    folder = download_model(args.cache_dir)
    print(f"Verified {MODEL_REPO}@{MODEL_REVISION} in {folder}")


if __name__ == "__main__":
    main()
