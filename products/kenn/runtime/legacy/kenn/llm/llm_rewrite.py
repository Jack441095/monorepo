"""Optional OpenAI-compatible LLM rewrite for chat answers (retrieval-first).

Improvements in this version:
1. httpx replaces urllib — connection pooling, proper timeouts, robust SSE parsing
2. Dynamic system prompt per answer mode + route (tone/shape adapts to the task)
3. Feeds raw chunk context for synthesis (not just the pre-built template)
4. Tracks and exposes token usage metadata in stream/payload
5. Multi-model routing by task: route, rewrite, paraphrase, followups
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

import httpx

ROOT = Path(__file__).resolve().parent.parent
# ROOT is studio/kenn/kenn (the package dir) -- the real repo root (where the
# actual AUDIO_TOO_LLM_* .env lives) is three levels up, not one. The old
# `ROOT.parent` (studio/kenn) meant load_env() below only ever checked
# studio/kenn/.env and studio/kenn/kenn/.env, neither of which exists, so
# config() silently fell back to every default (openai/gpt-4o-mini, disabled)
# regardless of what the repo-root .env actually said -- found 2026-08-10
# while verifying the LLM-enhanced answer path actually used the configured
# local Ollama model.
PROJECT_ROOT = ROOT.parent.parent.parent


# ---------------------------------------------------------------------------
# Base system prompt template — mode/route instructions injected dynamically
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are KENN, senior audio engineer assistant and trusted studio partner for Audio_Too.

Specialty: {route_description}

Tone: Conversational and opinionated. Use UK spelling and direct verbs ("I'd", "you'll want to"). Give clear verdicts when the evidence supports one. Never say "as an AI". State a concise evidence boundary when it materially changes the advice; do not claim to have heard or measured audio that was not provided.

Answer structure (strictly required):
  Short answer: (one punchy paragraph — verdict first, then reason)
  Try this: (numbered steps 1. 2. 3. actionable in the DAW)
  Why it matters: (one paragraph of the underlying engineering principle)
  {sources_instruction}
  You could also ask: (- up to 3 short follow-up questions)

Mode-specific guidance:
{mode_instructions}

Rules:
- Answer ONLY using the provided context. Do not invent plugins, settings, prices, or policies.
- If context is insufficient, name the specific gap (e.g. "We need a note on parallel compression").
- Keep every step actionable in Ableton Live or the relevant workflow.
- Address only the current question. Ignore irrelevant history.
- Say plainly whether the question has an objective/technical answer (clipping, phase, LUFS, a
  measurable fault) or is a subjective/creative call (brightness, width, "should it sound bigger").
  Do not present a creative preference as if it were a technical rule, and do not hedge a genuine
  technical fact as if it were just an opinion.
- Never claim to have heard, measured, or analysed the user's actual audio unless real measurements
  were provided in the source excerpts or conversation context above. If none were provided, say so
  and reason from the description given instead of pretending to have listened.
{skill_level_instruction}
"""

# ---------------------------------------------------------------------------
# Route descriptions and mode instructions for the dynamic system prompt
# ---------------------------------------------------------------------------

ROUTE_DESCRIPTIONS = {
    "ableton": "Ableton Live workflows — devices, routing, session view, arrangement, shortcuts, MIDI, audio clips, warping, automation, freezing, CPU management.",
    "production": "Music production, mixing, mastering, recording, arrangement, sound design, loudness standards, translation, monitoring, and client delivery.",
    "mix_review": "Mix review follow-up analysis — interpreting objective metrics (peak, RMS, crest, spectrum), action plans, revision checklists, Ableton repair chains.",
    "mix_review_followup": "Mix review follow-up analysis — interpreting objective metrics (peak, RMS, crest, spectrum), action plans, revision checklists, Ableton repair chains.",
    "game_audio": "Game audio implementation — Wwise, middleware, events, SoundBanks, real-time mixing, platform limits, memory and voice budgeting.",
    "conversation": "General conversation about audio production, Ableton, and mixing.",
    "out_of_scope": "Topics outside audio engineering and music production.",
    "unknown": "General audio engineering and music production.",
}

MODE_INSTRUCTIONS = {
    "ableton_steps": "Focus on exact Ableton device names, routing options, and Live-specific UI paths. Output contract: how-to (direct instructions, numbered steps, no explanation preamble). Include a 'Live safety:' boundary reminding the user to duplicate the track or save before making changes.",
    "client_delivery": "Focus on file formats, stem organisation, labelling versions, revision scope, and communication. Output contract: business status (pricing, revision limits, scope boundary). Include a 'Scope boundary:' warning against vague briefs and missing deliverables.",
    "deep_explanation": "Explain the concept clearly, then ground it in a practical example. Include a 'Understanding check:' prompt to apply the idea in the session.",
    "dialogue_cleanup": "Focus on podcast/dialogue noise reduction, breath control, room tone preservation, and avoiding over-processing. Include a 'Cleanup boundary:' on preserving intelligibility.",
    "game_audio_implementation": "Focus on middleware/engine context, event triggers, state transitions, and platform limits. Include a 'Runtime tradeoff:' on balancing DAW polish against engine constraints.",
    "mastering_safety": "Focus on loudness targets, true peak safety, level-matched comparison, and translation checks. Include a 'Mastering boundary:' on not chasing loudness until balance is right.",
    "mix_diagnosis": "Treat this like a troubleshooting engineer, not a preset generator. Identify the audible symptom, then name 2-3 plausible causes ranked by likelihood, impact, ease of testing, and how reversible the fix is — do not commit to a single cause on the first guess. For a tonal, harshness, thinness, or performance symptom, consider recording-stage causes (mic choice, mic distance, off-axis angle, proximity effect, room, performance) alongside mix-stage causes (EQ, compression, saturation, arrangement/masking, phase) — do not jump straight to a mix-stage fix when the source could equally be at the recording stage. If the question doesn't give enough detail to tell the hypotheses apart, make 'Try this:' the cheap diagnostic tests that distinguish between them (solo/mute, bypass, mono check, level-matched A/B) rather than a fix, and close with the single most useful question to ask before recommending a specific move. Only prescribe a fix once a cause is reasonably narrowed. Output contract: diagnosis (Symptom → Likely causes, ranked → Tests → Fix once confirmed). Include a 'Diagnosis boundary:' stating whether this is an objective/technical issue or a subjective/creative call.",
    "mix_review_followup": "Focus on the uploaded-track metrics and action plan. Output contract: mix review (interpreting objective metrics, action plans, checklist). Include a 'Revision check:' on making one focused change per revision cycle.",
    "quick_fix": "Keep it short and practical — one or two small moves the user can try immediately. Output contract: quick answer (very concise, single-paragraph response, quick fix). Include a 'Check:' to compare before/after at matched loudness.",
    "voice": "This answer will be read aloud by TTS. Output contract: voice (natural spoken English under 80 words — no markdown, no bullet symbols, no section headers). Give the verdict in two or three sentences, then one or two concrete steps Jack can take immediately. No sources section. The TTS engine understands one pause tag, <break time=\"500ms\"/> — insert it after a warm opening transition (e.g. \"Got it, Jack.\") and between distinct sentences where a real speaker would take a breath, so the delivery doesn't run on at one flat pace. Use it sparingly, at most one or two per answer — it counts toward the word limit, so don't let it crowd out the actual content.",
    "action_preview": "Explain the action that is about to be taken and ask for the user's explicit confirmation. Output contract: action preview (explaining what action is planned, prepare confirmation gate). Include a 'Confirmation gate:' detailing what will be executed once approved.",
    "action_receipt": "Confirm that the action was successfully executed. Output contract: action receipt (confirmed receipt details of a run command). Include an 'Action receipt:' summarizing the changes made.",
}


@dataclass
class LLMUsage:
    """Track token usage and latency for a single LLM call."""
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    task: str = "rewrite"

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "task": self.task,
        }


_global_usage: list[LLMUsage] = []  # accumulate across requests for monitoring


def get_accumulated_usage() -> list[dict]:
    return [u.to_dict() for u in _global_usage]


def _add_usage(usage: LLMUsage) -> None:
    _global_usage.append(usage)
    # Keep only last 1000 entries to bound memory
    if len(_global_usage) > 1000:
        _global_usage[:200] = []


def load_env() -> None:
    for path in (PROJECT_ROOT / ".env", ROOT / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def truthy(name: str, default: str = "0") -> bool:
    load_env()
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def config(task: str = "rewrite") -> dict:
    """Return config for a specific task, allowing per-task model routing.

    Task can be: "rewrite", "route", "paraphrase", "followups".
    Falls back to the base model config if no per-task override exists.
    """
    load_env()
    suffix = f"_{task.upper()}" if task != "rewrite" else ""
    provider = os.environ.get(f"AUDIO_TOO_LLM_PROVIDER{suffix}", "").strip().lower()
    if not provider:
        provider = os.environ.get("AUDIO_TOO_LLM_PROVIDER", "openai").strip().lower()
    base = os.environ.get(f"AUDIO_TOO_LLM_BASE_URL{suffix}", "").strip()
    if not base:
        base = os.environ.get("AUDIO_TOO_LLM_BASE_URL", "").strip()
    if not base:
        base = "http://127.0.0.1:11434/v1" if provider == "ollama" else "https://api.openai.com/v1"
    model = os.environ.get(f"AUDIO_TOO_LLM_MODEL_{task.upper()}", "").strip()
    if not model:
        model = os.environ.get("AUDIO_TOO_LLM_MODEL", "gpt-4o-mini").strip()
    return {
        "enabled": truthy("AUDIO_TOO_LLM_ENABLED"),
        "api_key": os.environ.get(f"AUDIO_TOO_LLM_API_KEY{suffix}", "").strip()
                   or os.environ.get("AUDIO_TOO_LLM_API_KEY", "").strip(),
        "base_url": base.rstrip("/"),
        "model": model,
        "provider": provider,
        # Found live 2026-08-10 dogfooding KENN as an actual chat assistant:
        # with the previous 90s default, a slow/oversized local Ollama
        # call (measured 17-60+s for a realistic retrieval-context prompt
        # on this hardware, even on the smaller of the two available
        # models) meant a single question could make the user wait up to
        # a minute and a half before enhance()'s own broad except-clause
        # gracefully fell back to the template answer -- "graceful" only
        # in the sense that it didn't crash, not in the sense that it was
        # fast. A real-time chat assistant needs to fail fast into that
        # already-good template fallback, not make the user wonder if it
        # hung. 90 was also a fabricated-sounding round number with no
        # comment explaining why -- 20s is still generous for a local
        # model but caps the worst case at something a user will actually
        # wait through.
        "timeout": int(os.environ.get("AUDIO_TOO_LLM_TIMEOUT", "20") or "20"),
    }


def is_enabled(task: str = "rewrite") -> bool:
    cfg = config(task)
    if not cfg["enabled"]:
        return False
    if cfg["provider"] == "ollama":
        return True
    return bool(cfg["api_key"])


# ---------------------------------------------------------------------------
# httpx client (connection-pooled, shared across calls)
# ---------------------------------------------------------------------------

_client_instance: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client_instance
    if _client_instance is None:
        try:
            import certifi
            verify = certifi.where()
        except ImportError:
            verify = True
        _client_instance = httpx.Client(
            verify=verify,
            timeout=httpx.Timeout(90.0, connect=15.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
        )
    _ensure_ollama_keep_alive()
    return _client_instance


# ---------------------------------------------------------------------------
# Ollama keep-alive pinger — Ollama's OpenAI-compatible endpoint ignores a
# "keep_alive" field in the request body (verified: it always falls back to
# the server default, ~5 min), so a studio session with gaps between
# questions longer than that pays a full cold model reload (~1-3s) on the
# next answer. Only the native /api/generate endpoint honours keep_alive.
# This background thread re-pings it periodically, well under the 5 min
# default TTL, so the model stays resident in GPU memory for the life of
# the process. Additive only — never touches the answer-generation path.
# ---------------------------------------------------------------------------

_keep_alive_started = False
_keep_alive_lock = threading.Lock()
KEEP_ALIVE_DURATION = os.environ.get("KENN_OLLAMA_KEEP_ALIVE", "30m")
KEEP_ALIVE_INTERVAL_S = 240  # under Ollama's 5 min default unload timeout


def _native_ollama_base(base_url: str) -> str:
    return base_url[:-3] if base_url.endswith("/v1") else base_url


def _ping_ollama_keep_alive(cfg: dict) -> None:
    try:
        httpx.post(
            f"{_native_ollama_base(cfg['base_url'])}/api/generate",
            json={"model": cfg["model"], "prompt": "", "keep_alive": KEEP_ALIVE_DURATION},
            timeout=10.0,
        )
    except Exception:
        pass  # best-effort — a missed ping just means the next real call reloads normally


def _keep_alive_loop() -> None:
    while True:
        cfg = config()
        if cfg["provider"] == "ollama" and cfg["enabled"]:
            _ping_ollama_keep_alive(cfg)
        time.sleep(KEEP_ALIVE_INTERVAL_S)


def _ensure_ollama_keep_alive() -> None:
    global _keep_alive_started
    if _keep_alive_started:
        return
    with _keep_alive_lock:
        if _keep_alive_started:
            return
        cfg = config()
        if cfg["provider"] == "ollama" and cfg["enabled"] and KEEP_ALIVE_INTERVAL_S > 0:
            threading.Thread(target=_keep_alive_loop, daemon=True).start()
        _keep_alive_started = True


def _build_headers(cfg: dict) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    return headers


# Voice answers are instructed (see MODE_INSTRUCTIONS["voice"]) to stay under
# 80 words with no sources section — this caps worst-case generation time to
# match that contract instead of trusting the model to stop on its own.
MAX_TOKENS_BY_MODE = {"voice": 220}
DEFAULT_MAX_TOKENS = 1200


def _build_payload(
    cfg: dict, messages: list[dict], *, stream: bool = False, answer_mode: str = ""
) -> dict:
    return {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.35,
        "max_tokens": MAX_TOKENS_BY_MODE.get(answer_mode, DEFAULT_MAX_TOKENS),
        "stream": stream,
    }


# ---------------------------------------------------------------------------
# Dynamic system prompt builder
# ---------------------------------------------------------------------------

def asks_for_sources(query: str) -> bool:
    if not query:
        return False
    terms = {"source", "sources", "reference", "references", "citation", "citations", "link", "links", "where is this from", "prove", "origin"}
    query_lower = query.lower()
    return any(term in query_lower for term in terms)


SKILL_LEVEL_INSTRUCTIONS = {
    "beginner": (
        "The user's session context indicates they are new to this. Use plain language, avoid "
        "assuming familiarity with jargon or plugin names, and prefer fewer concepts explained "
        "clearly over an exhaustive technical list."
    ),
    "advanced": (
        "The user's session context indicates an experienced engineer. Skip basic definitions, "
        "use precise technical language, and where relevant note tradeoffs or alternative "
        "approaches rather than a single prescribed path."
    ),
}


def build_system_prompt(
    answer_mode: str = "",
    route: str = "unknown",
    query: str = "",
    skill_level: str = "",
) -> str:
    """Build the system prompt with route description and mode instructions injected."""
    route_desc = ROUTE_DESCRIPTIONS.get(route, ROUTE_DESCRIPTIONS["unknown"])
    mode_instr = MODE_INSTRUCTIONS.get(answer_mode, MODE_INSTRUCTIONS["quick_fix"])
    skill_instr = SKILL_LEVEL_INSTRUCTIONS.get(skill_level, "")

    if asks_for_sources(query):
        sources_instruction = (
            "Sources: (List sources ONLY as markdown links. Format: - [Clean Title](/api/ableton/note?name=filename.md). Do NOT display raw file names or paths in the link label, use clean human-readable names. Do not include raw .md text in the labels.)"
        )
    else:
        sources_instruction = (
            "Do NOT include a 'Sources:' section under any circumstances. If the user didn't ask for sources, do not mention them."
        )

    return SYSTEM_PROMPT_TEMPLATE.format(
        route_description=route_desc,
        mode_instructions=mode_instr,
        sources_instruction=sources_instruction,
        skill_level_instruction=skill_instr,
    )


# ---------------------------------------------------------------------------
# Raw context block builder (feeds full source excerpts for LLM synthesis)
# ---------------------------------------------------------------------------

def build_raw_context_block(
    results: list[tuple[float, dict]],
    source_label: callable,
    *,
    max_chars: int = 3500,
) -> str:
    """Build a context block from the raw retrieved chunks."""
    parts: list[str] = []
    char_count = 0
    for score, chunk in results[:4]:
        if score < 4.0:
            continue
        label = source_label(chunk)
        text = str(chunk.get("text", ""))[:1200]
        block = f"[Source: {label} | relevance {score:.1f}]\n{text}"
        if char_count + len(block) > max_chars:
            remaining = max_chars - char_count
            if remaining > 200:
                parts.append(block[:remaining])
            break
        parts.append(block)
        char_count += len(block)
    return "\n\n".join(parts) if parts else "(no source excerpts provided)"


# ---------------------------------------------------------------------------
# Core API calls (httpx-based)
# ---------------------------------------------------------------------------

# ── LLM answer cache ─────────────────────────────────────────────────────────
# Identical prompts (same model + same messages) regenerate the same answer, and
# CPU generation costs 6-8 s. Keying on the fully-built messages means retrieval
# context, conversation history, and corpus changes all change the key naturally —
# a rebuilt index or a new turn produces different messages and misses the cache.
# In-memory + bounded + TTL; lost on restart (fine — a warm process is the win).
# Disable with KENN_LLM_CACHE=0.

def _get_db_path() -> Path:
    db_dir = PROJECT_ROOT / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "llm_cache.db"


def _init_db() -> None:
    db_path = _get_db_path()
    with sqlite3.connect(db_path, timeout=10.0) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_answer_cache (
                key TEXT PRIMARY KEY,
                timestamp REAL,
                content TEXT
            )
            """
        )
        conn.commit()


_CACHE_MAX = int(os.environ.get("KENN_LLM_CACHE_MAX", "512"))
_CACHE_TTL = float(os.environ.get("KENN_LLM_CACHE_TTL", str(24 * 3600)))


def cache_enabled() -> bool:
    return os.environ.get("KENN_LLM_CACHE", "1").strip().lower() in {"1", "true", "yes", "on"}


def _cache_key(cfg: dict, messages: list[dict[str, str]]) -> str:
    blob = json.dumps(
        {"model": cfg.get("model", ""), "messages": messages},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    if not cache_enabled():
        return None
    try:
        _init_db()
        db_path = _get_db_path()
        with sqlite3.connect(db_path, timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content, timestamp FROM llm_answer_cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            content, ts = row
            if _CACHE_TTL > 0 and (time.time() - ts) > _CACHE_TTL:
                cursor.execute("DELETE FROM llm_answer_cache WHERE key = ?", (key,))
                conn.commit()
                return None
            return content
    except Exception as e:
        print(f"LLM cache read error: {e}")
        return None


def _cache_put(key: str, content: str) -> None:
    if not cache_enabled() or not content:
        return
    try:
        _init_db()
        db_path = _get_db_path()
        with sqlite3.connect(db_path, timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO llm_answer_cache (key, timestamp, content) VALUES (?, ?, ?)",
                (key, time.time(), content)
            )
            # Evict oldest entries beyond _CACHE_MAX
            cursor.execute("SELECT COUNT(*) FROM llm_answer_cache")
            count = cursor.fetchone()[0]
            if count > _CACHE_MAX:
                cursor.execute(
                    """
                    DELETE FROM llm_answer_cache 
                    WHERE key NOT IN (
                        SELECT key FROM llm_answer_cache 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    )
                    """,
                    (_CACHE_MAX,)
                )
            conn.commit()
    except Exception as e:
        print(f"LLM cache write error: {e}")


def clear_answer_cache() -> None:
    """Drop all cached answers (e.g. after an index rebuild or for tests)."""
    try:
        _init_db()
        db_path = _get_db_path()
        with sqlite3.connect(db_path, timeout=5.0) as conn:
            conn.execute("DELETE FROM llm_answer_cache")
            conn.commit()
    except Exception as e:
        print(f"LLM cache clear error: {e}")


def _cached_usage(cfg: dict, task: str, content: str) -> LLMUsage:
    """Synthetic usage record for a cache hit (0 latency, flagged as cached)."""
    return LLMUsage(
        model=cfg["model"],
        provider=cfg["provider"],
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=0,
        task=f"{task}:cached",
    )


def _chat_completion(
    messages: list[dict[str, str]],
    task: str = "rewrite",
    *,
    system_prompt: str | None = None,
    answer_mode: str = "",
) -> tuple[str, LLMUsage]:
    """Non-streaming chat completion. Returns (content, usage)."""
    cfg = config(task)
    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + [
            m for m in messages if m.get("role") != "system"
        ]
    elif not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": build_system_prompt()}] + messages

    cache_key = _cache_key(cfg, messages)
    cached = _cache_get(cache_key)
    if cached is not None:
        usage = _cached_usage(cfg, task, cached)
        _add_usage(usage)
        return cached, usage

    payload = _build_payload(cfg, messages, stream=False, answer_mode=answer_mode)
    headers = _build_headers(cfg)
    client = _get_client()
    started = time.perf_counter()

    # One retry on transient connection failures only (not on a timeout or
    # any HTTP status -- those are either already the full configured
    # budget or a real application-level error that would just fail the
    # same way again). Ollama's ~5-minute idle cold-reload (see comments
    # elsewhere in this file) manifests as exactly this class of hiccup --
    # a single retry after a short pause turns a one-off connection blip
    # into a successful generation instead of silently dropping straight to
    # the unpolished template answer.
    last_connect_error: httpx.ConnectError | None = None
    for attempt in range(2):
        try:
            response = client.post(
                f"{cfg['base_url']}/chat/completions",
                json=payload,
                headers=headers,
                # Found live 2026-08-10: this call never overrode the
                # shared client's fixed 90s default (_get_client()), so
                # AUDIO_TOO_LLM_TIMEOUT / cfg["timeout"] had zero real
                # effect -- it only ever appeared in the TimeoutError
                # message text below, cosmetic, not the actual budget
                # that was being enforced.
                timeout=httpx.Timeout(cfg["timeout"], connect=15.0),
            )
            response.raise_for_status()
            data = response.json()
            break
        except httpx.ConnectError as e:
            last_connect_error = e
            if attempt == 0:
                time.sleep(1.0)
                continue
            raise RuntimeError(f"LLM connection failed after retry: {e}") from last_connect_error
        except httpx.TimeoutException:
            raise TimeoutError(f"LLM timed out after {cfg['timeout']}s")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"LLM returned {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            raise ValueError(f"LLM request failed: {e}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("LLM returned no choices")
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise ValueError("LLM returned empty content")

    usage_data = data.get("usage") or {}
    usage = LLMUsage(
        model=cfg["model"],
        provider=cfg["provider"],
        prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
        completion_tokens=int(usage_data.get("completion_tokens", 0)),
        total_tokens=int(usage_data.get("total_tokens", 0)),
        latency_ms=elapsed_ms,
        task=task,
    )
    _add_usage(usage)
    _cache_put(cache_key, content)
    return content, usage


def chat_completion(
    messages: list[dict[str, str]],
    task: str = "rewrite",
    *,
    system_prompt: str | None = None,
) -> str:
    """Backward-compatible non-streaming chat completion. Returns content string only.

    External callers (test_llm_config.py, analysis_interpretation.py) expect just the string.
    Internal callers should use _chat_completion() for usage tracking.
    """
    content, _usage = _chat_completion(messages, task=task, system_prompt=system_prompt)
    return content


def chat_completion_stream(
    messages: list[dict[str, str]],
    task: str = "rewrite",
    *,
    system_prompt: str | None = None,
    answer_mode: str = "",
) -> Generator[tuple[str, LLMUsage | None], None, None]:
    """Streaming chat completion. Yields (token_chunk, usage_or_None).

    The final yield will contain the accumulated usage data.
    """
    cfg = config(task)
    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + [
            m for m in messages if m.get("role") != "system"
        ]
    elif not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": build_system_prompt()}] + messages

    cache_key = _cache_key(cfg, messages)
    cached = _cache_get(cache_key)
    if cached is not None:
        usage = _cached_usage(cfg, task, cached)
        _add_usage(usage)
        yield cached, None
        yield "", usage
        return

    payload = _build_payload(cfg, messages, stream=True, answer_mode=answer_mode)
    headers = _build_headers(cfg)
    client = _get_client()
    started = time.perf_counter()
    _accumulated: list[str] = []

    try:
        with client.stream(
            "POST",
            f"{cfg['base_url']}/chat/completions",
            json=payload,
            headers=headers,
            # Same fix as the non-streaming call above -- this never
            # overrode the shared client's fixed 90s default either.
            timeout=httpx.Timeout(cfg["timeout"], connect=15.0),
        ) as response:
            response.raise_for_status()
            prompt_tokens = 0
            completion_tokens = 0
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            _accumulated.append(content)
                            yield content, None
                    # Track usage if provided (OpenAI sends it on final chunk)
                    usage_data = data.get("usage") or {}
                    if usage_data:
                        prompt_tokens = int(usage_data.get("prompt_tokens", 0))
                        completion_tokens = int(usage_data.get("completion_tokens", 0))
                except json.JSONDecodeError:
                    continue
    except httpx.TimeoutException:
        raise TimeoutError(f"LLM stream timed out after {cfg['timeout']}s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"LLM returned {e.response.status_code}: {e.response.text[:200]}")
    except Exception as exc:
        print(f"WARNING: chat_completion_stream ended early on an unexpected error ({exc!r}) -- "
              f"caller sees a normally-terminated stream with no indication generation was cut short")
        return

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    usage = LLMUsage(
        model=cfg["model"],
        provider=cfg["provider"],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        latency_ms=elapsed_ms,
        task=task,
    )
    _add_usage(usage)
    _cache_put(cache_key, "".join(_accumulated))
    yield "", usage  # signal end with usage data


# ---------------------------------------------------------------------------
# LLM routing fallback — when keyword routing fails
# ---------------------------------------------------------------------------

ROUTE_CLASSIFICATION_PROMPT = """Classify the following user query into one of these categories.
Reply with ONLY a single word from the list below — no explanation, no punctuation, no extra text.

Categories:
- ableton — Specific Ableton Live features, devices, routing, shortcuts, warp, automation, freezing, MIDI, clips, Session View, Arrangement View
- production — Mixing, mastering, EQ, compression, saturation, reverb, delay, bass, drums, vocals, loudness, translation, monitoring
- mix_review — Questions about an uploaded mix review, metrics, flags, action plan, revision steps
- game_audio — Wwise, game audio implementation, SoundBanks, events, interactive music
- conversation — Greetings, thanks, how-are-you, meta questions about the assistant
- out_of_scope — Non-audio topics (legal, medical, finance, cooking, etc.)

Query: {query}
"""


def llm_route_query(query: str) -> str | None:
    """Use the LLM to classify a query when keyword routing fails.

    Returns a route string or None if LLM is not available.
    """
    if not is_enabled("route"):
        return None
    user_msg = ROUTE_CLASSIFICATION_PROMPT.format(query=query[:500])
    messages = [{"role": "user", "content": user_msg}]
    cfg = config("route")
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.05,  # very low temperature for classification
        "max_tokens": 20,
    }
    headers = _build_headers(cfg)
    client = _get_client()
    try:
        response = client.post(
            f"{cfg['base_url']}/chat/completions",
            json=payload,
            headers=headers,
            # Same fixed-90s-default bug as _chat_completion/
            # _chat_completion_stream -- fixed alongside those.
            timeout=httpx.Timeout(cfg["timeout"], connect=15.0),
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = str(choices[0].get("message", {}).get("content", "")).strip().lower()
        valid = {"ableton", "production", "mix_review", "game_audio", "conversation", "out_of_scope"}
        for word in content.split():
            word = word.strip(".,!?\"'")
            if word in valid:
                return word
    except Exception as exc:
        print(f"WARNING: llm_route_query failed ({exc!r}) -- caller falls back to keyword routing")
        return None
    return None


# ---------------------------------------------------------------------------
# Enhanced answer generation — feeds raw chunks for synthesis
# ---------------------------------------------------------------------------

def _build_synthesis_messages(
    query: str,
    template_answer: str,
    results: list[tuple[float, dict]],
    history: list | None,
    history_context: str,
    source_label: callable,
    normalize_history: callable,
    *,
    answer_mode: str = "",
    route: str = "unknown",
    timeline_context: str | None = None,
    skill_level: str = "",
) -> list[dict]:
    """Build the messages array for answer synthesis.

    Instead of asking the LLM to 'improve' a pre-built template answer, we:
    1. Give the LLM the raw source excerpts
    2. Include the template answer as a 'draft' reference (not as the primary source)
    3. Let the LLM synthesise its own answer from the raw sources
    """
    system_prompt = build_system_prompt(answer_mode=answer_mode, route=route, query=query, skill_level=skill_level)

    # Build raw context from chunks
    raw_context = build_raw_context_block(results, source_label)
    if timeline_context:
        raw_context = f"Track Review History Timeline:\n{timeline_context}\n\n" + raw_context

    # Build user message parts (static/cacheable content first, dynamic query last)
    user_parts = []

    user_parts.append(
        "Source excerpts (use these to answer — do not add information outside these excerpts):\n"
        f"{raw_context}"
    )

    user_parts.append(
        "Draft answer from the local index (use this as a reference for structure and facts, "
        "but prefer synthesising directly from the source excerpts above):\n"
        f"{template_answer[:3500]}"
    )

    if history_context:
        user_parts.append(f"Conversation context: {history_context}")

    user_parts.append(f"User question: {query}")

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for turn in normalize_history(history):
        role = "assistant" if turn["role"] == "assistant" else "user"
        messages.append({"role": role, "content": turn["content"][:900]})
    messages.append({"role": "user", "content": "\n\n".join(user_parts)})
    return messages


# Same synonym sets kenn/core/chat_grounding.py's answer_quality_report()
# already uses for *scoring* section presence -- ported here 2026-08-02 so
# the final accept/reject gate (valid_structure(), via valid_response(),
# via enhance()) recognizes the same headers instead of a stricter,
# independent 3-exact-string check. Found live-testing: a real, substantive
# qwen2.5:1.5b answer used a MODE_INSTRUCTIONS-driven header ("Diagnosis
# boundary:" for mix_diagnosis mode) instead of the literal "Try this:"
# string, and got discarded outright in favour of the far more rigid
# deterministic template -- backwards from what should happen when the LLM
# actually did its job. "sources:" stays a literal, required check: there's
# no legitimate synonym for citing sources, and it costs the model nothing
# to include it verbatim.
_SHORT_ANSWER_MARKERS = (
    "short answer:", "direct solution is:", "main recommendation:",
    "recommended production technique:", "direct advice:",
    "to address your query directly:", "symptom and likely cause:",
    "the concept:", "the reasoning:", "why this works:",
)
_TRY_THIS_MARKERS = (
    "try this:", "try this in your session:", "try it:", "to apply this:",
    "step-by-step", "correction steps", "try this workflow", "concrete steps",
)


def valid_structure(text: str) -> bool:
    """Check for the required answer structure sections."""
    lowered = text.lower()
    numbered_steps = len(re.findall(r"(?m)^\s*\d+\.\s+\S+", text))
    has_short_answer = any(marker in lowered for marker in _SHORT_ANSWER_MARKERS)
    has_try_this = numbered_steps >= 2 or any(marker in lowered for marker in _TRY_THIS_MARKERS)
    has_sources = "sources:" in lowered
    return has_short_answer and has_try_this and has_sources


def valid_response(text: str, answer_mode: str = "") -> bool:
    """Validate the response contract for written and spoken answers."""
    stripped = text.strip()
    if answer_mode == "voice":
        # Voice mode deliberately forbids the headings required for written
        # answers. Reject empty, rambling, or accidentally formatted output.
        return bool(stripped) and len(stripped.split()) <= 100 and not any(
            heading in stripped.lower()
            for heading in ("short answer:", "try this:", "sources:")
        )
    return valid_structure(stripped)


def valid_note_structure(text: str) -> bool:
    """Check for the required note structure sections."""
    lowered = text.lower()
    return (
        "short answer:" in lowered
        and "try this:" in lowered
        and "why it matters:" in lowered
    )


# ---------------------------------------------------------------------------
# Public API — used by chat.py / server.py
# ---------------------------------------------------------------------------

def enhance_stream(
    query: str,
    template_answer: str,
    results: list[tuple[float, dict]],
    history: list | None,
    history_context: str,
    source_label: callable,
    normalize_history: callable,
    *,
    answer_mode: str = "",
    route: str = "unknown",
    timeline_context: str | None = None,
    skill_level: str = "",
):
    """Stream LLM-enhanced answer with usage tracking.

    Yields dicts with either:
      {"event": "token", "token": "..."}
      {"event": "llm_usage", "data": {...}}
    """
    if not is_enabled():
        return

    messages = _build_synthesis_messages(
        query,
        template_answer,
        results,
        history,
        history_context,
        source_label,
        normalize_history,
        answer_mode=answer_mode,
        route=route,
        timeline_context=timeline_context,
        skill_level=skill_level,
    )

    try:
        for token, usage in chat_completion_stream(messages, "rewrite", answer_mode=answer_mode):
            if token:
                yield {"event": "token", "token": token}
            if usage and usage.total_tokens > 0:
                yield {"event": "llm_usage", "data": usage.to_dict()}
    except Exception as exc:
        print(f"WARNING: enhance_stream ended early on an unexpected error ({exc!r}) -- "
              f"caller sees a normally-terminated stream with no indication generation was cut short")
        return


def build_context_block(results: list[tuple[float, dict]], source_label) -> str:
    """Legacy context block builder — kept for backward compatibility."""
    return build_raw_context_block(results, source_label, max_chars=3200)


def enhance(
    query: str,
    template_answer: str,
    results: list[tuple[float, dict]],
    history: list | None,
    history_context: str,
    source_label: callable,
    normalize_history: callable,
    *,
    answer_mode: str = "",
    route: str = "unknown",
    timeline_context: str | None = None,
    skill_level: str = "",
) -> str | None:
    """Non-streaming LLM enhancement with dynamic system prompt and raw-context synthesis.

    Returns the enhanced text, or None if the LLM was unavailable or the result
    failed the structure check.
    """
    if not is_enabled():
        return None

    messages = _build_synthesis_messages(
        query,
        template_answer,
        results,
        history,
        history_context,
        source_label,
        normalize_history,
        answer_mode=answer_mode,
        route=route,
        timeline_context=timeline_context,
        skill_level=skill_level,
    )

    try:
        text, usage = _chat_completion(messages, "rewrite", answer_mode=answer_mode)
    except Exception:
        # Found 2026-08-02 while live-testing: _chat_completion() wraps a
        # persistent connection failure (after its own one retry) and any
        # non-timeout HTTP status error (wrong/unavailable model name, a
        # 500, rate limiting, ...) in a bare RuntimeError -- not any of
        # TimeoutError/ValueError/httpx.HTTPError/httpx.TimeoutException.
        # That narrower tuple let a RuntimeError escape uncaught, crashing
        # the whole KENN answer instead of degrading to the deterministic
        # template answer, which is the entire point of this try/except
        # (see this function's own docstring). Every other _chat_completion
        # caller in this file already catches broad Exception; matching
        # that here instead of chasing the exact exception-type list again.
        return None

    text = re.sub(r"^#+\s*", "", text, flags=re.M).strip()
    from kenn.llm.linter import lint_response
    text = lint_response(text, answer_mode)
    if not valid_response(text, answer_mode):
        return None
    return text


def status_message() -> str:
    cfg = config()
    if not cfg["enabled"]:
        return "LLM rewrite off (set AUDIO_TOO_LLM_ENABLED=1 in .env)"
    route_cfg = config("route") if is_enabled("route") else None
    parts = [f"LLM rewrite on — {cfg['model']}"]
    if route_cfg and route_cfg["model"] != cfg["model"]:
        parts.append(f"routing via {route_cfg['model']}")
    if cfg["provider"] == "ollama":
        parts.append(f"@ {cfg['base_url']}")
    if not cfg["api_key"] and cfg["provider"] != "ollama":
        parts.append("(no API key set)")
    return " · ".join(parts)


def public_status() -> dict:
    return {
        "enabled": config()["enabled"],
        "ready": is_enabled(),
        "provider": config()["provider"],
        "model": config()["model"],
        "route_model": config("route")["model"] if is_enabled("route") else None,
        "message": status_message(),
    }


def enhance_paraphrase_note(
    draft_markdown: str,
    *,
    title: str = "",
    transcript_excerpt: str = "",
    answer_mode: str = "",
    route: str = "unknown",
) -> str | None:
    """Paraphrase a training note using the LLM.

    Uses the PARAPHRASE_SYSTEM_PROMPT and per-task model routing.
    """
    if not is_enabled("paraphrase"):
        return None

    system_prompt = PARAPHRASE_SYSTEM_PROMPT
    excerpt_block = ""
    if transcript_excerpt.strip():
        excerpt_block = (
            "\n\nSource transcript excerpt (facts and steps must be grounded here):\n"
            f"{transcript_excerpt.strip()[:6000]}"
        )
    user = (
        f"Note title: {title or 'Untitled'}\n\n"
        "Rewrite the draft below into the required note structure. "
        "Keep metadata lines at the top unchanged; Status must remain Draft.\n"
        f"{excerpt_block}\n\n"
        f"Draft to improve:\n{draft_markdown[:8000]}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]
    try:
        text, usage = _chat_completion(messages, "paraphrase")
    except Exception:
        # See the matching note in enhance() above -- a persistent
        # connection failure or HTTP status error raises a bare
        # RuntimeError, which this narrower tuple didn't catch.
        return None
    text = re.sub(r"^#+\s*", "", text, flags=re.M).strip()
    if not valid_note_structure(text):
        return None
    return text


PARAPHRASE_SYSTEM_PROMPT = """You rewrite draft training notes derived from video transcripts or web articles into Audio_Too training notes.

Rules:
- Keep every metadata line at the top exactly as provided (Type, Tags, Status, Source *, Transcript file). Status must stay Draft.
- Use this structure with these headings:
  Short answer:
  Key ideas:
  Try this:
  (numbered steps 1. 2. 3.)
  Why it matters:
  Related questions:
  Useful terms:
  Editor notes:
- Remove YouTube filler, patron promos, subscribe calls, and off-topic creator chatter.
- Use clear UK-friendly production language. Do not invent steps or devices not supported by the source excerpt.
- Do not mention OpenAI, ChatGPT, or that you are an AI model."""


def get_public_usage_stats() -> dict:
    """Return aggregated usage stats for the status endpoint."""
    if not _global_usage:
        return {"total_calls": 0, "total_tokens": 0}
    total_tokens = sum(u.total_tokens for u in _global_usage)
    total_calls = len(_global_usage)
    recent = [u for u in _global_usage if u.latency_ms > 0][-20:]
    avg_latency = int(sum(u.latency_ms for u in recent) / len(recent)) if recent else 0
    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "avg_latency_ms": avg_latency,
        "model": config()["model"],
    }


# ---------------------------------------------------------------------------
# Ensure backward-compatible imports
# ---------------------------------------------------------------------------

ssl_context = lambda: ssl.create_default_context()  # noqa: E731 — kept for any external importers


def critique_answer(query: str, answer: str, context: str, past_reasoning: str) -> dict:
    """Ask local LLM to critique the answer against sources and past reasoning."""
    import logging
    import json
    import re
    log = logging.getLogger("kenn.llm.llm_rewrite")

    system_prompt = (
        "You are KENN's self-critique engine. Analyze the proposed answer against the source excerpts and past reasoning.\n"
        "Check:\n"
        "1. Does the answer contain any unsupported claims or assumptions not found in the source excerpts?\n"
        "2. Does the answer contradict the past reasoning conclusions?\n\n"
        "Return a JSON object in this format (no markdown fences, just raw JSON):\n"
        "{\n"
        '  "passed": true | false,\n'
        '  "warnings": ["warning 1"],\n'
        '  "unsupported_claims": ["claim 1"],\n'
        '  "contradictions": ["contradiction 1"]\n'
        "}"
    )
    user_content = (
        f"Source Excerpts:\n{context}\n\n"
        f"Past Reasoning:\n{past_reasoning}\n\n"
        f"Proposed Answer:\n{answer}\n\n"
        f"Query: {query}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    try:
        content, _ = _chat_completion(messages, "paraphrase")
        clean = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.IGNORECASE).strip()
        return json.loads(clean)
    except Exception as e:
        log.warning(f"LLM critique failed: {e}")
        return {"passed": True, "warnings": [], "unsupported_claims": [], "contradictions": []}


def generate_lesson(query: str, conclusion: str, correction: str) -> str | None:
    """Generate a concise lesson learned from user correction using local LLM."""
    import logging
    log = logging.getLogger("kenn.llm.llm_rewrite")

    system_prompt = (
        "You are KENN's knowledge learning engine. Summarize the user's correction into a single concise lesson "
        "learned for future audio engineering queries. Write exactly one sentence, e.g., 'For parallel compression, "
        "prefer -4 dB threshold over -6 dB to preserve punch.' Do not include any intro/outro text."
    )
    user_content = (
        f"Query: {query}\n"
        f"KENN Conclusion: {conclusion}\n"
        f"User Correction: {correction}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    try:
        content, _ = _chat_completion(messages, "paraphrase")
        return content.strip()
    except Exception as e:
        log.warning(f"LLM lesson generation failed: {e}")
        return None


CONVERSATIONAL_SYSTEM_PROMPT = (
    "You are KENN (and Thursday) — a warm, witty, highly knowledgeable senior audio engineer and studio partner for Jack at Audio_Too.\n"
    "Respond to the user's message in a natural, friendly, conversational AI chatbot style.\n"
    "Rules:\n"
    "- Be direct, engaging, warm, and natural. Answer questions directly and naturally.\n"
    "- Speak like a real human engineer in the control room. Use natural UK spelling and contractions ('I'd', 'we'll', 'you'll').\n"
    "- If the user asks a casual, personal, or playful question (or joke), answer lightheartedly as a trusted studio companion.\n"
    "- Keep responses concise (1 to 3 natural sentences or paragraphs)."
)


def generate_conversational_llm_response(query: str, history: list | None = None) -> str | None:
    """Generate a dynamic conversational response for non-technical or casual chat using LLM."""
    if not truthy("AUDIO_TOO_LLM_ENABLED"):
        return None
    try:
        messages = []
        if history:
            for turn in history[-4:]:
                if isinstance(turn, dict):
                    role = turn.get("role", "user")
                    content = turn.get("content", turn.get("text", ""))
                    if content:
                        messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": query})
        
        response, _usage = _chat_completion(
            messages,
            task="chat",
            system_prompt=CONVERSATIONAL_SYSTEM_PROMPT,
        )
        return response if response else None
    except Exception:
        return None
