export const getArticleById = jest.fn(() => null);
export const getReadingState = jest.fn(() => ({
  article_id: '',
  depth: 'unread',
  current_section_index: 0,
  last_read_at: 0,
  time_spent_ms: 0,
  started_at: 0,
}));
export const updateReadingState = jest.fn();
export const addSignal = jest.fn();
export const processClaimSignalForConcepts = jest.fn();
export const getRelatedArticles = jest.fn(() => []);
export const addVoiceNote = jest.fn();
export const getVoiceNotes = jest.fn(() => []);
export const getVoiceNoteById = jest.fn(() => undefined);
export const processTranscriptForConcepts = jest.fn(() => []);
