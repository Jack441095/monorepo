export default {
  async fetch(request, env) {
    const incomingUrl = new URL(request.url);
    const upstreamUrl = new URL(env.STAGING_API_ORIGIN);
    // Assign the path rather than resolve it: a path beginning // must never
    // replace the configured host and turn this Worker into an open proxy.
    upstreamUrl.pathname = incomingUrl.pathname;
    upstreamUrl.search = incomingUrl.search;

    // Stripe signs the exact webhook bytes, so the proxy must carry the original request body and headers untouched.
    const upstreamResponse = await fetch(new Request(upstreamUrl, request), {
      cf: { cacheTtl: 0 },
    });

    // Checkout and download responses can contain customer-specific data; never let an edge cache retain them.
    const headers = new Headers(upstreamResponse.headers);
    headers.set("Cache-Control", "no-store");
    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers,
    });
  },
};
