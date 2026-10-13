import assert from "node:assert/strict";
import test from "node:test";

import worker from "./staging-api-worker.mjs";

test("forwards Stripe webhook bytes and signature to the staging origin without caching", async (t) => {
  const originalFetch = globalThis.fetch;
  let forwardedRequest;
  let fetchOptions;
  globalThis.fetch = async (request, options) => {
    forwardedRequest = request;
    fetchOptions = options;
    return new Response("accepted", { status: 202 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const body = '{"type":"checkout.session.completed"}';
  const request = new Request(
    "https://worker.example/webhooks/stripe?source=test",
    {
      method: "POST",
      headers: { "Stripe-Signature": "t=123,v1=signature" },
      body,
    },
  );

  const response = await worker.fetch(request, {
    STAGING_API_ORIGIN: "https://origin.example",
  });

  assert.equal(forwardedRequest.url, "https://origin.example/webhooks/stripe?source=test");
  assert.equal(forwardedRequest.method, "POST");
  assert.equal(forwardedRequest.headers.get("Stripe-Signature"), "t=123,v1=signature");
  assert.equal(await forwardedRequest.text(), body);
  assert.deepEqual(fetchOptions, { cf: { cacheTtl: 0 } });
  assert.equal(response.status, 202);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("keeps double-slash paths on the staging host and preserves API errors", async (t) => {
  const originalFetch = globalThis.fetch;
  let forwardedRequest;
  globalThis.fetch = async (request) => {
    forwardedRequest = request;
    return new Response('{"detail":"Unauthorized"}', {
      status: 401,
      headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=60" },
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const response = await worker.fetch(new Request("https://worker.example//other.example/admin"), {
    STAGING_API_ORIGIN: "https://origin.example",
  });

  assert.equal(forwardedRequest.url, "https://origin.example//other.example/admin");
  assert.equal(forwardedRequest.method, "GET");
  assert.equal(forwardedRequest.body, null);
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("Content-Type"), "application/json");
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal(await response.text(), '{"detail":"Unauthorized"}');
});
