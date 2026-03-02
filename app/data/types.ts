export interface Article {
  id: string;
  title: string;
  author: string;
  source_url: string;
  hostname: string;
  date: string;
  content_markdown: string;
  sections: ArticleSection[];
  one_line_summary: string;
  full_summary: string;
  key_claims: string[];
  topics: string[];
  estimated_read_minutes: number;
  content_type: ContentType;
  word_count: number;
  sources: ArticleSource[];
}

export interface ArticleSection {
  heading: string;
  content: string;
  summary: string;
  key_claims: string[];
}

export interface ArticleSource {
  type: 'twitter_bookmark' | 'rss' | 'manual';
  tweet_id?: string;
  author_username?: string;
  tweet_text?: string;
  bookmarked_at?: string;
}

export type ContentType =
  | 'analysis' | 'tutorial' | 'opinion' | 'news'
  | 'research' | 'reference' | 'announcement' | 'discussion'
  | 'unknown';

export interface ReadingState {
  article_id: string;
  depth: ReadingDepth;
  current_section_index: number;
  last_read_at: number;
  time_spent_ms: number;
  started_at: number;
}

export type ReadingDepth = 'unread' | 'summary' | 'claims' | 'sections' | 'full';

export interface UserSignal {
  article_id: string;
  signal: 'interesting' | 'knew_it' | 'deep_dive' | 'not_relevant' | 'save';
  timestamp: number;
  section_index?: number;
  depth?: ReadingDepth;
}
