// Petrarca Clipper — Popup script with auto-save countdown

(function () {
  "use strict";

  const DEFAULT_SERVER = "http://alifstian.duckdns.org:8090";
  const COUNTDOWN_MS = 10000;

  // DOM refs
  const pageTitle = document.getElementById("page-title");
  const pageUrl = document.getElementById("page-url");
  const selectionBox = document.getElementById("selection-box");
  const selectedTextEl = document.getElementById("selected-text");
  const topicTags = document.getElementById("topic-tags");
  const tagsList = document.getElementById("tags-list");
  const commentEl = document.getElementById("comment");
  const saveBtn = document.getElementById("save-btn");
  const btnLabel = document.getElementById("btn-label");
  const btnCheck = document.getElementById("btn-check");
  const statusEl = document.getElementById("status");
  const cancelBtn = document.getElementById("cancel-btn");
  const countdownStatus = document.getElementById("countdown-status");
  const countdownNum = document.getElementById("countdown-num");
  const timerThick = document.getElementById("timer-thick");
  const timerThin = document.getElementById("timer-thin");
  const settingsToggle = document.getElementById("settings-toggle");
  const settingsBack = document.getElementById("settings-back");
  const clipView = document.getElementById("clip-view");
  const settingsView = document.getElementById("settings-view");
  const serverUrlInput = document.getElementById("server-url");
  const authTokenInput = document.getElementById("auth-token");
  const saveSettingsBtn = document.getElementById("save-settings-btn");
  const settingsStatus = document.getElementById("settings-status");

  let pageData = null;
  let saving = false;

  // --- Countdown state ---------------------------------------------------

  let state = "counting"; // 'counting' | 'paused' | 'saving' | 'saved'
  let timerStart = null;
  let elapsedBeforePause = 0;
  let rafId = null;

  function startCountdown() {
    state = "counting";
    timerStart = performance.now();
    tick();
  }

  function tick() {
    const now = performance.now();
    const totalElapsed = elapsedBeforePause + (now - timerStart);
    const remaining = Math.max(0, COUNTDOWN_MS - totalElapsed);
    const progress = remaining / COUNTDOWN_MS;

    // Update timer bars
    const pct = (progress * 100).toFixed(1) + "%";
    timerThick.style.width = pct;
    timerThin.style.width = pct;

    // Update number
    const secs = Math.ceil(remaining / 1000);
    countdownNum.textContent = secs;

    if (remaining <= 0) {
      doSave();
      return;
    }

    rafId = requestAnimationFrame(tick);
  }

  function pauseCountdown() {
    if (state !== "counting") return;
    state = "paused";
    elapsedBeforePause += performance.now() - timerStart;
    cancelAnimationFrame(rafId);

    // Visual: freeze timer in muted color
    timerThick.classList.add("paused");
    timerThin.classList.add("paused");
    countdownNum.classList.add("paused");

    // Update status text
    countdownStatus.textContent = "paused";
    btnLabel.textContent = "Save with Note";
  }

  function showSavedState() {
    state = "saved";
    cancelAnimationFrame(rafId);

    // Gold completion flash on double rule
    timerThick.classList.remove("paused");
    timerThin.classList.remove("paused");
    timerThick.classList.add("gold");
    timerThin.classList.add("gold");

    countdownNum.classList.add("hidden");
    countdownStatus.textContent = "";

    saveBtn.classList.add("success");
    btnLabel.classList.add("hidden");
    btnCheck.classList.remove("hidden");
    cancelBtn.classList.add("hidden");
  }

  // --- Pause triggers: typing in note field ------------------------------

  commentEl.addEventListener("input", () => {
    pauseCountdown();
    commentEl.classList.add("active");
  });

  commentEl.addEventListener("focus", () => {
    commentEl.classList.add("active");
    // Only pause if they actually type (handled by input event)
  });

  // --- Cancel ------------------------------------------------------------

  cancelBtn.addEventListener("click", () => {
    cancelAnimationFrame(rafId);
    window.close();
  });

  // --- Init --------------------------------------------------------------

  init();

  async function init() {
    const settings = await loadSettings();
    serverUrlInput.value = settings.serverUrl || DEFAULT_SERVER;
    authTokenInput.value = settings.authToken || "";

    try {
      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });
      if (tab && tab.id) {
        pageTitle.textContent = tab.title || "Untitled";
        pageUrl.textContent = cleanUrl(tab.url || "");
        pageUrl.title = tab.url || "";

        chrome.tabs.sendMessage(
          tab.id,
          { type: "getPageData" },
          (response) => {
            if (chrome.runtime.lastError) {
              pageData = {
                title: tab.title || "",
                url: tab.url || "",
                content: "",
                selectedText: "",
              };
              startCountdown();
              return;
            }
            if (response) {
              pageData = response;
              pageTitle.textContent =
                response.title || tab.title || "Untitled";
              pageUrl.textContent = cleanUrl(
                response.url || tab.url || ""
              );
              pageUrl.title = response.url || tab.url || "";

              if (response.selectedText) {
                selectedTextEl.textContent = response.selectedText;
                selectionBox.classList.remove("hidden");
              }

              if (response.topics && response.topics.length > 0) {
                tagsList.textContent = response.topics.join("  \u00b7  ");
                topicTags.classList.remove("hidden");
              }
            }
            startCountdown();
          }
        );
      }
    } catch (err) {
      pageTitle.textContent = "Could not read page";
      startCountdown();
    }

    chrome.runtime.sendMessage({ type: "clearBadge" });
  }

  // --- Keyboard shortcuts ------------------------------------------------

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      const inSettings = !settingsView.classList.contains("hidden");
      if (inSettings) {
        e.preventDefault();
        saveSettingsBtn.click();
        return;
      }
      e.preventDefault();
      doSave();
    }

    if (e.key === "Escape") {
      cancelAnimationFrame(rafId);
      window.close();
    }
  });

  // --- Settings ----------------------------------------------------------

  settingsToggle.addEventListener("click", () => {
    pauseCountdown();
    clipView.classList.add("hidden");
    settingsView.classList.remove("hidden");
  });

  settingsBack.addEventListener("click", () => {
    settingsView.classList.add("hidden");
    clipView.classList.remove("hidden");
  });

  saveSettingsBtn.addEventListener("click", async () => {
    const serverUrl = serverUrlInput.value.trim().replace(/\/+$/, "");
    const authToken = authTokenInput.value.trim();

    await chrome.storage.sync.set({
      petrarca_server_url: serverUrl,
      petrarca_auth_token: authToken,
    });

    showStatus(settingsStatus, "Saved \u2713", "success");
    setTimeout(() => settingsStatus.classList.add("hidden"), 2000);
  });

  // --- Save --------------------------------------------------------------

  saveBtn.addEventListener("click", doSave);

  async function doSave() {
    if (!pageData || saving) return;
    saving = true;
    state = "saving";
    cancelAnimationFrame(rafId);

    const settings = await loadSettings();
    const serverUrl = (settings.serverUrl || DEFAULT_SERVER).replace(
      /\/+$/,
      ""
    );
    const authToken = settings.authToken || "";

    const payload = {
      url: pageData.url,
      title: pageData.title,
      content: pageData.content || "",
      selected_text: pageData.selectedText || "",
      comment: commentEl.value.trim(),
      source: "clipper",
    };

    saveBtn.disabled = true;
    btnLabel.textContent = "Saving\u2026";
    countdownStatus.textContent = "";
    statusEl.classList.add("hidden");

    try {
      const headers = { "Content-Type": "application/json" };
      if (authToken) {
        headers["X-Petrarca-Token"] = authToken;
      }

      const response = await fetch(`${serverUrl}/ingest`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        showSavedState();
        setTimeout(() => window.close(), 1200);
      } else {
        const text = await response.text();
        showStatus(
          statusEl,
          `Error ${response.status}: ${text.slice(0, 100)}`,
          "error"
        );
        resetSaveBtn();
      }
    } catch (err) {
      try {
        await storeLocally(payload);
        showStatus(
          statusEl,
          "Server unavailable \u2014 saved locally",
          "info"
        );
        showSavedState();
        setTimeout(() => window.close(), 1800);
      } catch (storageErr) {
        showStatus(statusEl, `Failed: ${err.message}`, "error");
        resetSaveBtn();
      }
    }
  }

  function resetSaveBtn() {
    saveBtn.disabled = false;
    btnLabel.textContent = state === "paused" ? "Save with Note" : "Save";
    btnLabel.classList.remove("hidden");
    btnCheck.classList.add("hidden");
    saving = false;
  }

  async function storeLocally(payload) {
    const result = await chrome.storage.local.get(["petrarca_queue"]);
    const queue = result.petrarca_queue || [];
    queue.push({
      ...payload,
      queued_at: new Date().toISOString(),
    });
    await chrome.storage.local.set({ petrarca_queue: queue });
  }

  // --- Helpers -----------------------------------------------------------

  async function loadSettings() {
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

  function showStatus(el, message, type) {
    el.textContent = message;
    el.className = type;
  }

  function cleanUrl(url) {
    try {
      const u = new URL(url);
      return u.hostname + u.pathname.replace(/\/$/, "");
    } catch {
      return url;
    }
  }
})();
