/** Shared display utilities */

export function getDisplayTitle(article: { title: string; one_line_summary: string }): string {
  if (/^Thread by @/i.test(article.title) && article.one_line_summary && article.one_line_summary !== '[dry run]') {
    return article.one_line_summary;
  }
  return article.title;
}

/** Normalize topic key: hyphens→spaces, lowercase, collapse whitespace */
export function normalizeTopic(topic: string): string {
  return topic.replace(/-/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
}

/** Display-friendly topic: "medieval-history" → "Medieval History" */
export function displayTopic(topic: string): string {
  return normalizeTopic(topic).replace(/\b\w/g, c => c.toUpperCase());
}
