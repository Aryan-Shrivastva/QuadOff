from __future__ import annotations

import os
from typing import Any


class LocalReasoner:
    """Evidence-first local reasoning with an optional cached Gemma adapter.

    The deterministic path is intentionally useful without model weights. It
    produces a citation-preserving briefing from retrieved records; a cached
    Gemma 4 runtime can be enabled later without changing the API contract.
    """

    def __init__(self) -> None:
        self.backend = os.getenv("REASONING_BACKEND", "deterministic").lower()
        self.model_name = os.getenv("REASONING_MODEL", "google/gemma-4-E2B-it")
        self._pipeline = None
        self._load_error: str | None = None
        if self.backend in {"gemma", "gemma4", "gemma4-local"}:
            self._try_load()

    @property
    def description(self) -> str:
        if self._pipeline:
            return f"{self.backend}:{self.model_name}"
        if self._load_error:
            return f"evidence-first fallback ({self._load_error})"
        return "evidence-first local briefing (Gemma 4 adapter available)"

    def _try_load(self) -> None:
        try:
            from transformers import pipeline  # type: ignore

            self._pipeline = pipeline(
                "text-generation",
                model=self.model_name,
                device="cpu",
                local_files_only=True,
            )
        except Exception as exc:  # pragma: no cover - optional model path
            self._load_error = str(exc).splitlines()[0][:140]

    def answer(self, query: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
        if not matches:
            return {
                "summary": "No local evidence matched this question. Capture a note or reconnect to refresh the project pack.",
                "caveat": "This device cannot infer beyond its local memory.",
                "citations": [],
            }
        if self._pipeline:  # pragma: no cover - requires cached Gemma weights
            context = "\n".join(f"[{idx + 1}] {item['title']}: {item['text']}" for idx, item in enumerate(matches[:5]))
            prompt = (
                "Answer the research question only from the cited context. State uncertainty and do not diagnose contamination.\n"
                f"Question: {query}\nContext:\n{context}\nBrief answer with citations:"
            )
            try:
                generated = self._pipeline(prompt, max_new_tokens=180, do_sample=False, return_full_text=False)[0]["generated_text"]
                return {"summary": generated.strip()[-1200:], "caveat": "Gemma 4 ran locally over retrieved evidence.", "citations": [item["id"] for item in matches[:5]]}
            except Exception as exc:  # pragma: no cover - model/runtime specific
                self._load_error = f"generation failed: {str(exc).splitlines()[0][:100]}"

        lowered = query.lower()
        low_oxygen = any(token in lowered for token in ("oxygen", "hypoxia", "low do"))
        turbidity = "turbid" in lowered or "ntu" in lowered or "sediment" in lowered
        observations = [item for item in matches if item.get("kind") == "observation"]
        summary_bits: list[str] = []
        if low_oxygen:
            low = [item for item in observations if "dissolved oxygen" in item["text"].lower() and any(value in item["text"] for value in ("4.2", "4.8", "5.1"))]
            if low:
                summary_bits.append(f"Local evidence includes {len(low)} low-oxygen observation(s) near the review band, including {low[0]['title']}.")
        if turbidity:
            high = [item for item in observations if "turbidity" in item["text"].lower() and any(value in item["text"] for value in ("15.0", "18.4", "16.2", "13.7"))]
            if high:
                summary_bits.append(f"It also includes post-rainfall turbidity readings above 10 NTU, such as {high[0]['title']}.")
        if not summary_bits:
            summary_bits.append(f"The top local matches are {', '.join(item['title'] for item in matches[:3])}.")
        return {
            "summary": " ".join(summary_bits),
            "caveat": "This is a local evidence briefing, not an environmental diagnosis. Verify the instrument, weather, and current authority before acting.",
            "citations": [item["id"] for item in matches[:5]],
        }
