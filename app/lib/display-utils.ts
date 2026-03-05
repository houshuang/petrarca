/** Shared display utilities */

export function getDisplayTitle(article: { title: string; one_line_summary: string }): string {
  if (/^Thread by @/i.test(article.title) && article.one_line_summary && article.one_line_summary !== '[dry run]') {
    return article.one_line_summary;
  }
  return article.title;
}
