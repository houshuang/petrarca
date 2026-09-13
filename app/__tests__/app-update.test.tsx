jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(), setItem: jest.fn(),
}));
jest.mock('expo-constants', () => ({ expoConfig: { version: '1.0.0' } }));
jest.mock('expo-updates', () => ({
  __esModule: true,
  isEnabled: true, isEmbeddedLaunch: false, updateId: 'update-one', createdAt: null,
}));
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Updates from 'expo-updates';
import { detectNewlyAppliedUpdate } from '../lib/app-version';

beforeEach(() => {
  jest.clearAllMocks();
  Object.assign(Updates, { isEnabled: true, isEmbeddedLaunch: false, updateId: 'update-one' });
  jest.mocked(AsyncStorage.getItem).mockResolvedValue(null);
  jest.mocked(AsyncStorage.setItem).mockResolvedValue();
});

test('announces the running update once, and a later update again', async () => {
  expect(await detectNewlyAppliedUpdate()).toEqual({ updateId: 'update-one', label: 'v1.0.0' });
  jest.mocked(AsyncStorage.getItem).mockResolvedValue('update-one');
  expect(await detectNewlyAppliedUpdate()).toBeNull();
  Object.assign(Updates, { updateId: 'update-two' });
  expect((await detectNewlyAppliedUpdate())?.updateId).toBe('update-two');
});

test('does not announce embedded, development or web launches', async () => {
  Object.assign(Updates, { isEmbeddedLaunch: true });
  expect(await detectNewlyAppliedUpdate()).toBeNull();
  Object.assign(Updates, { isEmbeddedLaunch: false, isEnabled: false });
  expect(await detectNewlyAppliedUpdate()).toBeNull();
  expect(AsyncStorage.setItem).not.toHaveBeenCalled();
});

test('storage failure does not interrupt startup', async () => {
  jest.mocked(AsyncStorage.getItem).mockRejectedValue(new Error('Unavailable'));
  expect(await detectNewlyAppliedUpdate()).toBeNull();
});
