# ai/markov/core/base.py
# Project module `base` (ai).

# base.py
import random
import types
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


class BaseMarkov:
    def __init__(self, order: int = 2, smoothing: float = 0.01,
                 backoff_decay: float = 0.7, rng=random):
        self.order = order
        self.smoothing = smoothing
        self.backoff_decay = backoff_decay
        # RNG used for sampling transitions.
        #
        # Important: the stdlib `random` *module* is not picklable, which breaks
        # deepcopy() of trained models. We therefore store `None` when given the
        # module and fall back to module-level randomness at sampling time.
        #
        # Callers who want determinism should pass a seeded `random.Random()`.
        self.rng = None if isinstance(rng, types.ModuleType) else rng
        self.counts = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.totals = defaultdict(lambda: defaultdict(float))
        self.vocab = set()
        self._vocab_list = []
        self._vocab_to_idx = {}
        self._uniform_probs = None
        self._global_probs = None


        self._prob_cache: Dict[Tuple, Tuple] = {}

    def __getstate__(self):
        """
        Make instances picklable by stripping unpicklable defaultdict lambdas.
        """
        state = dict(self.__dict__)
        # Convert nested defaultdicts to plain dicts.
        counts_plain: Dict[int, Dict[Tuple[Any, ...], Dict[Any, float]]] = {}
        for n, ctx_map in getattr(self, "counts", {}).items():
            ctx_plain: Dict[Tuple[Any, ...], Dict[Any, float]] = {}
            for ctx, sym_map in ctx_map.items():
                ctx_plain[tuple(ctx)] = dict(sym_map)
            counts_plain[int(n)] = ctx_plain
        totals_plain: Dict[int, Dict[Tuple[Any, ...], float]] = {}
        for n, ctx_map in getattr(self, "totals", {}).items():
            ctx_plain2: Dict[Tuple[Any, ...], float] = {}
            for ctx, total in ctx_map.items():
                ctx_plain2[tuple(ctx)] = float(total)
            totals_plain[int(n)] = ctx_plain2
        state["counts"] = counts_plain
        state["totals"] = totals_plain
        # Cache can be recomputed; keep it empty to shrink pickle.
        state["_prob_cache"] = {}
        return state

    def __setstate__(self, state):
        """
        Restore nested defaultdict structure after unpickling.
        """
        from collections import defaultdict as _dd

        self.__dict__.update(state)
        # Restore defaultdict shells.
        counts_dd = _dd(lambda: _dd(lambda: _dd(float)))
        for n, ctx_map in (state.get("counts") or {}).items():
            for ctx, sym_map in (ctx_map or {}).items():
                for sym, v in (sym_map or {}).items():
                    counts_dd[int(n)][tuple(ctx)][sym] = float(v)
        totals_dd = _dd(lambda: _dd(float))
        for n, ctx_map in (state.get("totals") or {}).items():
            for ctx, total in (ctx_map or {}).items():
                totals_dd[int(n)][tuple(ctx)] = float(total)
        self.counts = counts_dd
        self.totals = totals_dd
        self._prob_cache = {}
        # Ensure rng fallback invariant.
        if getattr(self, "rng", None) is None:
            # Leave as None; sampling will fall back to module-level random.
            pass

    # ------------------------------------------------------------------
    # JSON serialization (string symbols only)
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """
        Return a JSON-serializable dict for this Markov model.

        Notes:
        - Symbols and context tokens are serialized as strings (via str()).
        - Counts/totals are stored in a compact nested mapping:
          counts[n][\"a|b|c\"][sym] = weight
        - This is intended for portability and inspection, not maximal compression.
        """
        # Ensure vocab list exists (train() populates it; but allow manual construction).
        vocab_list = list(getattr(self, "_vocab_list", []) or [])
        if not vocab_list and getattr(self, "vocab", None):
            try:
                vocab_list = sorted(list(self.vocab), key=repr)
            except Exception:
                vocab_list = [str(x) for x in list(self.vocab)]

        def _ctx_key(ctx: Tuple[Any, ...]) -> str:
            return "|".join(str(x) for x in (ctx or ()))

        counts_out: Dict[str, Dict[str, Dict[str, float]]] = {}
        for n, ctx_map in (getattr(self, "counts", {}) or {}).items():
            nn = str(int(n))
            out_ctx: Dict[str, Dict[str, float]] = {}
            for ctx, sym_map in (ctx_map or {}).items():
                try:
                    ctx_t = tuple(ctx)
                except Exception:
                    ctx_t = (ctx,)
                k = _ctx_key(ctx_t)
                out_ctx[k] = {str(sym): float(v) for sym, v in (sym_map or {}).items()}
            counts_out[nn] = out_ctx

        totals_out: Dict[str, Dict[str, float]] = {}
        for n, ctx_map in (getattr(self, "totals", {}) or {}).items():
            nn = str(int(n))
            out_ctx2: Dict[str, float] = {}
            for ctx, total in (ctx_map or {}).items():
                try:
                    ctx_t = tuple(ctx)
                except Exception:
                    ctx_t = (ctx,)
                k = _ctx_key(ctx_t)
                out_ctx2[k] = float(total)
            totals_out[nn] = out_ctx2

        return {
            "kind": type(self).__name__,
            "order": int(getattr(self, "order", 2)),
            "smoothing": float(getattr(self, "smoothing", 0.01)),
            "backoff_decay": float(getattr(self, "backoff_decay", 0.7)),
            "vocab": [str(x) for x in vocab_list],
            "counts": counts_out,
            "totals": totals_out,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any], *, rng=None) -> "BaseMarkov":
        """
        Restore a model from a dict produced by to_dict().
        """
        order = int((payload or {}).get("order", 2) or 2)
        smoothing = float((payload or {}).get("smoothing", 0.01) or 0.01)
        backoff_decay = float((payload or {}).get("backoff_decay", 0.7) or 0.7)
        m = cls(order=order, smoothing=smoothing, backoff_decay=backoff_decay, rng=rng or random)

        vocab = (payload or {}).get("vocab", []) or []
        try:
            m._vocab_list = [str(x) for x in list(vocab)]
        except Exception:
            m._vocab_list = []
        m.vocab = set(m._vocab_list)
        m._vocab_to_idx = {sym: i for i, sym in enumerate(m._vocab_list)}
        m._uniform_probs = None
        m._global_probs = None
        m._prob_cache = {}

        def _ctx_tuple(k: str) -> Tuple[str, ...]:
            if k is None:
                return tuple()
            s = str(k)
            if s == "":
                return tuple()
            return tuple(s.split("|"))

        counts_dd = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        totals_dd = defaultdict(lambda: defaultdict(float))

        counts_in = (payload or {}).get("counts", {}) or {}
        for n_str, ctx_map in (counts_in or {}).items():
            try:
                n = int(n_str)
            except Exception:
                continue
            for ctx_key, sym_map in (ctx_map or {}).items():
                ctx_t = _ctx_tuple(ctx_key)
                for sym, v in (sym_map or {}).items():
                    counts_dd[n][ctx_t][str(sym)] = float(v)

        totals_in = (payload or {}).get("totals", {}) or {}
        for n_str, ctx_map in (totals_in or {}).items():
            try:
                n = int(n_str)
            except Exception:
                continue
            for ctx_key, total in (ctx_map or {}).items():
                ctx_t = _ctx_tuple(ctx_key)
                totals_dd[n][ctx_t] = float(total)

        m.counts = counts_dd
        m.totals = totals_dd
        return m

    def train(self, sequences: List[List[Any]], sequence_weights: Optional[Sequence[float]] = None):
        if sequence_weights is None:
            sequence_weights = [1.0] * len(sequences)
        elif len(sequence_weights) != len(sequences):
            raise ValueError("sequence_weights must match sequences length")

        for seq, seq_weight in zip(sequences, sequence_weights):
            weight = max(0.0, float(seq_weight))
            if weight == 0.0:
                continue
            for n in range(1, self.order + 1):
                for i in range(len(seq) - n):
                    context = tuple(seq[i:i + n])
                    next_sym = seq[i + n]
                    self.counts[n][context][next_sym] += weight
                    self.totals[n][context] += weight
                    self.vocab.add(next_sym)
        self._vocab_list = sorted(self.vocab, key=repr)
        self._vocab_to_idx = {sym: i for i, sym in enumerate(self._vocab_list)}
        self._uniform_probs = None
        self._global_probs = None

        self._prob_cache.clear()

    def _get_uniform_probs(self):
        if self._uniform_probs is None:
            uniform = 1.0 / len(self._vocab_list)
            self._uniform_probs = {sym: uniform for sym in self._vocab_list}
        return self._uniform_probs.copy()

    def _get_global_probs(self) -> Dict[Any, float]:
        if self._global_probs is not None:
            return self._global_probs.copy()

        if not self._vocab_list:
            self._global_probs = {}
            return {}

        vocab_size = len(self._vocab_list)
        aggregated = np.full(vocab_size, self.smoothing, dtype=np.float64)

        for context_counter in self.counts[1].values():
            for sym, count in context_counter.items():
                aggregated[self._vocab_to_idx[sym]] += count

        total = aggregated.sum()
        if total <= 0.0:
            self._global_probs = self._get_uniform_probs()
        else:
            self._global_probs = {
                sym: float(aggregated[i] / total)
                for i, sym in enumerate(self._vocab_list)
            }
        return self._global_probs.copy()

    def get_next(self, context: List[Any], temperature: float = 1.0,
                 top_k: Optional[int] = None) -> Optional[Any]:
        # Fast path: use cached, deterministically-ordered (symbol, prob) tuples.
        context_tuple = tuple(context[-self.order:])
        items = self._get_probabilities_cached(context_tuple, temperature, top_k)
        if not items:
            return None
        symbols, weights = zip(*items)
        rng = getattr(self, "rng", None) or random
        return rng.choices(symbols, weights=weights)[0]

    def _get_probabilities_cached(
        self,
        context_tuple: Tuple[Any, ...],
        temperature: float,
        top_k: Optional[int],
    ) -> Tuple[Tuple[Any, float], ...]:
        """
        Internal method: compute and cache transition probabilities for a
        given context.  Results are stored in self._prob_cache (an ordinary
        dict on the instance) so the cache is automatically invalidated
        whenever train() is called.
        """
        if not self._vocab_list:
            return ()

        cache_key = (context_tuple, temperature, top_k)
        if cache_key in self._prob_cache:
            return self._prob_cache[cache_key]

        result = self._compute_probabilities(context_tuple, temperature, top_k)
        self._prob_cache[cache_key] = result
        return result

    def _compute_probabilities(
        self,
        context_tuple: Tuple[Any, ...],
        temperature: float,
        top_k: Optional[int],
    ) -> Tuple[Tuple[Any, float], ...]:

        vocab_size = len(self._vocab_list)
        max_context = min(self.order, len(context_tuple))
        blended = np.zeros(vocab_size, dtype=np.float64)
        total_weight = 0.0

        # Variable-order backoff (PPM-style): prefer the longest context that has
        # enough empirical support; otherwise fall back to shorter contexts.
        try:
            from audiogen_core.config import CONFIG

            min_total = int(getattr(CONFIG.composition, "markov_variable_order_min_total", 8) or 8)
        except Exception:
            min_total = 8
        min_total = max(1, int(min_total))

        for n in range(max_context, 0, -1):
            ctx = context_tuple[-n:]
            if ctx in self.totals[n] and self.totals[n][ctx] >= float(min_total):
                counter = self.counts[n][ctx]
                total = self.totals[n][ctx]
                denom = total + self.smoothing * vocab_size

                unseen_prob = self.smoothing / denom
                probs_array = np.full(vocab_size, unseen_prob, dtype=np.float64)

                # Override slots for symbols that were actually observed.
                for sym, count in counter.items():
                    idx = self._vocab_to_idx[sym]
                    probs_array[idx] = (count + self.smoothing) / denom

                weight = self.backoff_decay ** (max_context - n)
                blended += probs_array * weight
                total_weight += weight

        if total_weight > 0.0:
            probs_array = blended / total_weight
        else:
            fallback = self._get_global_probs()
            if not fallback:
                fallback = self._get_uniform_probs()
            probs_array = np.array([fallback[sym] for sym in self._vocab_list], dtype=np.float64)

        if temperature != 1.0:
            probs_array = probs_array ** (1.0 / temperature)
        probs_sum = probs_array.sum()
        if probs_sum <= 0.0:
            fallback = self._get_global_probs()
            if not fallback:
                fallback = self._get_uniform_probs()
            probs_array = np.array([fallback[sym] for sym in self._vocab_list], dtype=np.float64)
            probs_sum = probs_array.sum()
        probs_array /= probs_sum

        result_dict = {
            sym: float(probs_array[i])
            for i, sym in enumerate(self._vocab_list)
            if probs_array[i] > 0
        }
        if top_k is not None and len(result_dict) > top_k:
            # Deterministic tie-break: probability desc, then repr(symbol).
            sorted_items = sorted(
                result_dict.items(), key=lambda kv: (-float(kv[1]), repr(kv[0]))
            )[:top_k]
            result_dict = dict(sorted_items)
            total_prob = sum(result_dict.values())
            result_dict = {k: v / total_prob for k, v in result_dict.items()}

        # Important for determinism: never depend on dict insertion order at sampling sites.
        return tuple(sorted(result_dict.items(), key=lambda kv: repr(kv[0])))

    def get_probabilities(
        self,
        context: List[Any],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[Any, float]:
        context_tuple = tuple(context[-self.order:])
        cached = self._get_probabilities_cached(context_tuple, temperature, top_k)
        return dict(cached)

    def generate(
        self,
        seed: List[Any],
        length: int,
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> List[Any]:
   
        seq = list(seed[:length])
        for _ in range(max(0, length - len(seq))):
            nxt = self.get_next(seq[-(self.order):], temperature, top_k)
            if nxt is None:
                break
            seq.append(nxt)
        return seq
