from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "google/embeddinggemma-300m")
REASONING_MODEL = os.getenv("REASONING_MODEL", "google/gemma-4-E2B-it")


def check() -> int:
    print("FieldNote local model readiness")
    print(f"  HF cache: {os.getenv('HF_HOME', str(Path.home() / '.cache' / 'huggingface'))}")
    for package in ("torch", "transformers", "sentence_transformers"):
        spec = importlib.util.find_spec(package)
        print(f"  {package}: {'installed' if spec else 'missing'}")
    try:
        from huggingface_hub import try_to_load_from_cache  # type: ignore

        for model in (EMBEDDING_MODEL, REASONING_MODEL):
            marker = try_to_load_from_cache(model, "config.json")
            print(f"  {model}: {'cached' if marker else 'not cached'}")
    except Exception as exc:
        print(f"  cache inspection unavailable: {exc}")
    print("\nThe service intentionally falls back to deterministic local retrieval when a model is not cached.")
    return 0


def download(kind: str) -> int:
    if kind in {"embedding", "all"}:
        print(f"Downloading {EMBEDDING_MODEL} through SentenceTransformers...")
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        print(f"  embedding dimension: {model.get_sentence_embedding_dimension()}")
    if kind in {"reasoning", "all"}:
        print(f"Downloading {REASONING_MODEL} through Transformers...")
        from transformers import pipeline  # type: ignore

        pipeline("text-generation", model=REASONING_MODEL, device="cpu")
    print("Model setup complete. Set the model backend variables before restarting the service.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare optional local EmbeddingGemma and Gemma 4 runtimes")
    parser.add_argument("action", choices=("check", "download"))
    parser.add_argument("--kind", choices=("embedding", "reasoning", "all"), default="all")
    args = parser.parse_args()
    try:
        return check() if args.action == "check" else download(args.kind)
    except Exception as exc:
        print(f"Model setup failed: {exc}", file=sys.stderr)
        print("If the model is gated, accept its Google license and authenticate with Hugging Face, then retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
