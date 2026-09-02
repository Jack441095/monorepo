import { NextResponse } from "next/server";

const MAX_BODY_BYTES = 16_384;

function serviceUrl(): string {
  return (process.env.KENN_CHAT_SERVICE_URL || "").trim().replace(/\/$/, "");
}

export async function POST(request: Request) {
  const upstream = serviceUrl();
  if (!upstream) {
    return NextResponse.json(
      {
        error: "KENN chat is not configured for this deployment.",
        scope: "mix_advice_only",
      },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    const raw = await request.arrayBuffer();
    if (raw.byteLength > MAX_BODY_BYTES) {
      return NextResponse.json({ error: "Request is too large." }, { status: 413 });
    }
    body = JSON.parse(new TextDecoder().decode(raw));
  } catch {
    return NextResponse.json({ error: "Request must be valid JSON." }, { status: 400 });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35_000);
  try {
    const response = await fetch(`${upstream}/kenn/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error && error.name === "AbortError"
      ? "KENN took too long to answer."
      : "KENN chat could not be reached.";
    return NextResponse.json({ error: message }, { status: 504 });
  } finally {
    clearTimeout(timeout);
  }
}
