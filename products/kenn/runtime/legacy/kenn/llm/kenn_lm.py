"""Wrapper for loading and generating answers using the local fine-tuned KENN language model.

Prefers MLX (Metal-native, ~29 tok/s on Apple Silicon) over the HF Transformers/PEFT
path (~6.5 tok/s under HF's MPS backend even natively) — a known Apple Silicon gap,
the same reason thursday/voice.py prefers mlx-whisper over faster-whisper. Since the
project venv is x86_64 (Rosetta), MLX generation runs via subprocess in the native
arm64 system Python that already hosts mlx/mlx-lm (see thursday/voice.py's _MLX_CMD).
The Transformers/PEFT path remains as a fallback when MLX isn't available.
"""

from __future__ import annotations

import json
import socket
import subprocess
import tempfile
from pathlib import Path

KENN_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = KENN_DIR / "artifacts" / "models" / "kenn-lora"
MLX_MODEL_PATH = KENN_DIR / "artifacts" / "models" / "kenn-mlx"

_MLX_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
_MLX_CMD = ["arch", "-arm64", _MLX_PYTHON]

# Persistent model server (kenn_lm_server.py) — loads the MLX model once and
# stays warm, instead of the per-call subprocess path below reloading it from
# disk on every single generation (see docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md).
_SERVER_SCRIPT = Path(__file__).resolve().parent / "kenn_lm_server.py"
_SERVER_SOCKET = Path(tempfile.gettempdir()) / "kenn_lm_server.sock"
_SERVER_PING_TIMEOUT = 0.5
_last_start_attempt_time = 0.0

_MLX_WORKER_SCRIPT = """
import json, sys
from mlx_lm import load, generate

with open(sys.argv[1], "r", encoding="utf-8") as f:
    job = json.load(f)

model, tokenizer = load(job["model_path"])
prompt = tokenizer.apply_chat_template(job["messages"], tokenize=False, add_generation_prompt=True)
text = generate(
    model, tokenizer, prompt=prompt,
    max_tokens=job.get("max_new_tokens", 450),
    verbose=False,
)

with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump({"text": text}, f)
"""


def _send_to_server(job: dict, *, connect_timeout: float, response_timeout: float = 180.0) -> dict | None:
    """Send one newline-delimited JSON request to the persistent server.

    Two different timeouts on purpose: connecting should fail fast
    (connect_timeout) if the server isn't running yet, but once connected a
    real generation call can legitimately take many seconds — that wait
    uses response_timeout, matching the subprocess fallback's 180s budget.

    Returns the parsed response dict, or None if the server isn't reachable
    (not started, still loading, or crashed) so the caller can fall back.
    """
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(connect_timeout)
            sock.connect(str(_SERVER_SOCKET))
            sock.sendall((json.dumps(job) + "\n").encode("utf-8"))
            sock.settimeout(response_timeout)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if chunk.endswith(b"\n"):
                    break
            data = b"".join(chunks).decode("utf-8").strip()
            return json.loads(data) if data else None
    except Exception:
        return None


def _send_to_server_stream(job: dict, *, connect_timeout: float, response_timeout: float = 180.0):
    """Send a streaming request to the persistent server and yield parsed JSON chunks."""
    job_payload = dict(job)
    job_payload["stream"] = True
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(connect_timeout)
            sock.connect(str(_SERVER_SOCKET))
            sock.sendall((json.dumps(job_payload) + "\n").encode("utf-8"))
            sock.settimeout(response_timeout)
            buffer = ""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            parsed = json.loads(line)
                            yield parsed
                            if parsed.get("done"):
                                return
                        except Exception:
                            pass
    except Exception:
        return


_MLX_AVAILABLE_CACHE: bool | None = None


def _ensure_server_started(wait_timeout: float = 5.0) -> bool:
    """Launch the persistent MLX server once, detached, if not already running.

    If wait_timeout > 0, briefly waits (polling every 50ms) for the socket
    to become active so the immediate first turn can use the persistent server
    instead of paying the 20s cold-start subprocess cost.
    """
    global _last_start_attempt_time
    import time
    now = time.time()
    if now - _last_start_attempt_time < 60.0:
        return _SERVER_SOCKET.exists()
    _last_start_attempt_time = now
    try:
        log_file = open("/tmp/kenn_lm_server_start.log", "a")
        log_file.write(f"\n--- Starting server at {time.ctime()} ---\n")
        log_file.flush()
        subprocess.Popen(
            _MLX_CMD + [str(_SERVER_SCRIPT), str(MLX_MODEL_PATH), str(_SERVER_SOCKET)],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
    except Exception as e:
        try:
            with open("/tmp/kenn_lm_server_start.log", "a") as f:
                f.write(f"Failed to start subprocess: {e}\n")
        except Exception:
            pass

    if wait_timeout > 0:
        start_wait = time.time()
        while time.time() - start_wait < wait_timeout:
            if _SERVER_SOCKET.exists():
                ping_res = _send_to_server({"op": "ping"}, connect_timeout=0.2)
                if ping_res is not None and ping_res.get("ok"):
                    return True
            time.sleep(0.05)
    return _SERVER_SOCKET.exists()


def _mlx_lm_available() -> bool:
    """Check if mlx-lm and a converted MLX model are available."""
    global _MLX_AVAILABLE_CACHE
    if _MLX_AVAILABLE_CACHE is not None:
        return _MLX_AVAILABLE_CACHE
    if not MLX_MODEL_PATH.exists():
        _MLX_AVAILABLE_CACHE = False
        return False
    if _SERVER_SOCKET.exists() or Path(_MLX_PYTHON).exists():
        _MLX_AVAILABLE_CACHE = True
        return True
    try:
        result = subprocess.run(
            _MLX_CMD + ["-c", "import mlx_lm; print('ok')"],
            capture_output=True, timeout=30,
        )
        _MLX_AVAILABLE_CACHE = (result.returncode == 0 and b"ok" in result.stdout)
        return _MLX_AVAILABLE_CACHE
    except Exception:
        _MLX_AVAILABLE_CACHE = False
        return False


class KennLM:
    """Manages the local fine-tuned language model for KENN."""
    def __init__(self, model_dir: Path = MODEL_PATH):
        self.model_dir = model_dir
        self.model = None
        self.tokenizer = None
        self.device = None
        self._torch = None
        self.available = False
        self.base_model_name = "Qwen/Qwen2.5-1.5B-Instruct"

        self.use_mlx = _mlx_lm_available()
        if self.use_mlx:
            self.available = True
            print(f"Local KENN Language Model will use MLX ({MLX_MODEL_PATH}).")
            return

        try:
            from peft import PeftModel
        except ImportError:
            print("PEFT library not available. KennLM will run in fallback/inactive mode.")
            return

        self._load_model(PeftModel)

    def _load_model(self, peft_model_cls) -> None:
        """Load tokenizer and fine-tuned model weights."""
        if not self.model_dir.exists():
            print(f"Fine-tuned model directory {self.model_dir} not found. KennLM is inactive.")
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self._torch = torch
            # Determine best hardware acceleration
            if torch.backends.mps.is_available():
                self.device = torch.device("mps")
                dtype = torch.float16
            elif torch.cuda.is_available():
                self.device = torch.device("cuda")
                dtype = torch.float16
            else:
                self.device = torch.device("cpu")
                dtype = torch.float32

            print(f"Loading tokenizer from {self.model_dir}...")
            self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), trust_remote_code=True)
            if self.tokenizer.pad_token_id is None:
                self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

            # Determine the base model from adapter config or default to Qwen
            adapter_config_path = self.model_dir / "adapter_config.json"
            base_model_id = self.base_model_name
            if adapter_config_path.exists():
                try:
                    with open(adapter_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        base_model_id = config.get("base_model_name_or_path", base_model_id)
                except Exception:
                    pass

            print(f"Loading base model {base_model_id} in {dtype} on {self.device}...")
            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                torch_dtype=dtype,
                trust_remote_code=True
            )

            print(f"Loading LoRA adapters from {self.model_dir}...")
            self.model = peft_model_cls.from_pretrained(base_model, str(self.model_dir))
            self.model.to(self.device)
            self.model.eval()
            
            self.available = True
            print("Local KENN Language Model loaded successfully.")
        except Exception as e:
            print(f"Error loading local KENN LM: {e}")
            self.model = None
            self.tokenizer = None
            self.available = False

    def generate(self, query: str, context: str, history: list[dict[str, str]] | None = None,
                 *, self_correct: bool = True) -> str:
        """Generate answer grounded in the retrieved context using the local fine-tuned model.

        If ``self_correct`` is True (default), the answer is passed through a fast
        critique loop that checks for statements not supported by the source context.
        Unsupported statements are stripped before returning.
        """
        if not self.available:
            raise RuntimeError("KennLM is not loaded/available.")
        if not self.use_mlx and (self.model is None or self.tokenizer is None):
            raise RuntimeError("KennLM is not loaded/available.")

        # Build structural prompt
        messages = [
            {
                "role": "system",
                "content": (
                    "You are KENN, a senior audio engineer answering strictly from provided sources.\n"
                    "Format your response concisely with:\n"
                    "Short Answer: 1-2 direct sentences.\n"
                    "Try This:\n"
                    "1. Actionable step with specific settings from sources\n"
                    "2. Next actionable step\n"
                    "Why It Matters: Brief technical reason."
                )
            }
        ]

        if history:
            for turn in history[-4:]:  # Limit history to prevent prompt bloat
                messages.append({
                    "role": turn.get("role", "user"),
                    "content": turn.get("content") or turn.get("question") or ""
                })

        messages.append({
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion:\n{query}"
        })

        try:
            max_tokens = 220
            answer = self._run_generation(messages, max_new_tokens=max_tokens)

            if self_correct and answer:
                answer = self._critique_and_correct(answer, context, query)

            return answer
        except Exception as e:
            print(f"Error during local model generation: {e}")
            raise e

    def generate_stream(self, query: str, context: str, history: list[dict[str, str]] | None = None,
                        *, max_new_tokens: int = 220):
        """Generate answer tokens incrementally from the local model."""
        if not self.available:
            raise RuntimeError("KennLM is not loaded/available.")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are KENN, a senior audio engineer answering strictly from provided sources.\n"
                    "Format your response concisely with:\n"
                    "Short Answer: 1-2 direct sentences.\n"
                    "Try This:\n"
                    "1. Actionable step with specific settings from sources\n"
                    "2. Next actionable step\n"
                    "Why It Matters: Brief technical reason."
                )
            }
        ]
        if history:
            for turn in history[-4:]:
                messages.append({
                    "role": turn.get("role", "user"),
                    "content": turn.get("content") or turn.get("question") or ""
                })
        messages.append({
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion:\n{query}"
        })

        if self.use_mlx:
            _ensure_server_started()
            streamed_any = False
            for chunk in _send_to_server_stream(
                {"messages": messages, "max_new_tokens": max_new_tokens},
                connect_timeout=_SERVER_PING_TIMEOUT
            ):
                if chunk.get("ok") and "token" in chunk:
                    streamed_any = True
                    yield chunk["token"]
                elif chunk.get("done"):
                    return
            if streamed_any:
                return

        # Fallback if streaming server not active
        full = self.generate(query, context, history=history, self_correct=False)
        yield full

    def _run_generation(self, messages: list[dict], *, max_new_tokens: int = 220,
                        temperature: float = 0.3) -> str:
        """Run a single generation pass from a structured message list."""
        if self.use_mlx:
            return self._run_generation_mlx(messages, max_new_tokens=max_new_tokens)
        if self._torch is None:
            raise RuntimeError("PyTorch is not available for local generation.")
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

        with self._torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=temperature,
                top_p=0.9,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )

        new_tokens = output_ids[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    def _run_generation_mlx(self, messages: list[dict], *, max_new_tokens: int = 450) -> str:
        """Run a generation pass via mlx-lm in the native arm64 system Python.

        Prefers the persistent server (kenn_lm_server.py, model loaded once)
        over a fresh per-call subprocess — self_correct=True alone calls this
        up to 3x per answer turn, so a per-call full model reload was the
        real latency bottleneck once grounding was fixed (see
        docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md). Starts the server on
        first use if it isn't already running, and falls back to the
        original per-call subprocess path (unchanged) whenever the server
        isn't reachable yet or returns an error, so correctness never
        regresses even if the server has an issue.
        """
        response = _send_to_server(
            {"messages": messages, "max_new_tokens": max_new_tokens}, connect_timeout=_SERVER_PING_TIMEOUT
        )
        if response is None:
            # Not running yet (or just crashed) — start it and wait briefly for it to be ready
            if _ensure_server_started():
                response = _send_to_server(
                    {"messages": messages, "max_new_tokens": max_new_tokens}, connect_timeout=_SERVER_PING_TIMEOUT
                )
        if response and response.get("ok"):
            return str(response.get("text", "")).strip()

        return self._run_generation_mlx_subprocess(messages, max_new_tokens=max_new_tokens)

    def _run_generation_mlx_subprocess(self, messages: list[dict], *, max_new_tokens: int = 450) -> str:
        """Per-call fallback: spawn a fresh subprocess that loads the model
        from scratch. The project venv is x86_64 (Rosetta); MLX requires
        arm64, so this shells out to the same native interpreter
        thursday/voice.py uses for mlx-whisper. Input/output pass through
        temp files rather than stdout, since mlx-lm may print library
        warnings to stdout.
        """
        with tempfile.TemporaryDirectory() as tmp:
            job_path = Path(tmp) / "job.json"
            out_path = Path(tmp) / "out.json"
            job_path.write_text(json.dumps({
                "model_path": str(MLX_MODEL_PATH),
                "messages": messages,
                "max_new_tokens": max_new_tokens,
            }), encoding="utf-8")

            result = subprocess.run(
                _MLX_CMD + ["-c", _MLX_WORKER_SCRIPT, str(job_path), str(out_path)],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode != 0 or not out_path.exists():
                raise RuntimeError(f"MLX generation failed: {result.stderr.strip()[-500:]}")

            return json.loads(out_path.read_text(encoding="utf-8"))["text"].strip()

    def _critique_and_correct(self, answer: str, context: str, query: str) -> str:
        """Phase 10.2 — Self-correction critique loop.

        Passes the generated answer through a fast critique template that checks
        whether the answer contains information not supported by the source context.
        If unsupported statements are found, the answer is regenerated strictly.
        """
        # 1. Fast check: Extract measurements (numbers tied to audio units like dB, Hz, ms, LUFS)
        import re
        measurement_pattern = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:dbtp|dbfs|db|hz|khz|lufs|lu|ms|bpm|%|semitones?|cents?)", re.I)
        answer_measurements = set(m.group(0).lower().replace(" ", "") for m in measurement_pattern.finditer(answer))
        context_measurements = set(m.group(0).lower().replace(" ", "") for m in measurement_pattern.finditer(context))
        hallucinated = answer_measurements - context_measurements

        # If answer has no invented numbers and is short/clean, avoid redundant LLM critique round-trip
        if not hallucinated and len(answer) < 800:
            return answer

        critique_messages = [
            {
                "role": "system",
                "content": (
                    "You are a technical fact-checker for audio engineering. "
                    "Verify if the response draft makes fabricated technical claims or invents numbers/settings "
                    "not supported by the context. Rephrased facts, advice structure, and conversational English are SUPPORTED."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Context:\n{context}\n\n"
                    f"Question:\n{query}\n\n"
                    f"Response draft:\n{answer}\n\n"
                    f"Does this draft invent fabricated technical claims? "
                    f"Reply with exactly one word: SUPPORTED or UNSUPPORTED."
                )
            }
        ]

        try:
            # Fast check: 8 tokens max
            critique = self._run_generation(critique_messages, max_new_tokens=8, temperature=0.1)
        except Exception as e:
            return answer

        critique_upper = critique.strip().upper()

        if "UNSUPPORTED" in critique_upper and ("SUPPORTED" not in critique_upper or critique_upper.startswith("UN")):
            # If the critique genuinely finds fabricated content, run regeneration pass
            regen_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are KENN, a senior audio engineer. ONLY use information "
                        "from the provided sources. Do NOT add any information that "
                        "is not explicitly stated in the sources."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Context:\n{context}\n\n"
                        f"Question:\n{query}\n\n"
                        f"Answer strictly from the context above. If the context "
                        f"does not contain enough information, say so."
                    )
                }
            ]
            try:
                regenerated = self._run_generation(regen_messages, max_new_tokens=220, temperature=0.2)
                if regenerated and len(regenerated) > 20:
                    return regenerated
            except Exception:
                pass

        # Grounded or fallback
        return answer

    @staticmethod
    def _strip_unsupported(answer: str, critique: str) -> str:
        """Attempt to remove unsupported statements from the answer.

        Uses a simple heuristic: if the critique lists specific statements,
        remove sentences from the answer that overlap significantly with those.
        """
        # Extract unsupported lines from the critique
        lines = critique.split("\n")
        unsupported_fragments = []
        capture = False
        for line in lines:
            line = line.strip()
            if "UNSUPPORTED" in line.upper():
                capture = True
                # Check if the unsupported statement is on the same line
                after_colon = line.split(":", 1)
                if len(after_colon) > 1 and after_colon[1].strip():
                    unsupported_fragments.append(after_colon[1].strip().lower())
                continue
            if capture and line:
                # Remove common list prefixes
                clean = line.lstrip("- •*0123456789.").strip()
                if clean:
                    unsupported_fragments.append(clean.lower())

        if not unsupported_fragments:
            return answer

        # Split answer into sentences and filter
        sentences = answer.replace("\n", " ").split(". ")
        kept = []
        for sentence in sentences:
            sentence_lower = sentence.strip().lower()
            is_unsupported = False
            for fragment in unsupported_fragments:
                # Check for significant overlap (at least 3 consecutive matching words)
                frag_words = set(fragment.split())
                sent_words = set(sentence_lower.split())
                overlap = frag_words & sent_words
                if len(overlap) >= 3 and len(overlap) / max(len(frag_words), 1) > 0.4:
                    is_unsupported = True
                    break
            if not is_unsupported:
                kept.append(sentence.strip())

        return ". ".join(kept).strip()


def critique_answer(answer: str, context: str, query: str) -> dict:
    """Standalone critique function for use without the full model.

    Uses heuristic checks rather than LLM inference. Returns a dict with:
      - ``is_grounded``: bool
      - ``confidence``: float [0.0, 1.0]
      - ``issues``: list of potential grounding problems
    """
    issues = []

    # Heuristic 1: Check if the answer mentions specific numbers/values not in context
    import re
    answer_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\s*(?:Hz|kHz|dB|ms|%)\b', answer, re.IGNORECASE))
    context_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\s*(?:Hz|kHz|dB|ms|%)\b', context, re.IGNORECASE))
    ungrounded_numbers = answer_numbers - context_numbers
    if ungrounded_numbers:
        issues.append(f"Answer mentions values not found in sources: {', '.join(ungrounded_numbers)}")

    # Heuristic 2: Check for hedging phrases that suggest fabrication
    hedging_phrases = [
        "I think", "I believe", "it's generally", "it might be",
        "probably", "some people say", "many engineers",
    ]
    for phrase in hedging_phrases:
        if phrase.lower() in answer.lower():
            issues.append(f"Answer contains hedging phrase '{phrase}' suggesting ungrounded content")

    # Heuristic 3: Check if key answer terms appear in the context
    answer_words = set(answer.lower().split())
    context_words = set(context.lower().split())
    # Remove common words
    common = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
              "have", "has", "had", "do", "does", "did", "will", "would", "could",
              "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
              "at", "by", "from", "as", "into", "through", "and", "or", "but", "not",
              "this", "that", "it", "its", "you", "your", "we", "our", "they", "their"}
    meaningful_answer = answer_words - common
    meaningful_context = context_words - common
    if meaningful_answer:
        overlap_ratio = len(meaningful_answer & meaningful_context) / len(meaningful_answer)
        if overlap_ratio < 0.3:
            issues.append(
                f"Low term overlap between answer and sources ({overlap_ratio:.0%}). "
                f"Answer may contain significant ungrounded content."
            )

    confidence = max(0.0, 1.0 - len(issues) * 0.25)
    return {
        "is_grounded": len(issues) == 0,
        "confidence": round(confidence, 2),
        "issues": issues,
    }
