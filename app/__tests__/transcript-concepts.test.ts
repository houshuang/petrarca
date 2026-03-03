/**
 * Tests for processTranscriptForConcepts — matching voice note transcripts
 * against article concepts and creating linked ConceptNotes.
 */

// We need to test the real store logic, so we mock only persistence and logger
jest.mock('../data/persistence', () => ({
  loadSignals: jest.fn(async () => []),
  saveSignals: jest.fn(),
  loadReadingStates: jest.fn(async () => new Map()),
  saveReadingStates: jest.fn(),
  loadConceptStates: jest.fn(async () => new Map()),
  saveConceptStates: jest.fn(),
  loadVoiceNotes: jest.fn(async () => []),
  saveVoiceNotes: jest.fn(),
  loadConceptReviews: jest.fn(async () => new Map()),
  saveConceptReviews: jest.fn(),
}));

jest.mock('../data/logger', () => ({
  logEvent: jest.fn(),
}));

// Mock the JSON requires — jest will intercept require('./articles.json') etc.
jest.mock('../data/articles.json', () => [
  {
    id: 'art_1',
    title: 'Test Article',
    author: 'Author',
    source_url: 'https://example.com',
    hostname: 'example.com',
    date: '2026-01-01',
    content_markdown: '',
    sections: [],
    one_line_summary: 'Test',
    full_summary: 'Test article',
    key_claims: [],
    topics: ['testing'],
    estimated_read_minutes: 5,
    content_type: 'analysis',
    word_count: 500,
    sources: [],
  },
], { virtual: true });

jest.mock('../data/concepts.json', () => [
  {
    id: 'c_spaced_repetition',
    text: 'Spaced repetition systems improve long-term memory retention',
    topic: 'learning',
    source_article_ids: ['art_1'],
  },
  {
    id: 'c_incremental_reading',
    text: 'Incremental reading prioritizes knowledge extraction from articles',
    topic: 'learning',
    source_article_ids: ['art_1'],
  },
  {
    id: 'c_blockchain',
    text: 'Blockchain consensus mechanisms enable decentralized trust',
    topic: 'crypto',
    source_article_ids: ['art_1'],
  },
], { virtual: true });

import {
  initStore,
  processTranscriptForConcepts,
  getConceptReview,
  getConceptState,
  getVoiceNoteById,
  addVoiceNote,
} from '../data/store';

beforeAll(async () => {
  await initStore();
});

describe('processTranscriptForConcepts', () => {
  it('matches transcript words against concept content words', () => {
    const matched = processTranscriptForConcepts(
      'art_1',
      'I was thinking about spaced repetition and how it helps with long-term memory retention in learning',
      'vn_1'
    );

    expect(matched).toContain('c_spaced_repetition');
  });

  it('does not match unrelated concepts', () => {
    const matched = processTranscriptForConcepts(
      'art_1',
      'I was thinking about spaced repetition and memory retention',
      'vn_2'
    );

    expect(matched).not.toContain('c_blockchain');
  });

  it('marks matched concepts as encountered', () => {
    processTranscriptForConcepts(
      'art_1',
      'Incremental reading helps prioritize knowledge extraction from many articles',
      'vn_3'
    );

    const state = getConceptState('c_incremental_reading');
    expect(state.state).toBe('encountered');
  });

  it('creates ConceptNote with voice_note_id', () => {
    processTranscriptForConcepts(
      'art_1',
      'Spaced repetition improves long-term memory retention significantly',
      'vn_4'
    );

    const review = getConceptReview('c_spaced_repetition');
    expect(review).toBeDefined();
    const voiceNotes = review!.notes.filter(n => n.voice_note_id === 'vn_4');
    expect(voiceNotes.length).toBe(1);
    expect(voiceNotes[0].text).toContain('Spaced repetition');
  });

  it('deduplicates — same voice_note_id does not create duplicate notes', () => {
    const notesBefore = getConceptReview('c_spaced_repetition')?.notes.length || 0;

    processTranscriptForConcepts(
      'art_1',
      'Spaced repetition improves long-term memory retention significantly',
      'vn_4' // same voice note ID as previous test
    );

    const notesAfter = getConceptReview('c_spaced_repetition')?.notes.length || 0;
    expect(notesAfter).toBe(notesBefore);
  });

  it('returns empty array for article with no concepts', () => {
    const matched = processTranscriptForConcepts(
      'art_nonexistent',
      'Some random transcript text about nothing in particular',
      'vn_5'
    );

    expect(matched).toEqual([]);
  });
});

describe('getVoiceNoteById', () => {
  it('returns undefined for nonexistent note', () => {
    expect(getVoiceNoteById('nonexistent')).toBeUndefined();
  });

  it('returns the voice note after adding one', () => {
    addVoiceNote({
      id: 'vn_lookup_test',
      article_id: 'art_1',
      depth: 'summary',
      recorded_at: Date.now(),
      duration_ms: 3000,
      file_uri: 'file:///tmp/test.m4a',
      transcription_status: 'pending',
    });

    const note = getVoiceNoteById('vn_lookup_test');
    expect(note).toBeDefined();
    expect(note!.id).toBe('vn_lookup_test');
    expect(note!.article_id).toBe('art_1');
  });
});
