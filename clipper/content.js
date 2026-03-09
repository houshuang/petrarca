// Petrarca Clipper — Content Script
// Extracts article content/selection for the popup and keyboard shortcut.

(function () {
  "use strict";

  // --- Selection tracking --------------------------------------------------

  let lastSelection = window.getSelection().toString().trim();

  document.addEventListener("selectionchange", () => {
    const sel = window.getSelection().toString().trim();
    if (sel) lastSelection = sel;
  });

  // --- Article extraction --------------------------------------------------

  function extractArticleContent() {
    const article = document.querySelector("article");
    if (article && article.innerText.trim().length > 200) {
      return cleanText(article.innerText);
    }

    const selectors = [
      '[role="main"]',
      "main",
      ".post-content",
      ".article-content",
      ".entry-content",
      ".content-body",
      "#content",
      ".post-body",
      ".story-body",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText.trim().length > 200) {
        return cleanText(el.innerText);
      }
    }

    const candidates = document.querySelectorAll("div, section, td");
    let best = null;
    let bestLen = 0;
    for (const el of candidates) {
      const text = el.innerText || "";
      const paragraphs = el.querySelectorAll("p");
      const pTextLen = Array.from(paragraphs).reduce(
        (sum, p) => sum + (p.innerText || "").length,
        0
      );
      const score = Math.max(pTextLen, text.length * 0.3);
      if (score > bestLen && text.length > 200) {
        bestLen = score;
        best = el;
      }
    }
    if (best) {
      return cleanText(best.innerText);
    }

    return cleanText(document.body.innerText).slice(0, 50000);
  }

  function extractTopics() {
    const topics = [];
    const metaKeywords = document.querySelector(
      'meta[name="keywords"], meta[property="article:tag"]'
    );
    if (metaKeywords) {
      const content = metaKeywords.getAttribute("content") || "";
      content
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, 5)
        .forEach((t) => topics.push(t));
    }

    if (topics.length === 0) {
      const tagEls = document.querySelectorAll(
        '.tag, .topic, [rel="tag"], a[href*="/tag/"], a[href*="/topic/"]'
      );
      tagEls.forEach((el) => {
        const text = (el.textContent || "").trim();
        if (text && text.length < 40 && topics.length < 5) {
          topics.push(text);
        }
      });
    }

    return topics;
  }

  function cleanText(text) {
    return text
      .replace(/\t/g, " ")
      .replace(/ {2,}/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  // --- Message handler -----------------------------------------------------

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request.type === "getPageData") {
      const content = extractArticleContent();
      const topics = extractTopics();
      sendResponse({
        title: document.title,
        url: window.location.href,
        content: content,
        selectedText: lastSelection,
        topics: topics,
      });
    }
    return true;
  });

})();
