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
  similar_articles?: Array<{ id: string; title: string; score: number }>;
  exploration_tag?: string;
  parent_id?: string;
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
  scroll_position_y: number;
}

export type ReadingDepth = 'unread' | 'summary' | 'claims' | 'sections' | 'full';

export interface UserSignal {
  article_id: string;
  signal: 'interesting' | 'knew_it' | 'deep_dive' | 'not_relevant' | 'save';
  timestamp: number;
  section_index?: number;
  depth?: ReadingDepth;
}

// --- Knowledge Model ---

export interface Concept {
  id: string;
  text: string;
  topic: string;
  source_article_ids: string[];
}

export type ConceptKnowledgeLevel = 'unknown' | 'encountered' | 'known';

export interface ConceptState {
  concept_id: string;
  state: ConceptKnowledgeLevel;
  last_seen: number;
  signal_count: number;
}

// --- Spaced Attention Scheduling ---

export interface ConceptReview {
  concept_id: string;
  // Scheduling state
  stability_days: number;        // Current interval in days (grows with good reviews)
  difficulty: number;            // 0.3 (easy) to 3.0 (hard)
  due_at: number;                // Timestamp when next review is due
  engagement_count: number;      // Total times engaged
  last_engaged_at: number;
  // Self-assessment
  understanding: number;         // 1-4 scale (confused → could teach)
  // Engagement history
  notes: ConceptNote[];
}

export interface ConceptNote {
  id: string;
  text: string;
  voice_note_id?: string;
  created_at: number;
}

export type ReviewRating = 1 | 2 | 3 | 4; // again(1) hard(2) good(3) easy(4)

// --- Topic Syntheses ---

export interface TopicSynthesis {
  topic: string;
  synthesis_text: string;
  article_ids: string[];
  generated_at: string;
}

// --- Voice Notes ---

export interface VoiceNote {
  id: string;
  article_id: string;
  depth: ReadingDepth;
  section_index?: number;
  recorded_at: number;
  duration_ms: number;
  file_uri: string;
  transcript?: string;
  transcription_status: 'pending' | 'processing' | 'completed' | 'failed';
}

// --- Highlights ---

export interface Highlight {
  id: string;
  article_id: string;
  block_index: number;       // index into markdown blocks
  text: string;              // full paragraph text
  highlighted_at: number;
  zone: ReadingDepth;
  note?: string;
}

// --- Research Agent ---

export interface ResearchResult {
  id: string;
  query: string;
  article_id: string;
  article_title: string;
  voice_note_id?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  requested_at: number;
  completed_at?: number;
  perspectives?: string[];
  recommendations?: string[];
  connections?: string[];
  error?: string;
}
