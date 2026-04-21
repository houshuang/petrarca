export interface ArticleEntity {
  name: string;
  type: 'person' | 'book' | 'company' | 'concept' | 'place' | 'event' | 'technology';
  synthesis: string;
  mentions: string[];
}

export interface FollowUpQuestion {
  question: string;
  connects_to: string;
}

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
  entities?: ArticleEntity[];
  follow_up_questions?: FollowUpQuestion[];
  ingested_at?: string;
}

/** Article without heavy content fields — used for feed/ranking/store. */
export type ArticleMeta = Omit<Article, 'content_markdown' | 'sections'>;

/** The heavy content fields loaded on demand when reading. */
export interface ArticleContent {
  id: string;
  content_markdown: string;
  sections: ArticleSection[];
}

export interface ArticleSection {
  heading: string;
  content: string;
  summary: string;
  key_claims: string[];
}

export interface ArticleSource {
  type: string;
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

export interface SynthesisFollowUpQuestion {
  question: string;
  research_prompt: string;
  related_topics: string[];
}

export interface TopicSynthesis {
  cluster_id: string;
  label: string;
  synthesis_markdown: string;
  article_ids: string[];
  article_coverage: Record<string, number>;
  claims_covered: string[];
  unique_per_article: Record<string, string[]>;
  follow_up_questions: SynthesisFollowUpQuestion[];
  tensions: Array<string | { label: string; description: string; article_ids?: string[] }>;
  generated_at: string;
  total_articles: number;
  total_claims_covered: number;
  total_claims_in_cluster: number;
  // Legacy fields (v1 format)
  topic?: string;
  synthesis_text?: string;
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
    nli_pairs_classified?: number;
    nli_changed?: number;
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
  nli_verdicts?: Record<string, 'ENTAILS' | 'EXTENDS' | 'UNRELATED'>;
  article_novelty_matrix: Record<string, Record<string, { new: number; extends: number; known: number }>>;
  article_similarities?: Array<{ a: string; b: string; score: number }>;
  delta_reports: Record<string, DeltaReport>;
  article_curriculum_nodes?: Record<string, Array<{
    node_id: string;
    domain_id: string;
    node_title: string;
    claim_count: number;
    avg_similarity: number;
    max_similarity: number;
  }>>;
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
  claim_type: string;
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

// --- Physical Books ---

export interface PhysicalBook {
  id: string;                         // pb_{timestamp}_{hash}
  title: string;
  author: string;
  cover_image_uri?: string;           // local photo of cover
  cover_url?: string;                 // web URL for cover image (from metadata lookup)
  isbn?: string;
  publisher?: string;
  year?: number;
  page_count?: number;
  language: string;
  topics: string[];
  chapters: PhysicalBookChapter[];
  current_chapter?: string;           // chapter title
  current_page?: number;
  reading_status: 'reading' | 'finished' | 'paused' | 'want_to_read' | 'archived';
  significance?: 'skimmed' | 'read' | 'essential';  // how formative this book is
  finished_date?: string;               // ISO date when marked finished
  added_at: number;
  last_interaction_at: number;        // for sorting by recency
  metadata_source?: 'photo' | 'manual' | 'search' | 'kindle';
  processing_status?: 'identifying' | 'ready';
}

export interface PhysicalBookChapter {
  number: number;
  title: string;
  start_page?: number;
}

export type BookCaptureType = 'voice_note' | 'page_photo' | 'text_note';

export interface BookCapture {
  id: string;                         // cap_{timestamp}
  book_id: string;
  type: BookCaptureType;
  created_at: number;
  // Voice
  audio_uri?: string;                 // local file path
  transcript?: string;
  transcription_status?: 'pending' | 'processing' | 'completed' | 'failed';
  // Photo
  photo_uri?: string;                 // local file path
  ocr_text?: string;
  ocr_status?: 'pending' | 'processing' | 'completed' | 'failed';
  // Text
  text?: string;
  // Context
  page_number?: number;
  chapter?: string;
  // Extracted knowledge
  extracted_ideas?: string[];
  topics?: string[];
  // Enhanced OCR fields
  key_passage?: string;
  elaborative_question?: string;
  // Server sync
  server_id?: string;
  upload_status: 'pending' | 'uploaded' | 'failed';
}

// --- Book Research types (from server research agent) ---

export interface BookResearch {
  book_id: string;
  title: string;
  author: string;
  thesis: string;
  debates: string[];
  key_terms: Array<{ term: string; definition: string }>;
  reception: string;
  chapter_research: Record<string, ChapterResearch>;
  article_connections: BookArticleConnection[];
  suggested_reading: SuggestedReading[];
  topics: string[];
  researched_at: string;
}

export interface ChapterResearch {
  summary: string;
  claims: string[];
  key_terms: string[];
}

export interface BookArticleConnection {
  article_id: string;
  article_title: string;
  connection_type: 'extends' | 'contradicts' | 'complements';
  reason: string;
  chapter_number?: number;
  similarity?: number;
}

export interface SuggestedReading {
  title: string;
  author?: string;
  url: string;
  reason: string;
}

export interface StorySoFarBriefing {
  argument_summary: string;
  highlights: Array<{ text: string; why_it_matters: string }>;
  preview: string;
  articles_since: number;
  suggested_reading: SuggestedReading[];
}

export interface ChapterInsights {
  chapter_number: number;
  chapter_title: string;
  summary: string;
  claims: string[];
  key_terms: string[];
  connections: BookArticleConnection[];
  captures_count: number;
}

// --- Resurfacing types ---

export interface MicrolearningQuiz {
  id: string;
  question: string;
  answer: string;
}

export interface ResurfacingItem {
  type: 'review' | 'microlearning' | 'microlearning_quiz' | 'entity_intro' | 'resonance' | 'dialogue' | 'retrieval' | 'temporal_ordering' | 'aspect' | 'sequence' | 'synchronic' | 'cast' | 'causal';
  // Review card fields (from knowledge_items)
  title?: string;  // prominent card title (with dates)
  question_id?: string;
  question?: string;
  answer?: string;
  rich_answer?: string;
  answer_type?: 'date' | 'name' | 'concept' | 'sequence' | 'person' | 'event' | 'connection' | 'significance';
  node_title?: string;
  node_description?: string;
  domain?: string;
  domain_id?: string;
  memory_hook?: string;
  temporal_hook?: string;
  // Session 90 P1.1: learner's own captured confidence on this fact
  confidence?: 'certain' | 'uncertain' | 'wrong';
  source_excerpt?: string;
  // Session 90 P1.2: verifiable correction when the short answer contradicts ground truth
  correction?: {
    user_said: string;
    actually: string;
    why_confused: string;
  } | null;
  curriculum_context?: string;
  anchors?: string[];
  follow_up_queries?: string[];
  triggered_follow_ups?: string[];  // durably tracked: queries already triggered
  content?: string;  // microlearning card body (plain text for entity spans)
  sections?: { heading: string | null; text: string }[];  // structured display
  query?: string;    // original research query
  quizzes?: MicrolearningQuiz[];  // multiple quizzes per ML card
  card_id?: string;  // parent card ID for individual quiz review
  review_count?: number;
  last_score?: string;
  stability_days?: number;
  node_knowledge?: string;
  node_confidence?: number;
  // Provenance — origin, scheduling, and scoring data for "About this card"
  provenance?: {
    origin: string;  // 'book_chapter' | 'book_whole' | 'gap_fill' | 'voice_wondering' | 'follow_up' | 'entity_research' | 'entity_capture' | 'user_request' | 'unknown'
    is_gap_fill?: boolean;
    stream_score?: number;
    schedule_reason?: string;  // 'never_reviewed' | 'overdue' | 'due_soon' | 'not_due'
    overdue_days?: number;
    knowledge_weight?: number;
    fact_type_adj?: number;
    sources?: Array<{
      // Book-chapter/whole-book source shape:
      book_id?: string;
      chapter_number?: number;
      chapter_title?: string;
      lens?: string;
      confidence?: number;
      // Voice-capture source shape (entity_capture items):
      source?: string;          // 'voice_capture' | 'voice_elicitation'
      capture_id?: string;      // voice_transcripts.id
      // Shared fields:
      source_text?: string;
      added_at?: string | number;
    }>;
    source_item_id?: string;
    source_node_id?: string;
    generation_depth?: number;
    created_at?: number;
    due_at?: number;
    last_reviewed_at?: number;
    // Entity-capture provenance:
    entity_id?: string;
    wikidata_qid?: string;
  };
  // Entity annotation (from server entity matching)
  entity_spans?: Record<string, EntitySpan[]>;
  // Entity intro card fields
  entity_id?: string;
  entity_name?: string;
  entity_type?: string;
  modern_name?: string;
  description?: string;
  latitude?: number;
  longitude?: number;
  wikipedia_url?: string;
  date_start?: number;
  date_end?: number;
  // Legacy fields (retained for compatibility)
  prompt_type?: string;
  prompt_text?: string;
  question_type?: string;
  cluster_label?: string;
  grading_options?: string[];
  capture_id?: string;
  book_id?: string;
  book_title?: string;
  book_author?: string;
  book_cover_url?: string;
  chapter?: string;
  highlight_text?: string;
  full_text?: string;
  months_since_capture?: number;
  resurface_count?: number;
  claim_a?: { text: string; book_id: string; book_title: string; book_author: string; chapter: string };
  claim_b?: { text: string; book_id: string; book_title: string; book_author: string; chapter: string };
  tension_prompt?: string;
}

export interface ReviewStreamResponse {
  items: ResurfacingItem[];
  generated_at: string;
  offset: number;
  has_more: boolean;
  total_candidates: number;
  total_items: number;
  total_with_question: number;
  due_count: number;
  domain_counts: Record<string, number>;
}

export interface EntitySpan {
  start: number;
  end: number;
  entity_id: string;
  entity_type: string;
  name: string;
}

export interface MicrolearningBacklink {
  card_id: string;
  query: string;
  snippet: string;
  domain?: string;
}

export interface EntityNote {
  id: number;
  note: string;
  created_at: number;
}

export interface EntityDetails {
  entity_id: string;
  name: string;
  description?: string;
  entity_type?: string;
  modern_name?: string;
  wikipedia_url?: string;
  latitude?: number;
  longitude?: number;
  aliases: string[];
  dates?: string;
  date_start?: number;
  date_end?: number;
  nexus_score: number;
  curriculum_links: EntityCurriculumLink[];
  microlearning_backlinks?: MicrolearningBacklink[];
  notes?: EntityNote[];
  voice_context?: Array<{ text: string; type: string }>;
}

export interface EntityCurriculumLink {
  domain_id: string;
  node_id: string;
  lens_title: string;
  lens_emphasis: string;
  node_title?: string;
  node_description?: string;
  knowledge?: string;
}

export interface ResurfacingSession {
  id: string;
  items: ResurfacingItem[];
  generated_at: string;
  resonance_count: number;
  dialogue_count: number;
  // Curriculum review fields (present when session includes review items)
  retrieval_count?: number;
  ordering_count?: number;
  total_questions_in_pool?: number;
}

// ─── Knowledge Review ────────────────────────────────────────────────────────

export interface ReviewItem {
  id: string;
  item_type: 'book_chapter' | 'exploration' | 'voice_followup';
  curriculum_domain?: string;
  curriculum_node_id?: string;
  curriculum_node_title?: string;
  source_book_id?: string;
  source_chapter_number?: number;
  source_chapter_title?: string;
  source_text: string;
  temporal_hook?: string;
  lens?: string;
  parent_item_id?: string;
  stability_days: number;
  due_at: number;
  last_reviewed_at?: number;
  last_score?: 'knew' | 'partly' | 'missed';
  review_count: number;
  created_at: number;
}

export interface ReviewQuestion {
  question: string;
  answer_guidance: string;
  rich_answer?: string;
  temporal_hook: string;
  curriculum_context: string;
}

export interface ReviewStats {
  due_today: number;
  due_this_week: number;
  total: number;
  by_source: Record<string, number>;
}

export interface ChapterCompleteResult {
  nodes_covered: string[];
  items_created: number;
  domain: string;
  due_today: number;
}
