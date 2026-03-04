# Ingestion Sources Research

## Email-to-Article Ingestion and Browser Web Clipper

Researched 2026-03-04. Goal: two new content ingestion paths for the existing pipeline, both ultimately calling `import_url.py` with extracted URLs.

---

## Part 1: Email-to-Article Ingestion

### What a Forwarded Email Looks Like

When you forward an email in Gmail, Apple Mail, or Outlook, the receiving server gets a standard RFC 2822 MIME message. The forwarded original is either:

1. **Inline** — Original content is appended below a `------- Forwarded message -------` header (Gmail/Outlook styles). The original subject, from, date, to headers are repeated as text.
2. **Attachment** — Some clients attach the original as a `message/rfc822` MIME part.

For newsletter emails (the main use case), the body contains HTML with `<a href="...">` links. The article URL you want is usually in:
- The primary CTA button link (`<a href="https://example.com/article">Read more</a>`)
- `<a>` tags in the body text
- Sometimes the email IS the article (Substack, email newsletters)

For a forwarded web article URL (you just forward a "share via email" or copy-paste a URL into an email), the URL sits in plain-text body.

Key insight: **Email forwarding is not standardized**. No single RFC governs the format. The `email-forward-parser` library (JS, MIT licensed) handles Apple Mail, Gmail, Outlook Live/365, Outlook 2013/2019, Yahoo Mail, Thunderbird across multiple locales: https://github.com/crisp-oss/email-forward-parser

---

### Option A: Cloudflare Email Workers (Recommended)

**What it is**: Cloudflare's free Email Routing service lets you assign email addresses to a domain you manage through Cloudflare DNS. You write a Worker (JS/TS) that receives every inbound email as a stream, parse it, and call out to your Hetzner server.

**Prerequisites**: You need a domain pointed at Cloudflare's nameservers. Any domain works. If you already use Cloudflare for DNS (e.g., for `alifstian.duckdns.org`) you're set.

**Cost**: Free tier. Email Routing itself is free. Workers free tier gives 100,000 requests/day. For personal use this is unlimited effectively.

**Size limit**: 25 MiB per message. No per-day volume limit documented for personal use.

**How it works**:

```
Forward email to petrarca@yourdomain.com
  → Cloudflare routes to Email Worker
    → Worker parses with postal-mime
      → Worker POSTs extracted URL to https://your-hetzner:8090/ingest
        → Hetzner server runs import_url.py
```

**Worker code** (complete, production-ready):

```javascript
import PostalMime from 'postal-mime';

export default {
  async email(message, env, ctx) {
    // Parse the raw email stream
    const email = await PostalMime.parse(message.raw);

    // Try to extract URLs from the email
    const urls = extractUrls(email);

    if (urls.length === 0) {
      console.log('No URLs found in email from:', message.from);
      // Optionally forward to your real inbox anyway
      await message.forward('your-real-email@gmail.com');
      return;
    }

    // POST each URL to Hetzner ingestion endpoint
    const results = [];
    for (const url of urls) {
      try {
        const resp = await fetch('https://your-hetzner-ip:8090/ingest', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Petrarca-Token': env.INGEST_TOKEN,
          },
          body: JSON.stringify({
            url,
            source: 'email',
            sender: message.from,
            subject: email.subject || '',
          }),
        });
        results.push({ url, status: resp.status });
      } catch (err) {
        console.error('Failed to ingest:', url, err.message);
      }
    }

    console.log('Ingested:', JSON.stringify(results));
    // Forward to your real inbox so you don't lose the email
    await message.forward('your-real-email@gmail.com');
  }
};

function extractUrls(email) {
  const urls = new Set();

  // 1. Check plain text body for bare URLs
  if (email.text) {
    const urlRegex = /https?:\/\/[^\s<>"{}|\\^`[\]]+/g;
    for (const url of email.text.matchAll(urlRegex)) {
      const u = url[0].replace(/[.,;!?)]+$/, ''); // strip trailing punctuation
      if (isArticleUrl(u)) urls.add(u);
    }
  }

  // 2. Check HTML body for <a href> links
  if (email.html) {
    const hrefRegex = /href=["']([^"']+)["']/gi;
    for (const match of email.html.matchAll(hrefRegex)) {
      const u = match[1];
      if (u.startsWith('http') && isArticleUrl(u)) urls.add(u);
    }
  }

  // Prefer the most "article-like" URL — longest path, not a tracker
  return Array.from(urls)
    .filter(u => !isTrackingUrl(u))
    .sort((a, b) => b.length - a.length)
    .slice(0, 3); // max 3 URLs per email
}

function isArticleUrl(url) {
  try {
    const u = new URL(url);
    // Skip images, CDN assets, tracking pixels
    if (/\.(png|jpg|gif|webp|ico|css|js|woff)(\?|$)/i.test(u.pathname)) return false;
    if (u.pathname === '/' || u.pathname === '') return false;
    return true;
  } catch { return false; }
}

function isTrackingUrl(url) {
  const trackingDomains = [
    'click.', 'track.', 'link.', 'email.', 'mg.', 'mailchi.mp',
    'mailchimp.com', 'sendgrid.net', 'mandrillapp.com',
    'list-manage.com', 'hubspot.', 'marketo.',
  ];
  return trackingDomains.some(d => url.includes(d));
}
```

**Setup steps**:
1. Add domain to Cloudflare (or use existing)
2. Enable Email Routing in Cloudflare dashboard → Email → Email Routing
3. Create Worker: `npm create cloudflare@latest petrarca-email-worker`
4. Install postal-mime: `npm install postal-mime`
5. In wrangler.toml: `[vars] INGEST_TOKEN = "your-secret-token"`
6. Route: Dashboard → Email → Email Workers → Create address `petrarca@yourdomain.com` → Send to Worker

**Tradeoffs**:
- Pro: Zero infrastructure to manage, totally free, reliable delivery
- Pro: Your Hetzner server doesn't need to run an SMTP service (no MX records, no port 25)
- Con: Requires a domain on Cloudflare DNS (not a raw IP)
- Con: Worker runs in JS/TS, not Python — but it's just a thin relay; all logic stays in Python on Hetzner

---

### Option B: Self-Hosted Postfix + Python Script (Simplest if you already have a domain with MX)

**What it is**: Install Postfix on Hetzner, point MX records for a domain at the server, configure Postfix to pipe emails for one address to a Python script via `master.cf`.

**Cost**: Free. Postfix is already on most Linux servers.

**The catch**: Port 25 (SMTP) is often blocked by cloud providers for new VMs due to spam concerns. Hetzner blocks port 25 by default on new servers. You need to request unblocking from Hetzner support, which they do grant for legitimate uses but requires a ticket.

**Config** (`/etc/postfix/master.cf`):

```
petrarca-ingest  unix  -  n  n  -  10  pipe
  flags=Rq user=petrarca null_sender=
  argv=/opt/petrarca/scripts/email_ingest.py -f ${sender} -t ${recipient}
```

`/etc/postfix/transport`:
```
yourdomain.com  petrarca-ingest:
```

`/etc/postfix/main.cf` addition:
```
transport_maps = hash:/etc/postfix/transport
```

**Python handler** (`/opt/petrarca/scripts/email_ingest.py`):

```python
#!/usr/bin/env python3
"""Postfix pipe handler: parse inbound email, extract URLs, call import_url.py."""
import argparse
import email
import re
import subprocess
import sys
from email import policy
from html.parser import HTMLParser
from pathlib import Path

PETRARCA_DIR = Path('/opt/petrarca')
VENV_PYTHON = PETRARCA_DIR / '.venv/bin/python3'
IMPORT_URL = PETRARCA_DIR / 'scripts/import_url.py'
LOG_FILE = PETRARCA_DIR / 'logs/email-ingest.log'

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr, val in attrs:
                if attr == 'href' and val and val.startswith('http'):
                    self.links.append(val)

def extract_urls(msg):
    urls = set()
    url_regex = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

    for part in msg.walk():
        ct = part.get_content_type()
        if ct == 'text/plain':
            text = part.get_payload(decode=True).decode('utf-8', errors='replace')
            for m in url_regex.finditer(text):
                u = m.group(0).rstrip('.,;!?)')
                urls.add(u)
        elif ct == 'text/html':
            html = part.get_payload(decode=True).decode('utf-8', errors='replace')
            parser = LinkExtractor()
            parser.feed(html)
            urls.update(parser.links)

    return [u for u in urls if is_article_url(u) and not is_tracking_url(u)]

def is_article_url(url):
    skip_exts = ('.png', '.jpg', '.gif', '.webp', '.ico', '.css', '.js')
    return not any(url.lower().split('?')[0].endswith(e) for e in skip_exts)

def is_tracking_url(url):
    trackers = ['click.', 'track.', 'mailchi.mp', 'sendgrid.net', 'list-manage.com']
    return any(t in url for t in trackers)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--from', dest='sender')
    parser.add_argument('-t', '--to', dest='recipient')
    args = parser.parse_args()

    raw = sys.stdin.buffer.read()
    msg = email.message_from_bytes(raw, policy=policy.default)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    subject = msg.get('subject', '(no subject)')

    urls = extract_urls(msg)

    with open(LOG_FILE, 'a') as log:
        log.write(f"FROM={args.sender} SUBJECT={subject!r} URLS={urls}\n")

    if not urls:
        sys.exit(0)

    # Call import_url.py for each URL
    for url in urls[:3]:
        result = subprocess.run(
            [str(VENV_PYTHON), str(IMPORT_URL), url, '--tag', 'manual'],
            capture_output=True, text=True, cwd=str(PETRARCA_DIR)
        )
        with open(LOG_FILE, 'a') as log:
            log.write(f"  import_url({url}): rc={result.returncode}\n")
            if result.stderr:
                log.write(f"  stderr: {result.stderr[:500]}\n")

    sys.exit(0)

if __name__ == '__main__':
    main()
```

**Tradeoffs**:
- Pro: Pure self-hosted, no external services
- Pro: Direct Python, no JS wrapper
- Con: Port 25 blocked by Hetzner by default (need support ticket)
- Con: Running a mail server means dealing with SPF/DKIM, spam filtering, TLS — nontrivial even for a single address
- Con: More maintenance than Cloudflare option

---

### Option C: Mailgun Inbound Routing

**What it is**: Create a free Mailgun account, add your domain, configure an inbound route that POSTs parsed email JSON to your Hetzner server.

**Cost**: Free tier exists but Mailgun now requires credit card and has limited free tier (100 emails/day for outbound; inbound routing requires "Foundation" plan starting at ~$35/month as of 2025). Not recommended for personal use.

**Verdict**: Skip. Cloudflare Email Workers is free and simpler.

---

### Newsletter-as-Article: The Substack Case

Some newsletters (Substack, Buttondown, Ghost) have web archive URLs for every issue. If you subscribe and get newsletter emails, the forwarded email contains a "View in browser" link pointing to the actual web page — that URL feeds directly into `import_url.py` and the existing pipeline handles it perfectly. No special parsing needed beyond finding that link.

---

### Recommendation for Petrarca

**Use Cloudflare Email Workers** if you have any domain on Cloudflare DNS (even a cheap one). It's:
- Free
- Zero maintenance
- No port 25 hassle
- 3-file implementation (worker.js, wrangler.toml, ingest endpoint in research-server.py)

The only thing needed on the Hetzner side is a new `/ingest` endpoint in `research-server.py` that receives `{url, source, sender, subject}` and calls `import_url.py` as a subprocess — exactly the pattern already used for research agents.

---

## Part 2: Browser Web Clipper Chrome Extension

### Existing Open Source Options Studied

**Omnivore** (https://github.com/omnivore-app/omnivore): The extension lives in `pkg/extension/`. It's built with webpack and uses an API key sent to their GraphQL endpoint. The whole app is AGPL-3.0 and self-hostable. Since Omnivore shut down their cloud in Nov 2024, the extension was repurposed for self-hosted instances. The extension is likely the most mature codebase to study — but it's feature-heavy (full-text extraction in the browser, labels, notes). Overkill to adapt.

**Wallabagger** (https://github.com/nicowillis/wallabagger): Sends `POST /api/entries` with `{url, title, tags}` to a Wallabag instance. Simple. Open source. Worth studying the manifest.json and popup UI pattern.

**Linkding extension** (https://github.com/sissbruecker/linkding-extension): Minimal extension for a self-hosted bookmark manager. Manifest V3 compatible. Saves via `POST /api/bookmarks/` with `{url, title, tag_names[]}`. The cleanest minimal example. The `LinkdingApi` class in `src/linkding.js` is ~50 lines.

### Building a Minimal Petrarca Clipper

A Chrome extension to save the current page to Petrarca is 3 files:

**`manifest.json`**:
```json
{
  "manifest_version": 3,
  "name": "Petrarca Clipper",
  "version": "1.0",
  "description": "Save current page to Petrarca",
  "permissions": ["activeTab", "storage"],
  "host_permissions": ["https://your-hetzner-ip/*"],
  "action": {
    "default_popup": "popup.html",
    "default_icon": "icon.png"
  }
}
```

**`popup.html`**:
```html
<!DOCTYPE html>
<html>
<head>
  <style>
    body { width: 280px; padding: 12px; font-family: system-ui; }
    button { width: 100%; padding: 8px; background: #7c3aed; color: white;
             border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
    button:disabled { opacity: 0.5; }
    #status { margin-top: 8px; font-size: 12px; color: #666; }
    #url { font-size: 11px; color: #999; margin-bottom: 8px;
           overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  </style>
</head>
<body>
  <div id="url"></div>
  <button id="save">Save to Petrarca</button>
  <div id="status"></div>
  <script src="popup.js"></script>
</body>
</html>
```

**`popup.js`**:
```javascript
const SERVER = 'https://your-hetzner-ip:8090';
const TOKEN = 'your-secret-token'; // load from chrome.storage in production

async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

document.addEventListener('DOMContentLoaded', async () => {
  const tab = await getCurrentTab();
  document.getElementById('url').textContent = tab.url;

  document.getElementById('save').addEventListener('click', async () => {
    const btn = document.getElementById('save');
    const status = document.getElementById('status');

    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
      const resp = await fetch(`${SERVER}/ingest`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Petrarca-Token': TOKEN,
        },
        body: JSON.stringify({
          url: tab.url,
          title: tab.title,
          source: 'clipper',
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        btn.textContent = 'Saved!';
        btn.style.background = '#059669';
        status.textContent = `Queued: ${tab.url.slice(0, 50)}...`;
      } else {
        throw new Error(`Server returned ${resp.status}`);
      }
    } catch (err) {
      btn.textContent = 'Save to Petrarca';
      btn.disabled = false;
      status.textContent = `Error: ${err.message}`;
      status.style.color = '#dc2626';
    }
  });
});
```

**To load unpacked in Chrome**: `chrome://extensions` → Developer mode → Load unpacked → select the folder.

No Chrome Web Store submission needed for personal use. Works immediately.

### The `/ingest` Endpoint

Add to `research-server.py`:

```python
def do_POST(self):
    if self.path == '/ingest':
        # Verify token
        token = self.headers.get('X-Petrarca-Token', '')
        if token != os.environ.get('PETRARCA_INGEST_TOKEN', ''):
            self.send_error(401, 'Unauthorized')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        url = body.get('url', '').strip()
        source = body.get('source', 'clipper')

        if not url or not url.startswith('http'):
            self.send_error(400, 'Missing or invalid url')
            return

        # Spawn import_url.py in background thread
        request_id = f'ingest_{int(time.time())}'

        def run_import():
            import subprocess
            result = subprocess.run(
                ['/opt/petrarca/.venv/bin/python3',
                 '/opt/petrarca/scripts/import_url.py',
                 url, '--tag', 'manual'],
                capture_output=True, text=True,
                cwd='/opt/petrarca'
            )
            print(f'[ingest] {request_id} rc={result.returncode} url={url[:60]}')

        thread = threading.Thread(target=run_import, daemon=True)
        thread.start()

        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'id': request_id,
            'status': 'queued',
            'url': url,
        }).encode())
        return

    # ... existing routes
```

### HTTPS on Port 8090

The clipper extension needs HTTPS to talk to the server from a web context. Options:
1. **Nginx reverse proxy with Let's Encrypt** on the Hetzner VM — run Certbot, get a cert for your domain, proxy `https://yourdomain.com:8091` → `localhost:8090`. Most robust.
2. **Self-signed cert** — works for the unpacked extension but you have to click through cert warnings. Fine for personal use.
3. **Cloudflare Tunnel** (`cloudflared`) — zero-config HTTPS tunnel from Cloudflare's edge to localhost. Free. Creates a `*.trycloudflare.com` subdomain or uses your domain.

For a personal tool, Cloudflare Tunnel is the simplest: install `cloudflared`, run `cloudflared tunnel --url http://localhost:8090`, add the resulting URL to the extension. Persistent tunnel can be set up as a systemd service.

---

## Summary: Recommended Implementation Path

### Email ingestion (Cloudflare Email Workers)
1. Add a domain to Cloudflare (or use existing)
2. Enable Email Routing → create `petrarca@yourdomain.com`
3. Write Worker (see code above), deploy with `wrangler deploy`
4. Add `/ingest` endpoint to `research-server.py`
5. Add `PETRARCA_INGEST_TOKEN` to `/opt/petrarca/.env`
6. Test: forward any newsletter to `petrarca@yourdomain.com`

Total new code: ~80 lines JS (worker) + ~30 lines Python (endpoint).

### Chrome extension (unpacked, no store)
1. Create 3 files: `manifest.json`, `popup.html`, `popup.js`
2. Set up HTTPS on server (Cloudflare Tunnel is easiest)
3. Add `/ingest` endpoint to `research-server.py`
4. Load unpacked in Chrome

Total new code: ~60 lines HTML/JS + ~30 lines Python (same endpoint as email).

Both paths share the same `/ingest` server endpoint. The server endpoint is the same pattern as the existing research agent spawn — background thread, `subprocess.run(import_url.py)`.

### What happens after ingestion
The URL goes through the existing pipeline unchanged:
1. `import_url.py` → `fetch_article()` → `_process_with_llm()` → saves to `data/articles.json`
2. `update_manifest()` bumps the hash
3. App syncs on next launch, article appears in Feed

No new pipeline code needed — the ingestion sources just become new entry points to the existing `import_url.py` CLI.
