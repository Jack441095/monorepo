import { expect, test } from "@playwright/test";
import { parseWaitlistJoin } from "../../lib/waitlist";
import { POST } from "../../app/api/waitlist/join/route";

test("normalizes a waitlist address and trims optional fields", () => {
  expect(parseWaitlistJoin({ email: " Buyer@Example.com ", product_id: " submit ", name: " Buyer ", use_case: " " }))
    .toEqual({ email: "buyer@example.com", product_id: "submit", name: "Buyer", use_case: null });
});

test("accepts omitted optional fields and each current product slug", () => {
  for (const product_id of ["submit", "kenn", "smart-sample-manager"]) {
    expect(parseWaitlistJoin({ email: "buyer@example.com", product_id }))
      .toEqual({ email: "buyer@example.com", product_id, name: null, use_case: null });
  }
});

test("rejects malformed or oversized fields before accessing the database", async () => {
  for (const body of [null, [], "text", {}, { email: {}, product_id: "submit" },
    { email: "invalid", product_id: "submit" }, { email: "a@@example.com", product_id: "submit" },
    { email: "a@example.com", product_id: 4 }, { email: "a@example.com", product_id: "../submit" },
    { email: "a@example.com", product_id: "submit", name: {} },
    { email: "a@example.com", product_id: "submit", name: "x".repeat(101) },
    { email: "a@example.com", product_id: "submit", use_case: "x".repeat(1001) },
    { email: `${"x".repeat(255)}@example.com`, product_id: "submit" }]) {
    expect(parseWaitlistJoin(body)).toBeNull();
    const response = await POST(new Request("https://nite.example/api/waitlist/join", {
      method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
    }));
    expect(response.status).toBe(400);
  }
});

test("rejects invalid JSON with a client error", async () => {
  // Invalid JSON used to escape the handler and become a server error.
  const response = await POST(new Request("https://nite.example/api/waitlist/join", {
    method: "POST", body: "{broken", headers: { "Content-Type": "application/json" },
  }));
  expect(response.status).toBe(400);
});
