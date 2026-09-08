jest.mock('react-native', () => ({ Platform: { OS: 'ios' } }));
jest.mock('expo-constants', () => ({
  __esModule: true, default: { expoConfig: { extra: { researchServerUrl: 'https://example.com/private/' } } },
}));
import { getResearchServerUrl, getLogEventsUrl } from '../lib/server-urls';
import Constants from 'expo-constants';

afterEach(() => { delete process.env.EXPO_PUBLIC_RESEARCH_SERVER_URL; });
test('native API and logging use the private release config', () => {
  expect(getResearchServerUrl()).toBe('https://example.com/private');
  expect(getLogEventsUrl()).toBe('https://example.com/private/log/events');
});
test('explicit developer override is retained', () => {
  process.env.EXPO_PUBLIC_RESEARCH_SERVER_URL = 'http://localhost:8090/';
  expect(getResearchServerUrl()).toBe('http://localhost:8090');
});
test('missing config never silently falls back to the closed public port', () => {
  if (Constants.expoConfig?.extra) Constants.expoConfig.extra.researchServerUrl = '';
  expect(getResearchServerUrl()).toBe('https://alifstian.duckdns.org/petrarca-api-not-configured');
});
