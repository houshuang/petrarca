export interface Bookmark {
  id: string;
  text: string;
  created_at: string;
  url: string;
  author_username: string;
  author_name: string;
  likes: number;
  retweets: number;
  lang: string;
  urls: string[];
  hashtags: string[];
  _relevance_score: number;
  _matched_patterns: string[];
  _parsed_date: string;
  extracted_articles: ExtractedArticle[];
  _llm_summary?: LLMSummary;
  _related_tweets?: string[];
  quoted_tweet?: {
    id: string;
    text: string;
    author_username: string;
    author_name: string;
  };
}

export interface ExtractedArticle {
  url: string;
  title: string;
  content: string;
  excerpt?: string;
}

export interface LLMSummary {
  summary: string;
  key_claims: string[];
  content_type: string;
  topics: string[];
  novelty_notes?: string;
}

export type SwipeDirection = 'left' | 'right' | 'up';

export interface UserSignal {
  bookmarkId: string;
  signal: 'knew_it' | 'interesting' | 'deep_dive' | 'not_relevant';
  timestamp: number;
  notes?: string;
}
