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
  reading_order?: 'foundational' | 'intermediate' | 'deep';
  exploration_tier?: 'foundational' | 'intermediate' | 'deep';
  exploration_order?: number;
  interest_topics?: InterestTopic[];
  novelty_claims?: NoveltyClaim[];
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

// --- Interest-driven fields (extracted by pipeline) ---

export interface InterestTopic {
  broad: string;
  specific: string;
  entity?: string;
}

export interface NoveltyClaim {
  claim: string;
  specificity: 'high' | 'medium' | 'low';
}

export interface ReadingState {
  article_id: string;
  status: ReadingStatus;
  last_read_at: number;
  time_spent_ms: number;
  started_at: number;
  completed_at?: number;
  scroll_position_y: number;
  // Legacy fields for migration
  depth?: ReadingDepth;
  current_section_index?: number;
}

export type ReadingStatus = 'unread' | 'reading' | 'read';
export type ReadingDepth = 'unread' | 'summary' | 'claims' | 'concepts' | 'sections' | 'full';

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
  name: string;                    // Short entity name: "Garibaldi", "Greek colonization of Sicily"
  description: string;             // 1-2 sentence explanation
  text?: string;                   // Deprecated — old sentence-style concept text
  topic: string;
  source_article_ids: string[];
  aliases?: string[];              // Alternative names for matching
  related_concepts?: string[];     // IDs of related entities
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

// --- Books ---

export interface Book {
  id: string;
  title: string;
  author: string;
  cover_url?: string;
  chapters: BookChapterMeta[];
  topics: string[];
  thesis_statement?: string;
  running_argument: string[];   // one sentence per chapter processed
  language: string;
  added_at: number;
}

export interface BookChapterMeta {
  chapter_number: number;
  title: string;
  section_count: number;
  processing_status: 'pending' | 'completed';
}

export interface BookSection {
  id: string;                  // book_id:ch{N}:s{M}
  book_id: string;
  chapter_number: number;
  section_number: number;
  title: string;
  chapter_title: string;
  content_markdown: string;
  summary: string;
  briefing: string;
  claims: BookClaim[];
  key_terms: KeyTerm[];
  cross_book_connections: CrossBookConnection[];
  word_count: number;
  estimated_read_minutes: number;
}

export interface BookClaim {
  claim_id: string;            // M1, S1, etc. (scoped to section)
  text: string;
  claim_type: string;
  confidence: number;
  source_passage?: string;
  supports_claim?: string;
  is_main: boolean;
}

export interface KeyTerm {
  term: string;
  definition: string;
  conflicts_with?: string;     // if another book defines it differently
}

export interface CrossBookConnection {
  target_section_id: string;
  target_book_title: string;
  target_claim_text: string;
  relationship: 'agrees' | 'disagrees' | 'extends' | 'provides_evidence' | 'same_topic';
}

export type BookReadingDepth = 'unread' | 'briefing' | 'claims' | 'reading' | 'reflected';

export type ClaimSignalType = 'knew_it' | 'interesting' | 'save';

export interface BookReadingState {
  book_id: string;
  section_states: Record<string, SectionReadingState>;
  total_time_spent_ms: number;
  last_read_at: number;
  personal_thread: PersonalThreadEntry[];
}

export interface SectionReadingState {
  depth: BookReadingDepth;
  scroll_position_y: number;
  time_spent_ms: number;
  last_read_at: number;
  claim_signals: Record<string, ClaimSignalType>;
}

export interface PersonalThreadEntry {
  id: string;
  book_id: string;
  section_id: string;
  created_at: number;
  type: 'reflection' | 'voice_note' | 'claim_reaction' | 'connection';
  text: string;
  voice_note_id?: string;
  claim_id?: string;
  linked_concept_ids?: string[];
}

// === Knowledge Index (loaded from server) ===

export interface KnowledgeIndex {
  version: number;
  generated_at: string;
  stats: {
    total_articles: number;
    total_claims: number;
    total_similarity_pairs: number;
    total_topics: number;
    delta_report_count: number;
  };
  claims: Record<string, {
    text: string;
    article_id: string;
    claim_type: string;
    source_paragraphs: number[];
    topics: string[];
  }>;
  article_claims: Record<string, string[]>;
  similarities: Array<{ a: string; b: string; score: number }>;
  article_novelty_matrix: Record<string, Record<string, { new: number; extends: number; known: number }>>;
  delta_reports: Record<string, DeltaReport>;
}

export interface DeltaReport {
  topic: string;
  summary: string;
  claim_count: number;
  article_count: number;
  top_claims: Array<{ text: string; article_id: string; claim_type: string }>;
}

// === User Knowledge State ===

export type NoveltyClassification = 'NEW' | 'KNOWN' | 'EXTENDS';

export interface ClaimKnowledgeEntry {
  claim_id: string;
  first_seen_at: number;
  article_id: string;
  engagement: 'skim' | 'read' | 'highlight' | 'annotate';
  stability_days: number;
}

export interface ClaimClassification {
  claim_id: string;
  text: string;
  classification: NoveltyClassification;
  similarity_score: number;
  source_paragraphs: number[];
}

export interface ParagraphDimming {
  paragraph_index: number;
  opacity: number;
  novelty: 'novel' | 'mostly_novel' | 'mixed' | 'mostly_familiar' | 'familiar' | 'neutral';
  claim_counts: { new: number; extends: number; known: number };
}

export interface ArticleNovelty {
  article_id: string;
  total_claims: number;
  new_claims: number;
  extends_claims: number;
  known_claims: number;
  novelty_ratio: number;
  curiosity_score: number;
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
