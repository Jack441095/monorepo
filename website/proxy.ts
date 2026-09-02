import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Phase 5 access control for /portfolio (docs/NITE_DSP_PORTFOLIO_READINESS_AUDIT_V1.md).
//
// /portfolio is an unlisted, employer-facing CV page — not a public product
// surface. It already has no nav link, no sitemap entry, and a robots
// disallow (see app/robots.ts), but none of that stops someone who has the
// direct URL. This adds one real gate: HTTP Basic Auth behind a single
// shared password, checked here at the edge before the route ever renders.
//
// Fails CLOSED by design, matching this codebase's existing security
// posture elsewhere (Paddle webhook verification, licensing signing key) —
// if PORTFOLIO_PASSWORD isn't configured in the environment, /portfolio is
// blocked entirely rather than left open. Set it in Railway's website
// service variables (not committed anywhere) to unlock the page.
const REALM = "NITE DSP Portfolio";

function unauthorized(): NextResponse {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"` },
  });
}

export function proxy(request: NextRequest): NextResponse {
  const configuredPassword = process.env.PORTFOLIO_PASSWORD;

  // No password configured anywhere in this environment — fail closed,
  // not open. A misconfigured deploy should never mean an unlocked page.
  if (!configuredPassword) {
    return new NextResponse("Portfolio access is not configured.", { status: 403 });
  }

  const authHeader = request.headers.get("authorization");
  if (!authHeader?.startsWith("Basic ")) {
    return unauthorized();
  }

  let decoded: string;
  try {
    decoded = atob(authHeader.slice("Basic ".length));
  } catch {
    return unauthorized();
  }

  // Username is unchecked on purpose — this is a single shared password
  // for a small, known audience (employers/collaborators Jack invites
  // directly), not a multi-user account system. Only the password after
  // the first colon needs to match.
  const separatorIndex = decoded.indexOf(":");
  const suppliedPassword = separatorIndex === -1 ? decoded : decoded.slice(separatorIndex + 1);

  if (suppliedPassword !== configuredPassword) {
    return unauthorized();
  }

  return NextResponse.next();
}

export default proxy;
export const middleware = proxy;

export const config = {
  matcher: ["/portfolio", "/portfolio/:path*"],
};

