jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: { getItem: jest.fn().mockResolvedValue(null), setItem: jest.fn().mockResolvedValue(undefined) },
}));
jest.mock('../data/logger', () => ({ logEvent: jest.fn() }));
jest.mock('../lib/book-api', () => ({
  loadBooksFromServer: jest.fn(() => new Promise(() => {})), syncBooksToServer: jest.fn(),
}));
jest.mock('../data/content-sync', () => ({
  loadCachedContent: jest.fn().mockResolvedValue(null),
  downloadContent: jest.fn(() => new Promise(() => {})), checkForUpdates: jest.fn(),
}));
jest.mock('../data/persistence', () => ({
  loadSignals: jest.fn().mockResolvedValue([]), loadReadingStates: jest.fn().mockResolvedValue(new Map()),
  loadHighlights: jest.fn().mockResolvedValue([]),
}));
jest.mock('../data/interest-model', () => ({ loadInterestProfile: jest.fn() }));
jest.mock('../data/queue', () => ({ loadQueue: jest.fn(), getQueuedArticleIds: jest.fn().mockReturnValue([]) }));
jest.mock('../data/bookmarks', () => ({ loadBookmarks: jest.fn() }));
jest.mock('../data/knowledge-engine', () => ({ initKnowledgeEngine: jest.fn() }));
jest.mock('../data/article-content', () => ({ prefetchArticleContent: jest.fn() }));

import AsyncStorage from '@react-native-async-storage/async-storage';
import { initStore, isInitialized } from '../data/store';
import { getPhysicalBooks, onBookStoreChange } from '../data/book-store';
import { downloadContent } from '../data/content-sync';
import { loadBooksFromServer } from '../lib/book-api';

test('startup completes with cached books while both server requests remain stalled', async () => {
  let finishBooks!: (data: Awaited<ReturnType<typeof loadBooksFromServer>>) => void;
  jest.mocked(loadBooksFromServer).mockImplementation(() => new Promise(resolve => { finishBooks = resolve; }));
  const onBooks = jest.fn();
  const unsubscribe = onBookStoreChange(onBooks);
  jest.mocked(AsyncStorage.getItem).mockImplementation(async key =>
    key === '@petrarca/physical_books' ? JSON.stringify([{ id: 'cached-book', title: 'On the phone' }]) : null);
  await initStore();
  expect(isInitialized()).toBe(true);
  expect(getPhysicalBooks()[0].id).toBe('cached-book');
  expect(loadBooksFromServer).toHaveBeenCalledTimes(1);
  expect(downloadContent).toHaveBeenCalledTimes(1);
  finishBooks({ books: [{ ...getPhysicalBooks()[0], id: 'server-book' }], captures: [] });
  await new Promise(resolve => setImmediate(resolve));
  expect(getPhysicalBooks().map(book => book.id).sort()).toEqual(['cached-book', 'server-book']);
  expect(onBooks).toHaveBeenCalledTimes(1);
  unsubscribe();
});
