// Petrarca Clipper — Background Service Worker
// Handles badge state, message routing, and Twitter cookie sync.

const SERVER_DEFAULT = "http://alifstian.duckdns.org:8090";
const COOKIE_SYNC_INTERVAL_MS = 4 * 60 * 60 * 1000; // 4 hours

// Listen for messages from popup or content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "saveClip") {
    handleSave(message.payload)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // keep channel open for async
  }

  if (message.type === "setBadge") {
    chrome.action.setBadgeText({ text: message.text || "" });
    chrome.action.setBadgeBackgroundColor({ color: "#8b2500" });
    sendResponse({ ok: true });
  }

  if (message.type === "clearBadge") {
    chrome.action.setBadgeText({ text: "" });
    sendResponse({ ok: true });
  }
});

async function handleSave(payload) {
  const settings = await loadSettings();
  const serverUrl = (settings.serverUrl || SERVER_DEFAULT).replace(/\/+$/, "");
  const authToken = settings.authToken || "";

  const headers = { "Content-Type": "application/json" };
  if (authToken) {
    headers["X-Petrarca-Token"] = authToken;
  }

  const response = await fetch(`${serverUrl}/ingest`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text.slice(0, 200)}`);
  }

  return { ok: true };
}

function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      ["petrarca_server_url", "petrarca_auth_token"],
      (result) => {
        resolve({
          serverUrl: result.petrarca_server_url || "",
          authToken: result.petrarca_auth_token || "",
        });
      }
    );
  });
}

// ---------------------------------------------------------------------------
// Twitter/X cookie auto-sync
// ---------------------------------------------------------------------------

async function maybeSyncTwitterCookies(tabUrl) {
  // Only trigger on twitter.com / x.com
  if (!tabUrl || (!tabUrl.includes("x.com") && !tabUrl.includes("twitter.com"))) {
    return;
  }

  // Throttle: check last sync time
  const { petrarca_last_cookie_sync } = await chrome.storage.local.get(
    "petrarca_last_cookie_sync"
  );
  const now = Date.now();
  if (petrarca_last_cookie_sync && now - petrarca_last_cookie_sync < COOKIE_SYNC_INTERVAL_MS) {
    return;
  }

  // Extract auth_token and ct0 cookies (try x.com first, then twitter.com)
  let authCookie = await chrome.cookies.get({ url: "https://x.com", name: "auth_token" });
  let ct0Cookie = await chrome.cookies.get({ url: "https://x.com", name: "ct0" });

  if (!authCookie || !ct0Cookie) {
    authCookie = await chrome.cookies.get({ url: "https://twitter.com", name: "auth_token" });
    ct0Cookie = await chrome.cookies.get({ url: "https://twitter.com", name: "ct0" });
  }

  if (!authCookie || !ct0Cookie) {
    console.log("[petrarca] No Twitter cookies found");
    return;
  }

  // Push to server
  const settings = await loadSettings();
  const serverUrl = (settings.serverUrl || SERVER_DEFAULT).replace(/\/+$/, "");
  const authToken = settings.authToken || "";

  try {
    const headers = { "Content-Type": "application/json" };
    if (authToken) {
      headers["X-Petrarca-Token"] = authToken;
    }

    const resp = await fetch(`${serverUrl}/twitter/cookies`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        auth_token: authCookie.value,
        ct0: ct0Cookie.value,
      }),
    });

    if (resp.ok) {
      await chrome.storage.local.set({ petrarca_last_cookie_sync: now });
      console.log("[petrarca] Twitter cookies synced to server");
    } else {
      console.log(`[petrarca] Cookie sync failed: ${resp.status}`);
    }
  } catch (err) {
    console.log(`[petrarca] Cookie sync error: ${err.message}`);
  }
}

// Trigger on tab updates (navigating to X/Twitter)
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url) {
    maybeSyncTwitterCookies(tab.url);
  }
});
