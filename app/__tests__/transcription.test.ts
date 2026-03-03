import { VoiceNote } from '../data/types';

// Mock store before importing transcription module
jest.mock('../data/store', () => ({
  updateVoiceNoteTranscript: jest.fn(),
  updateVoiceNoteStatus: jest.fn(),
  processTranscriptForConcepts: jest.fn(() => []),
}));
jest.mock('../data/logger', () => ({
  logEvent: jest.fn(),
}));

// Mock fetch globally
const mockFetch = jest.fn();
(global as any).fetch = mockFetch;

// Mock setTimeout/clearTimeout for polling
jest.useFakeTimers();

import { transcribeVoiceNote, transcribeAllPending } from '../data/transcription';
import { updateVoiceNoteTranscript, updateVoiceNoteStatus } from '../data/store';

const makeNote = (overrides?: Partial<VoiceNote>): VoiceNote => ({
  id: 'vn_test_1',
  article_id: 'art_1',
  depth: 'summary',
  recorded_at: Date.now(),
  duration_ms: 5000,
  file_uri: 'file:///tmp/test.m4a',
  transcription_status: 'pending',
  ...overrides,
});

function setupFetchSequence(responses: Array<{ ok: boolean; json?: any; status?: number }>) {
  for (const r of responses) {
    mockFetch.mockResolvedValueOnce({
      ok: r.ok,
      status: r.status || (r.ok ? 200 : 500),
      json: async () => r.json || {},
    });
  }
}

beforeEach(() => {
  jest.clearAllMocks();
  mockFetch.mockReset();
});

describe('transcribeVoiceNote', () => {
  it('completes full upload → create → poll → get → cleanup flow', async () => {
    setupFetchSequence([
      // 1. Upload file
      { ok: true, json: { id: 'file_123' } },
      // 2. Create transcription
      { ok: true, json: { id: 'txn_456' } },
      // 3. Poll - completed
      { ok: true, json: { status: 'completed' } },
      // 4. Get transcript
      { ok: true, json: { tokens: [{ text: 'Hello ' }, { text: 'world' }] } },
      // 5. Cleanup transcription (DELETE)
      { ok: true },
      // 6. Cleanup file (DELETE)
      { ok: true },
    ]);

    const note = makeNote();
    const promise = transcribeVoiceNote(note);
    // Advance past any polling timers
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe('Hello world');
    expect(updateVoiceNoteStatus).toHaveBeenCalledWith('vn_test_1', 'processing');
    expect(updateVoiceNoteTranscript).toHaveBeenCalledWith('vn_test_1', 'Hello world');

    // Verify API calls
    expect(mockFetch).toHaveBeenCalledTimes(6);
    // Upload
    expect(mockFetch.mock.calls[0][0]).toContain('/files');
    expect(mockFetch.mock.calls[0][1].method).toBe('POST');
    // Create transcription
    expect(mockFetch.mock.calls[1][0]).toContain('/transcriptions');
    expect(mockFetch.mock.calls[1][1].method).toBe('POST');
    // Poll
    expect(mockFetch.mock.calls[2][0]).toContain('/transcriptions/txn_456');
    // Get transcript
    expect(mockFetch.mock.calls[3][0]).toContain('/transcriptions/txn_456/transcript');
    // Cleanup
    expect(mockFetch.mock.calls[4][1].method).toBe('DELETE');
    expect(mockFetch.mock.calls[5][1].method).toBe('DELETE');
  });

  it('handles text response format (no tokens)', async () => {
    setupFetchSequence([
      { ok: true, json: { id: 'file_123' } },
      { ok: true, json: { id: 'txn_456' } },
      { ok: true, json: { status: 'completed' } },
      { ok: true, json: { text: 'Transcript text here' } },
      { ok: true },
      { ok: true },
    ]);

    const promise = transcribeVoiceNote(makeNote());
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe('Transcript text here');
    expect(updateVoiceNoteTranscript).toHaveBeenCalledWith('vn_test_1', 'Transcript text here');
  });

  it('sets status to failed on upload error', async () => {
    setupFetchSequence([
      { ok: false, status: 500 },
      // Cleanup still called (file_id null, txn_id null — no-ops)
    ]);

    const promise = transcribeVoiceNote(makeNote());
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(result).toBeNull();
    expect(updateVoiceNoteStatus).toHaveBeenCalledWith('vn_test_1', 'processing');
    expect(updateVoiceNoteStatus).toHaveBeenCalledWith('vn_test_1', 'failed');
  });

  it('sets status to failed on transcription error status', async () => {
    setupFetchSequence([
      { ok: true, json: { id: 'file_123' } },
      { ok: true, json: { id: 'txn_456' } },
      { ok: true, json: { status: 'error', error_message: 'Bad audio' } },
      // Cleanup
      { ok: true },
      { ok: true },
    ]);

    const promise = transcribeVoiceNote(makeNote());
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(result).toBeNull();
    expect(updateVoiceNoteStatus).toHaveBeenCalledWith('vn_test_1', 'failed');
  });

  it('polls multiple times before completion', async () => {
    setupFetchSequence([
      { ok: true, json: { id: 'file_123' } },
      { ok: true, json: { id: 'txn_456' } },
      // First poll - still processing
      { ok: true, json: { status: 'processing' } },
      // Second poll - completed
      { ok: true, json: { status: 'completed' } },
      { ok: true, json: { tokens: [{ text: 'Done' }] } },
      { ok: true },
      { ok: true },
    ]);

    const promise = transcribeVoiceNote(makeNote());
    await jest.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe('Done');
  });
});

describe('transcribeAllPending', () => {
  it('only transcribes pending notes', async () => {
    const notes = [
      makeNote({ id: 'vn_1', transcription_status: 'pending' }),
      makeNote({ id: 'vn_2', transcription_status: 'completed', transcript: 'already done' }),
      makeNote({ id: 'vn_3', transcription_status: 'pending' }),
    ];

    // Set up for 2 full transcription flows
    for (let i = 0; i < 2; i++) {
      setupFetchSequence([
        { ok: true, json: { id: `file_${i}` } },
        { ok: true, json: { id: `txn_${i}` } },
        { ok: true, json: { status: 'completed' } },
        { ok: true, json: { tokens: [{ text: `Text ${i}` }] } },
        { ok: true },
        { ok: true },
      ]);
    }

    const promise = transcribeAllPending(notes);
    await jest.runAllTimersAsync();
    const count = await promise;

    expect(count).toBe(2);
    // 2 notes * 6 calls each = 12
    expect(mockFetch).toHaveBeenCalledTimes(12);
  });
});
