/**
 * Petrarca Email Ingest — Cloudflare Email Worker
 *
 * Dumb pipe: receives email, forwards raw MIME text to the server
 * for processing. All smart parsing happens server-side in Python.
 *
 * Environment variables (set in Cloudflare worker settings):
 *   PETRARCA_INGEST_URL   — e.g. "http://alifstian.duckdns.org:8090"
 *   PETRARCA_INGEST_TOKEN — shared secret auth token
 */

export default {
  async email(message, env, ctx) {
    const from = message.from;
    const to = message.to;
    console.log(`[email] Received from ${from} to ${to}`);

    const raw = await new Response(message.raw).text();
    console.log(`[email] Raw email: ${raw.length} bytes`);

    const base = (env.PETRARCA_INGEST_URL || "").replace(/\/+$/, "");
    if (!base) {
      console.error("[email] PETRARCA_INGEST_URL not set");
      return;
    }

    const headers = {
      "Content-Type": "text/plain",
      "X-From": from,
      "X-To": to,
    };
    if (env.PETRARCA_INGEST_TOKEN) {
      headers["X-Petrarca-Token"] = env.PETRARCA_INGEST_TOKEN;
    }

    ctx.waitUntil(
      fetch(`${base}/ingest-email`, {
        method: "POST",
        headers,
        body: raw,
      })
        .then((r) => console.log(`[email] Server responded: ${r.status}`))
        .catch((e) => console.error(`[email] Server error: ${e.message}`))
    );
  },
};
