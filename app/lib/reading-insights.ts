import { Article, ReadingState } from '../data/types';
import {
  getArticles, getReadingState, getArticleById, getReadArticles,
  getInProgressArticles, getArticlesGroupedByTopic, getArticleNovelty,
  getCrossArticleConnections,
} from '../data/store';
import { isKnowledgeReady } from '../data/knowledge-engine';
import { getDisplayTitle } from './display-utils';

// --- Types ---

export interface ReadingThread {
  topic: string;
  description: string;
  articles: ThreadArticle[];
  totalArticles: number;
  readCount: number;
  readingCount: number;
  unreadCount: number;
}

export interface ThreadArticle {
  id: string;
  title: string;
  status: 'read' | 'reading' | 'unread';
  progress?: number; // 0-1 for reading articles
  source?: string;
  readMinutes?: number;
  reason?: string; // why this article is in the thread
}

export interface ReadingSession {
  date: string; // 'Today', 'Yesterday', 'Monday', etc.
  dateKey: string; // YYYY-MM-DD
  articles: SessionArticle[];
  totalMinutes: number;
}

export interface SessionArticle {
  id: string;
  title: string;
  action: string; // 'Finished', 'Started', 'Browsed', etc.
  minutes: number;
}

export interface TopicBubble {
  topic: string;
  articleCount: number;
  trend: 'active' | 'growing' | 'quiet' | 'new';
  lastReadDaysAgo: number;
}

export interface CrossThreadBridge {
  fromTopic: string;
  toTopic: string;
  description: string;
  articleTitles: [string, string];
}

// --- Thread computation ---

export function getActiveThreads(maxThreads: number = 6): ReadingThread[] {
  const groups = getArticlesGroupedByTopic();
  const allArticles = getArticles();

  const threads: ReadingThread[] = [];

  for (const { topic, articles: unreadArticles } of groups) {
    // Also include read articles in this topic
    const readInTopic = allArticles.filter(a => {
      const state = getReadingState(a.id);
      if (state.status !== 'read') return false;
      const topics = (a.interest_topics || []).map(t => t.broad);
      const fallback = topics.length > 0 ? topics : a.topics.slice(0, 2);
      return fallback.some(t => t.toLowerCase() === topic.toLowerCase());
    });

    const allInTopic = [...readInTopic, ...unreadArticles];
    if (allInTopic.length < 2) continue;

    const threadArticles: ThreadArticle[] = allInTopic
      .map(a => {
        const state = getReadingState(a.id);
        const status = state.status === 'read' ? 'read' as const
          : state.status === 'reading' ? 'reading' as const
          : 'unread' as const;
        return {
          id: a.id,
          title: getDisplayTitle(a),
          status,
          progress: state.scroll_position_y ? undefined : undefined,
          source: a.source_url?.replace(/^https?:\/\/(www\.)?/, '').split('/')[0],
          readMinutes: a.estimated_read_minutes,
        };
      })
      .sort((a, b) => {
        const order = { read: 0, reading: 1, unread: 2 };
        return order[a.status] - order[b.status];
      });

    const readCount = threadArticles.filter(a => a.status === 'read').length;
    const readingCount = threadArticles.filter(a => a.status === 'reading').length;
    const unreadCount = threadArticles.filter(a => a.status === 'unread').length;

    threads.push({
      topic,
      description: '', // Could be enriched with delta reports
      articles: threadArticles,
      totalArticles: threadArticles.length,
      readCount,
      readingCount,
      unreadCount,
    });
  }

  // Sort: threads with in-progress articles first, then by total engagement
  return threads
    .sort((a, b) => {
      if (a.readingCount > 0 && b.readingCount === 0) return -1;
      if (b.readingCount > 0 && a.readingCount === 0) return 1;
      return (b.readCount + b.readingCount) - (a.readCount + a.readingCount);
    })
    .slice(0, maxThreads);
}

// --- Session history ---

export function getRecentSessions(maxSessions: number = 7): ReadingSession[] {
  const allArticles = getArticles();
  const now = Date.now();

  // Group articles by day based on last_read_at
  const dayMap = new Map<string, SessionArticle[]>();

  for (const a of allArticles) {
    const state = getReadingState(a.id);
    if (!state.last_read_at) continue;

    const date = new Date(state.last_read_at);
    const dateKey = date.toISOString().split('T')[0];
    const minutes = Math.round(state.time_spent_ms / 60000);

    let action = 'Browsed';
    if (state.status === 'read') action = 'Finished';
    else if (state.status === 'reading') action = 'Started';

    if (!dayMap.has(dateKey)) dayMap.set(dateKey, []);
    dayMap.get(dateKey)!.push({
      id: a.id,
      title: getDisplayTitle(a),
      action,
      minutes: Math.max(1, minutes),
    });
  }

  const sessions: ReadingSession[] = [];
  const sortedDays = [...dayMap.keys()].sort().reverse();

  for (const dateKey of sortedDays.slice(0, maxSessions)) {
    const articles = dayMap.get(dateKey)!;
    const totalMinutes = articles.reduce((s, a) => s + a.minutes, 0);
    sessions.push({
      date: formatRelativeDate(dateKey),
      dateKey,
      articles,
      totalMinutes,
    });
  }

  return sessions;
}

function formatRelativeDate(dateKey: string): string {
  const date = new Date(dateKey + 'T12:00:00');
  const now = new Date();
  const todayKey = now.toISOString().split('T')[0];
  const yesterdayDate = new Date(now);
  yesterdayDate.setDate(yesterdayDate.getDate() - 1);
  const yesterdayKey = yesterdayDate.toISOString().split('T')[0];

  if (dateKey === todayKey) return 'Today';
  if (dateKey === yesterdayKey) return 'Yesterday';

  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays < 7) return dayNames[date.getDay()];

  return date.toLocaleDateString('en', { month: 'short', day: 'numeric' });
}

// --- Topic bubbles ---

export function getTopicBubbles(): TopicBubble[] {
  const groups = getArticlesGroupedByTopic();
  const allArticles = getArticles();
  const now = Date.now();

  const bubbles: TopicBubble[] = [];

  for (const { topic, articles: unreadArticles } of groups) {
    // Count all articles (read + unread) in this topic
    const readInTopic = allArticles.filter(a => {
      const state = getReadingState(a.id);
      if (state.status !== 'read') return false;
      const topics = (a.interest_topics || []).map(t => t.broad);
      const fallback = topics.length > 0 ? topics : a.topics.slice(0, 2);
      return fallback.some(t => t.toLowerCase() === topic.toLowerCase());
    });

    const allInTopic = [...readInTopic, ...unreadArticles];
    const totalCount = allInTopic.length;

    // Find most recent read time
    let latestRead = 0;
    for (const a of allInTopic) {
      const state = getReadingState(a.id);
      if (state.last_read_at && state.last_read_at > latestRead) {
        latestRead = state.last_read_at;
      }
    }

    const daysAgo = latestRead ? Math.floor((now - latestRead) / (1000 * 60 * 60 * 24)) : 999;

    let trend: TopicBubble['trend'] = 'quiet';
    if (readInTopic.length === 0 && unreadArticles.length > 0) trend = 'new';
    else if (daysAgo <= 2) trend = 'active';
    else if (daysAgo <= 7) trend = 'growing';

    bubbles.push({
      topic,
      articleCount: totalCount,
      trend,
      lastReadDaysAgo: daysAgo,
    });
  }

  return bubbles.sort((a, b) => {
    const trendOrder = { active: 0, growing: 1, new: 2, quiet: 3 };
    return trendOrder[a.trend] - trendOrder[b.trend] || b.articleCount - a.articleCount;
  });
}

// --- Cross-thread bridges ---

export function getCrossThreadBridges(maxBridges: number = 3): CrossThreadBridge[] {
  if (!isKnowledgeReady()) return [];

  const readArticles = getReadArticles();
  const bridges: CrossThreadBridge[] = [];
  const seen = new Set<string>();

  for (const article of readArticles.slice(0, 20)) {
    const connections = getCrossArticleConnections(article.id);
    const articleTopics = (article.interest_topics || []).map(t => t.broad);
    const primaryTopic = articleTopics[0] || article.topics[0] || '';

    for (const conn of connections.slice(0, 3)) {
      const other = getArticleById(conn.articleId);
      if (!other) continue;

      const otherTopics = (other.interest_topics || []).map(t => t.broad);
      const otherTopic = otherTopics[0] || other.topics[0] || '';

      if (!primaryTopic || !otherTopic) continue;
      if (primaryTopic.toLowerCase() === otherTopic.toLowerCase()) continue;

      const key = [primaryTopic, otherTopic].sort().join('::');
      if (seen.has(key)) continue;
      seen.add(key);

      bridges.push({
        fromTopic: primaryTopic,
        toTopic: otherTopic,
        description: `Shared ideas between ${getDisplayTitle(article)} and ${getDisplayTitle(other)}`,
        articleTitles: [getDisplayTitle(article), getDisplayTitle(other)],
      });

      if (bridges.length >= maxBridges) return bridges;
    }
  }

  return bridges;
}

// --- Desk data (for feed header) ---

export function getDeskArticle(): { article: Article; state: ReadingState; excerpt?: string } | null {
  const inProgress = getInProgressArticles();
  if (inProgress.length === 0) return null;

  const article = inProgress[0];
  const state = getReadingState(article.id);

  // Try to get a text excerpt near where they stopped
  let excerpt: string | undefined;
  if (article.content_markdown && state.scroll_position_y) {
    const paragraphs = article.content_markdown.split(/\n\n+/).filter(p => p.trim().length > 20 && !p.startsWith('#'));
    const estimatedPara = Math.min(
      Math.floor(state.scroll_position_y / 200),
      paragraphs.length - 1
    );
    const para = paragraphs[Math.max(0, estimatedPara)];
    if (para) {
      excerpt = para.slice(0, 150).trim() + (para.length > 150 ? '...' : '');
    }
  }

  return { article, state, excerpt };
}

// --- Stats summary ---

export function getReadingStats(periodDays: number = 7) {
  const allArticles = getArticles();
  const now = Date.now();
  const cutoff = now - periodDays * 24 * 60 * 60 * 1000;

  let articlesExplored = 0;
  let totalTimeMs = 0;
  const topicsSet = new Set<string>();

  for (const a of allArticles) {
    const state = getReadingState(a.id);
    if (!state.last_read_at || state.last_read_at < cutoff) continue;

    articlesExplored++;
    totalTimeMs += state.time_spent_ms;

    const topics = (a.interest_topics || []).map(t => t.broad);
    const fallback = topics.length > 0 ? topics : a.topics.slice(0, 2);
    for (const t of fallback) topicsSet.add(t);
  }

  const bridges = getCrossThreadBridges();

  return {
    articlesExplored,
    totalHours: Math.round(totalTimeMs / 3600000 * 10) / 10,
    topicsTouched: topicsSet.size,
    connectionsFound: bridges.length,
    periodDays,
  };
}
