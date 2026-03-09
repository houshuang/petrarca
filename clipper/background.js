// Petrarca Clipper — Background Service Worker
// Handles badge state and message routing between popup and content scripts.

const SERVER_DEFAULT = "http://alifstian.duckdns.org:8090";

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
