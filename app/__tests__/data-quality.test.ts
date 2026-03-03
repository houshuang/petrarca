import articles from '../data/articles.json';
import concepts from '../data/concepts.json';

const BOILERPLATE_PATTERNS = [
  /bitcoin/i,
  /donation/i,
  /downloads last month/i,
  /buy me a coffee/i,
  /patreon\.com/i,
  /paypal\.me/i,
  /subscribe to our newsletter/i,
];

describe('articles.json data quality', () => {
  test('all articles have non-empty title', () => {
    const bad = articles.filter((a: any) => !a.title || a.title.trim().length === 0);
    expect(bad.map((a: any) => a.id)).toEqual([]);
  });

  test('all articles have content_markdown > 100 chars', () => {
    const bad = articles.filter(
      (a: any) => !a.content_markdown || a.content_markdown.length < 100
    );
    expect(bad.map((a: any) => ({ id: a.id, len: a.content_markdown?.length }))).toEqual([]);
  });

  test('no section heading is just "[" or "](#"', () => {
    const bad: { article: string; heading: string }[] = [];
    for (const a of articles as any[]) {
      for (const s of a.sections || []) {
        const h = (s.heading || '').trim();
        if (h === '[' || h.startsWith('](#') || h === '') {
          bad.push({ article: a.id, heading: h });
        }
      }
    }
    expect(bad).toEqual([]);
  });

  test('no section has content < 20 chars', () => {
    const bad: { article: string; heading: string; len: number }[] = [];
    for (const a of articles as any[]) {
      for (const s of a.sections || []) {
        const content = (s.content || '').trim();
        if (content.length < 20) {
          bad.push({ article: a.id, heading: s.heading, len: content.length });
        }
      }
    }
    expect(bad).toEqual([]);
  });

  test('no article content ends with boilerplate', () => {
    const bad: { article: string; match: string }[] = [];
    for (const a of articles as any[]) {
      const tail = (a.content_markdown || '').slice(-500);
      for (const pattern of BOILERPLATE_PATTERNS) {
        if (pattern.test(tail)) {
          bad.push({ article: a.id, match: pattern.source });
        }
      }
    }
    expect(bad).toEqual([]);
  });

  test('all articles have at least 1 key_claim', () => {
    const bad = articles.filter(
      (a: any) => !a.key_claims || a.key_claims.length === 0
    );
    expect(bad.map((a: any) => ({ id: a.id, title: a.title }))).toEqual([]);
  });
});

describe('concepts.json data quality', () => {
  const articleIds = new Set((articles as any[]).map((a) => a.id));

  test('all concepts have non-empty text and topic', () => {
    const bad = (concepts as any[]).filter(
      (c) => !c.text || c.text.trim().length === 0 || !c.topic || c.topic.trim().length === 0
    );
    expect(bad.map((c: any) => c.id)).toEqual([]);
  });

  test('all concept source_article_ids reference existing articles', () => {
    const bad: { concept: string; missing: string[] }[] = [];
    for (const c of concepts as any[]) {
      const missing = (c.source_article_ids || []).filter(
        (id: string) => !articleIds.has(id)
      );
      if (missing.length > 0) {
        bad.push({ concept: c.id, missing });
      }
    }
    expect(bad).toEqual([]);
  });
});
