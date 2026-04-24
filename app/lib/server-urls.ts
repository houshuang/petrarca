import { Platform } from 'react-native';

const DEFAULT_RESEARCH = 'http://alifstian.duckdns.org:8090';
const DEFAULT_CONTENT = 'https://alifstian.duckdns.org/content';
const DEFAULT_WEB_ORIGIN = 'https://alifstian.duckdns.org:8084';

function trimTrailingSlash(url: string): string {
  return url.replace(/\/$/, '');
}

/**
 * research-server.py (API, logging, stats). Override with EXPO_PUBLIC_RESEARCH_SERVER_URL
 * (e.g. http://100.x.y.z:8090 over Tailscale).
 */
export function getResearchServerUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_RESEARCH_SERVER_URL?.trim();
  if (fromEnv) return trimTrailingSlash(fromEnv);
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    return trimTrailingSlash(
      `${window.location.protocol}//${window.location.hostname}:8090`,
    );
  }
  return DEFAULT_RESEARCH;
}

/**
 * Static JSON fallback (manifest, articles.json). Override with EXPO_PUBLIC_CONTENT_BASE_URL.
 */
export function getContentBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_CONTENT_BASE_URL?.trim();
  if (fromEnv) return trimTrailingSlash(fromEnv);
  if (Platform.OS === 'web') return '/content';
  return DEFAULT_CONTENT;
}

/**
 * Static web host (guide, map). Override with EXPO_PUBLIC_WEB_APP_ORIGIN (no trailing slash).
 */
export function getWebAppOrigin(): string {
  const fromEnv = process.env.EXPO_PUBLIC_WEB_APP_ORIGIN?.trim();
  if (fromEnv) return trimTrailingSlash(fromEnv);
  return DEFAULT_WEB_ORIGIN;
}

export function getLogEventsUrl(): string {
  return `${getResearchServerUrl()}/log/events`;
}

export function getStatsDashboardUrl(): string {
  return `${getResearchServerUrl()}/stats/dashboard`;
}

/** In-app browser / WebView: full URL to bundled map page. */
export function getMapHtmlUrl(): string {
  if (Platform.OS === 'web') return '/map/index.html';
  return `${getWebAppOrigin()}/map/index.html`;
}

/** User guide: relative on web dev server, absolute on native. */
export function getGuideUrl(): string {
  if (Platform.OS === 'web') return '/guide/';
  return `${getWebAppOrigin()}/guide/`;
}
