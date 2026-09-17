import { expect, test } from "@playwright/test";
import { requestParaphrase } from "../../lib/paraphrase";

const originalFetch = globalThis.fetch;
test.afterEach(() => { globalThis.fetch = originalFetch; });

function mockStream(text: string, close = true) {
  let cancelled = false;
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      // Split every byte, including multibyte UTF-8 and CRLF boundaries.
      for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
      if (close) controller.close();
    },
    cancel() { cancelled = true; },
  });
  globalThis.fetch = async () => new Response(body);
  return { body, cancelled: () => cancelled };
}

async function collect(signal?: AbortSignal) {
  const events = [];
  for await (const event of requestParaphrase("essay", "Draft", signal)) events.push(event);
  return events;
}

test("handles split UTF-8 and CRLF frames; stops at done", async () => {
  const stream = mockStream('data: {"type":"token","token":"café"}\r\n\r\ndata: {"type":"done"}\r\n\r\n', false);
  expect(await collect()).toEqual([{ type: "token", token: "café" }, { type: "done", stats: undefined }]);
  expect(stream.cancelled()).toBe(true);
  expect(stream.body.locked).toBe(false);
});

test("rejects premature EOF rather than reporting success", async () => {
  const stream = mockStream('data: {"type":"token","token":"partial"}\n\n');
  await expect(collect()).rejects.toThrow("Rewrite interrupted before completion");
  expect(stream.body.locked).toBe(false);
});

test("does not accept an unterminated completion frame", async () => {
  mockStream('data: {"type":"done"}');
  await expect(collect()).rejects.toThrow("Rewrite interrupted");
});

test("engine error ends and cancels the stream", async () => {
  const stream = mockStream('data: {"type":"error","message":"Unavailable"}\n\n', false);
  expect(await collect()).toEqual([{ type: "error", message: "Unavailable" }]);
  expect(stream.cancelled()).toBe(true);
});

test("consumer exiting early cancels and unlocks the reader", async () => {
  const stream = mockStream('data: {"type":"token","token":"partial"}\n\n', false);
  const events = requestParaphrase("essay", "Draft");
  await events.next();
  await events.return(undefined);
  expect(stream.cancelled()).toBe(true);
  expect(stream.body.locked).toBe(false);
});

test("passes cancellation to the pending fetch", async () => {
  const controller = new AbortController();
  let received: AbortSignal | null | undefined;
  globalThis.fetch = async (_url, init) => {
    received = init?.signal;
    return new Promise<Response>((_resolve, reject) => {
      received?.addEventListener("abort", () => reject(received?.reason), { once: true });
    });
  };
  const result = collect(controller.signal);
  expect(received).toBe(controller.signal);
  controller.abort();
  await expect(result).rejects.toMatchObject({ name: "AbortError" });
});
