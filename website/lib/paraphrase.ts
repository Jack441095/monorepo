// Client-side access to the paraphrase product (products/nite-paraphrase).
//
// Browser -> backend /v1/paraphrase (StreamingResponse), which proxies the
// engine service. This module owns the SSE read pattern, the anonymous
// free-tier counter, the unlock token, and the Phase 4 payment seam.
//
// The free tier is authoritative on the backend (3/day per client); the
// local counter is UX only and resets when the day changes.

import { apiFetch } from "./api";
export type Voice = "essay" | "email" | "report" | "casual";

export const VOICES: Voice[] = ["essay", "email", "report", "casual"];

export type ParaphraseStats = { tokens?: number; seconds?: number };

export type ParaphraseEvent =
  | { type: "token"; token: string }
  | { type: "alert"; message: string }
  | { type: "done"; stats?: ParaphraseStats }
  | { type: "error"; message: string };

const USAGE_KEY = "nite_paraphrase_usage_v1";
export const FREE_DAILY_LIMIT = 3;

export class ParaphraseError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// --- Free-tier usage (UX-only; backend enforces) ---

type Usage = { day: string; used: number };

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

export function readUsage(): Usage {
  if (typeof window === "undefined") return { day: todayKey(), used: 0 };
  try {
    const parsed = JSON.parse(window.localStorage.getItem(USAGE_KEY) ?? "{}") as Partial<Usage>;
    if (parsed.day === todayKey() && typeof parsed.used === "number") {
      return { day: parsed.day, used: parsed.used };
    }
  } catch {
    // corrupt/missing state — restart fresh
  }
  return { day: todayKey(), used: 0 };
}

export function recordUsage(): void {
  if (typeof window === "undefined") return;
  const next = readUsage();
  next.used = Math.min(next.used + 1, FREE_DAILY_LIMIT);
  window.localStorage.setItem(USAGE_KEY, JSON.stringify(next));
}

// --- Unlock token (set by the Phase 4 payment path) ---

const UNLOCK_KEY = "nite_paraphrase_unlock_v1";

export function readUnlockToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(UNLOCK_KEY);
}

function storeUnlockToken(token: string): void {
  window.localStorage.setItem(UNLOCK_KEY, token);
}

// Phase 4 seam: replaces this stub with a real Paddle checkout flow that
// returns an issued token (webhook delivered, then the client polls
// /v1/paraphrase/entitlement). Keep this function's signature.
export async function unlockParaphrase(
  _tier: "gbp-1" | "gbp-3" | "gbp-10",
): Promise<{ ok: true; token: string } | { ok: false; error: string }> {
  void _tier; // used by the Phase 4 Paddle catalog mapping
  const devToken = process.env.NEXT_PUBLIC_PARAPHRASE_UNLOCK_TOKEN;
  if (devToken) {
    storeUnlockToken(devToken);
    return { ok: true, token: devToken };
  }
  return { ok: false, error: "Payments open with the beta. Free rewriting stays available daily." };
}

// --- Streaming request ---

export async function* requestParaphrase(
  voice: Voice,
  text: string,
  signal?: AbortSignal,
): AsyncGenerator<ParaphraseEvent> {
  const token = readUnlockToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["X-Paraphrase-Token"] = token;

  const response = await apiFetch("/v1/paraphrase", {
    method: "POST",
    headers,
    body: JSON.stringify({ voice, text }),
    signal,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // non-JSON error body — keep the status-based message
    }
    throw new ParaphraseError(response.status, detail);
  }

  const body = response.body;
  if (!body) throw new ParaphraseError(0, "Response body unavailable.");
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function emitFrames(frame: string): ParaphraseEvent[] {
    const events: ParaphraseEvent[] = [];
    for (const line of frame.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const data = line.slice("data:".length).trim();
      if (!data) continue;
      try {
        const parsed = JSON.parse(data) as {
          type: string;
          token?: string;
          message?: string;
          stats?: ParaphraseStats;
        };
        if (parsed.type === "token" && typeof parsed.token === "string") {
          events.push({ type: "token", token: parsed.token });
        } else if (parsed.type === "alert" && typeof parsed.message === "string") {
          events.push({ type: "alert", message: parsed.message });
        } else if (parsed.type === "done") {
          events.push({ type: "done", stats: parsed.stats });
        } else if (parsed.type === "error" && typeof parsed.message === "string") {
          events.push({ type: "error", message: parsed.message });
        }
      } catch {
        // ignore malformed frames; the next chunk may complete them
      }
    }
    return events;
  }

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer)) !== null) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        for (const event of emitFrames(frame)) {
          yield event;
          if (event.type === "done" || event.type === "error") return;
        }
      }
    }
    throw new ParaphraseError(0, "Rewrite interrupted before completion. Please try again.");
  } finally {
    try {
      await reader.cancel();
    } catch {
      // An aborted or failed stream may already be closed.
    } finally {
      reader.releaseLock();
    }
  }
}