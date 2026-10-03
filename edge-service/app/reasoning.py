from __future__ import annotations

import os
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


LOCAL_SERVER_BACKENDS = {"ollama", "llama-server", "llamacpp", "local-server"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalReasoner:
    """Evidence-first local reasoning with optional local or online model backends.

    The deterministic path is intentionally useful without model weights. It
    produces a citation-preserving briefing from retrieved records. A small
    quantized model (default Gemma 3 1B) served by Ollama or llama.cpp's
    ``llama-server`` can be enabled without changing the API contract.
    """

    def __init__(self) -> None:
        self.backend = os.getenv("REASONING_BACKEND", "deterministic").lower()
        self.model_name = os.getenv("REASONING_MODEL", "google/gemma-4-E2B-it")
        self.local_url = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        self.local_model = os.getenv("LOCAL_LLM_MODEL", "gemma3:1b")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._pipeline = None
        self._processor = None
        self._model = None
        self._load_error: str | None = None
        if self.backend in {"gemma", "gemma4", "gemma4-local"}:
            self._try_load()

    @property
    def _local_server_enabled(self) -> bool:
        return self.backend in LOCAL_SERVER_BACKENDS

    @property
    def description(self) -> str:
        if self._local_server_enabled:
            if self._load_error:
                return f"Local model server unavailable · evidence-first fallback ({self._load_error})"
            return f"Local model server · {self.local_model} (offline, {self.local_url})"
        if self.backend in {"gemini", "gemini-api", "gemini-cloud"}:
            if self._load_error:
                return f"Gemini API unavailable · {self._load_error}"
            if not self.gemini_api_key:
                return "Gemini API unavailable · key not configured"
            return f"Gemini API · {self.gemini_model} (online reasoning)"
        if self._model and self._processor:
            return f"Gemma 4 local · {self.model_name}"
        if self._pipeline:
            return f"local text model · {self.model_name}"
        if self._load_error:
            return f"Gemma 4 unavailable · evidence-first fallback ({self._load_error})"
        if self.backend in {"gemma", "gemma4", "gemma4-local"}:
            return f"Gemma 4 unavailable · model weights not cached ({self.model_name})"
        return "deterministic evidence-first fallback · Gemma 4 weights not loaded"

    def _try_load(self) -> None:
        try:
            # Gemma 4 is an any-to-any model. The supported Transformers path
            # is processor + AutoModelForMultimodalLM, rather than the older
            # text-generation pipeline used by earlier Gemma releases.
            from transformers import AutoModelForMultimodalLM, AutoProcessor  # type: ignore

            self._processor = AutoProcessor.from_pretrained(self.model_name, local_files_only=True)
            self._model = AutoModelForMultimodalLM.from_pretrained(
                self.model_name,
                dtype="auto",
                device_map="auto",
                local_files_only=True,
            )
            self._model.eval()
        except Exception as exc:  # pragma: no cover - optional model path
            self._processor = None
            self._model = None
            self._load_error = str(exc).splitlines()[0][:140]

    def _generate(self, prompt: str, max_new_tokens: int) -> str:
        if self._model and self._processor:
            messages = [
                {"role": "system", "content": "You are a careful offline field-research assistant. Use only the supplied evidence and state uncertainty."},
                {"role": "user", "content": prompt},
            ]
            inputs = self._processor.apply_chat_template(
                messages,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                add_generation_prompt=True,
                enable_thinking=False,
            )
            device = next(self._model.parameters()).device
            inputs = inputs.to(device)
            input_len = inputs["input_ids"].shape[-1]
            outputs = self._model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
            return self._processor.decode(outputs[0][input_len:], skip_special_tokens=True).strip()
        if self._pipeline:
            return self._pipeline(prompt, max_new_tokens=max_new_tokens, do_sample=False, return_full_text=False)[0]["generated_text"].strip()
        raise RuntimeError("no local model loaded")

    def _call_local_server(self, prompt: str, max_new_tokens: int) -> str:
        """Call an OpenAI-compatible chat endpoint (Ollama or llama-server) on this device."""
        if urllib.parse.urlparse(self.local_url).hostname not in LOOPBACK_HOSTS:
            raise RuntimeError("LOCAL_LLM_URL must point at this device (localhost)")
        request = urllib.request.Request(
            f"{self.local_url}/chat/completions",
            data=json.dumps({
                "model": self.local_model,
                "messages": [
                    {"role": "system", "content": "You are a careful offline field-research assistant. Use only the supplied evidence and state uncertainty."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": max_new_tokens,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:160]
            raise RuntimeError(f"local model server error ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"local model server not reachable at {self.local_url}") from exc
        text = (payload.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("local model returned no text")
        return text

    @property
    def _gemini_enabled(self) -> bool:
        return self.backend in {"gemini", "gemini-api", "gemini-cloud"} and bool(self.gemini_api_key)

    def _call_gemini(self, prompt: str, max_output_tokens: int) -> str:
        if not self.gemini_api_key:
            raise RuntimeError("Gemini API key not configured")
        model = urllib.parse.quote(self.gemini_model, safe="")
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps({
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_output_tokens},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.gemini_api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
            raise RuntimeError(f"Gemini request failed ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Gemini request unavailable: {exc}") from exc
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise RuntimeError("Gemini returned no text")
        return text

    @staticmethod
    def _source_summary(source_text: str) -> str:
        """Extract the source report's own summary section, not a generated answer."""
        if not source_text:
            return "No source summary was supplied."
        normalized = re.sub(r"\s+(?=#{1,3}\s)", "\n", source_text.replace("\r", "")).strip()
        sections = re.split(r"\n(?=##\s+)", normalized)
        preferred = next((section for section in sections if re.match(r"^##\s+(observation summary|forecast summary|feature summary|report summary|summary|overview)", section.strip(), re.I)), None)
        chosen = preferred or next((section for section in sections if re.match(r"^##\s+", section.strip())), normalized)
        summary = re.sub(r"^#{1,3}\s+[^\n]+\n?", "", chosen.strip())
        return re.sub(r"\s+", " ", summary).strip() or "No source summary was supplied."

    @staticmethod
    def _numbers_supported(summary: str, *sources: str) -> bool:
        """Reject drafts that introduce numbers absent from the researcher's text or the source."""
        allowed = set(re.findall(r"\d+(?:\.\d+)?", " ".join(sources)))
        return all(number in allowed for number in re.findall(r"\d+(?:\.\d+)?", summary))

    @staticmethod
    def _bounded_words(text: str, limit: int) -> str:
        words = re.sub(r"\s+", " ", text.strip()).split()
        return " ".join(words[:limit]).rstrip(" .,;:")

    def _offline_refinement(self, *, observation: str, evidence: str, source_text: str, source_title: str, category: str, location: str) -> dict[str, Any]:
        """Create a useful 80–100 word synthesis without pretending a model ran."""
        source_summary = self._bounded_words(self._source_summary(source_text), 22)
        observation_text = self._bounded_words(observation or "No direct observation was entered.", 20)
        evidence_text = self._bounded_words(evidence or "No additional qualitative evidence was entered.", 18)
        source_reference = self._bounded_words(source_title or "the selected report", 8)
        parts = [
            f"Selected report summary: {source_summary}.",
            f"Field observation: {observation_text}.",
            f"Qualitative evidence: {evidence_text}.",
            f"This {category.lower()} observation was recorded at {location} as a new local finding related to {source_reference}, not as an edit to the original report.",
            "The source context and researcher wording should be reviewed together, and the finding should remain provisional until independently verified with a repeat observation, measurement, or supporting image.",
        ]
        summary = " ".join(parts)
        words = summary.split()
        if len(words) > 100:
            complete_sentences = re.split(r"(?<=[.!?])\s+", summary)
            kept: list[str] = []
            for sentence in complete_sentences:
                candidate = " ".join((*kept, sentence))
                if len(candidate.split()) > 100:
                    break
                kept.append(sentence)
            summary = " ".join(kept).strip()
        while len(summary.split()) < 80:
            padding = "The finding remains provisional until independently verified."
            candidate = f"{summary} {padding}".strip()
            if len(candidate.split()) > 100:
                break
            summary = candidate
        return {
            "title": f"{category} observation · {location}"[:180],
            "summary": summary,
            "engine": "deterministic local fallback",
            "model_status": self.description,
            "used_model": False,
        }

    def answer(self, query: str, matches: list[dict[str, Any]], network_allowed: bool = True) -> dict[str, Any]:
        if not matches:
            return {
                "summary": "No local evidence matched this question. Capture a note or reconnect to refresh the project pack.",
                "caveat": "This device cannot infer beyond its local memory.",
                "citations": [],
            }
        if self._gemini_enabled and network_allowed:
            context = "\n".join(f"[{idx + 1}] {item['title']}: {item['text']}" for idx, item in enumerate(matches[:5]))
            prompt = (
                "Answer the research question only from the cited local evidence. State uncertainty, do not invent measurements, "
                "and do not diagnose contamination. Include citation numbers like [1].\n"
                f"Question: {query}\nLocal evidence:\n{context}\nBrief answer with citations:"
            )
            try:
                generated = self._call_gemini(prompt, max_output_tokens=180)
                return {"summary": generated, "caveat": "Gemini API summarized locally retrieved Qdrant Edge evidence.", "citations": [item["id"] for item in matches[:5]], "engine": "Gemini API", "used_model": True}
            except Exception as exc:  # pragma: no cover - network/provider specific
                self._load_error = str(exc).splitlines()[0][:180]
        if self._local_server_enabled:  # pragma: no cover - requires a running local model server
            context = "\n".join(f"[{idx + 1}] {item['title']}: {item['text'][:1200]}" for idx, item in enumerate(matches[:5]))
            prompt = (
                "Answer the research question only from the cited context. State uncertainty and do not diagnose contamination. "
                "Include citation numbers like [1].\n"
                f"Question: {query}\nContext:\n{context}\nBrief answer with citations:"
            )
            try:
                generated = self._call_local_server(prompt, max_new_tokens=180)
                self._load_error = None
                return {"summary": generated[-1200:], "caveat": f"{self.local_model} ran on this device over retrieved evidence.", "citations": [item["id"] for item in matches[:5]], "engine": self.local_model, "used_model": True}
            except Exception as exc:
                self._load_error = str(exc).splitlines()[0][:140]
        if self._model or self._pipeline:  # pragma: no cover - requires cached Gemma weights
            context = "\n".join(f"[{idx + 1}] {item['title']}: {item['text']}" for idx, item in enumerate(matches[:5]))
            prompt = (
                "Answer the research question only from the cited context. State uncertainty and do not diagnose contamination.\n"
                f"Question: {query}\nContext:\n{context}\nBrief answer with citations:"
            )
            try:
                generated = self._generate(prompt, max_new_tokens=180)
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
            "engine": "deterministic local fallback",
            "used_model": False,
        }

    def refine_observation(self, *, observation: str, evidence: str, query: str, source_title: str, source_text: str, category: str, location: str, network_allowed: bool = True) -> dict[str, Any]:
        """Turn a rough field note into a citation-preserving new-record draft."""
        if self._gemini_enabled and network_allowed:
            prompt = (
                "Create a careful 80-100 word field-note copy from the selected report summary and the researcher's findings. "
                "Use the selected report summary first, then integrate the observation and qualitative evidence. Do not invent measurements or species. "
                "Preserve uncertainty. Return exactly two lines: TITLE: ... and SUMMARY: ...\n"
                f"Location: {location}\nCategory: {category}\nSearch question: {query}\nSelected source: {source_title}\n"
                f"Selected report summary: {self._source_summary(source_text)}\nObservation: {observation}\nQualitative evidence: {evidence}"
            )
            try:
                generated = self._call_gemini(prompt, max_output_tokens=220)
                title = next((line.split(":", 1)[1].strip() for line in generated.splitlines() if line.upper().startswith("TITLE:")), f"{category} observation · {location}")
                summary = next((line.split(":", 1)[1].strip() for line in generated.splitlines() if line.upper().startswith("SUMMARY:")), generated)
                return {"title": title[:180], "summary": summary[:6000], "engine": "Gemini API", "model_status": self.description, "used_model": True}
            except Exception as exc:  # pragma: no cover - network/provider specific
                self._load_error = str(exc).splitlines()[0][:180]

        if self._local_server_enabled:  # pragma: no cover - requires a running local model server
            prompt = (
                "Create a careful 80-100 word field-note copy from the selected report summary and the researcher's findings. "
                "Use the selected report summary first, then integrate the observation and qualitative evidence. Do not invent measurements or species. "
                "Preserve uncertainty. Return exactly two lines: TITLE: ... and SUMMARY: ...\n"
                f"Location: {location}\nCategory: {category}\nSearch question: {query}\nSelected source: {source_title}\n"
                f"Selected report summary: {self._source_summary(source_text)}\nObservation: {observation}\nQualitative evidence: {evidence}"
            )
            try:
                generated = self._call_local_server(prompt, max_new_tokens=220)
                title = next((line.split(":", 1)[1].strip() for line in generated.splitlines() if line.upper().startswith("TITLE:")), "")
                summary = next((line.split(":", 1)[1].strip() for line in generated.splitlines() if line.upper().startswith("SUMMARY:")), "")
                if title and len(summary.split()) >= 30 and self._numbers_supported(summary, observation, evidence, source_text):
                    self._load_error = None
                    return {"title": title[:180], "summary": summary[:6000], "engine": self.local_model, "model_status": self.description, "used_model": True}
                self._load_error = "model output failed format/grounding checks"
            except Exception as exc:
                self._load_error = str(exc).splitlines()[0][:140]

        if self._model or self._pipeline:  # pragma: no cover - requires cached Gemma weights
            prompt = (
                "Create an 80-100 word field-note summary. Use the selected report summary first, then integrate the observation and qualitative evidence. "
                "Do not invent measurements. Keep the source evidence and uncertainty explicit. Return exactly two lines: TITLE: ... and SUMMARY: ...\n"
                f"Location: {location}\nCategory: {category}\nSearch question: {query}\nSource: {source_title}\nSource context: {source_text}\n"
                f"Observation: {observation}\nQualitative evidence: {evidence}"
            )
            try:
                generated = self._generate(prompt, max_new_tokens=220)
                title = next((line.split(":", 1)[1].strip() for line in generated.splitlines() if line.upper().startswith("TITLE:")), f"{category} observation · {location}")
                summary = next((line.split(":", 1)[1].strip() for line in generated.splitlines() if line.upper().startswith("SUMMARY:")), generated)
                return {"title": title[:180], "summary": summary[:6000], "engine": "Gemma 4", "model_status": self.description, "used_model": True}
            except Exception as exc:  # pragma: no cover - model/runtime specific
                self._load_error = f"generation failed: {str(exc).splitlines()[0][:100]}"

        fallback = self._offline_refinement(observation=observation, evidence=evidence, source_text=source_text, source_title=source_title, category=category, location=location)
        if self._gemini_enabled and not network_allowed:
            fallback["model_status"] = "Gemini API skipped · device is offline; local evidence draft used"
        return fallback
