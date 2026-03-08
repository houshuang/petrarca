import AsyncStorage from '@react-native-async-storage/async-storage';
import { Article, InterestTopic } from './types';
import { logEvent } from './logger';

const INTEREST_PROFILE_KEY = '@petrarca/interest_profile';
const DECAY_HALF_LIFE_DAYS = 30;
const PARENT_SIGNAL_RATIO = 0.3;

// --- Types ---

export interface TopicInterest {
  topic: string;
  level: 'broad' | 'specific' | 'entity';
  parent?: string;
  positive_signals: number;
  negative_signals: number;
  interest_score: number;
  last_signal: number;
  articles_seen: number;
}

export interface InterestProfile {
  topics: Record<string, TopicInterest>;
  updated_at: number;
}

// --- Signal weights ---

export type SignalAction =
  | 'swipe_keep'
  | 'swipe_dismiss'
  | 'open_article'
  | 'tap_done'
  | 'highlight_paragraph'
  | 'interest_chip_positive'
  | 'interest_chip_negative'
  | 'bookmark_add'
  | 'bookmark_remove';

const SIGNAL_WEIGHTS: Record<SignalAction, { positive: boolean; weight: number }> = {
  swipe_keep:              { positive: true,  weight: 1.0 },
  swipe_dismiss:           { positive: false, weight: 0.5 },
  open_article:            { positive: true,  weight: 0.5 },
  tap_done:                { positive: true,  weight: 1.5 },
  highlight_paragraph:     { positive: true,  weight: 1.0 },
  interest_chip_positive:  { positive: true,  weight: 2.0 },
  interest_chip_negative:  { positive: false, weight: 2.0 },
  bookmark_add:            { positive: true,  weight: 1.5 },
  bookmark_remove:         { positive: false, weight: 0.5 },
};

// --- Module state ---

let profile: InterestProfile = { topics: {}, updated_at: 0 };

// --- Core functions ---

export async function loadInterestProfile(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(INTEREST_PROFILE_KEY);
    if (raw) {
      profile = JSON.parse(raw);
    }
  } catch (e) {
    console.warn('[interest-model] failed to load profile:', e);
  }
}

export async function saveInterestProfile(): Promise<void> {
  try {
    profile.updated_at = Date.now();
    await AsyncStorage.setItem(INTEREST_PROFILE_KEY, JSON.stringify(profile));
  } catch (e) {
    console.warn('[interest-model] failed to save profile:', e);
  }
}

export function getInterestProfile(): InterestProfile {
  return profile;
}

function ensureTopic(key: string, level: 'broad' | 'specific' | 'entity', parent?: string): TopicInterest {
  if (!profile.topics[key]) {
    profile.topics[key] = {
      topic: key,
      level,
      parent,
      positive_signals: 0,
      negative_signals: 0,
      interest_score: 0.5,
      last_signal: 0,
      articles_seen: 0,
    };
  }
  return profile.topics[key];
}

export function recordSignal(action: SignalAction, article: Article): void {
  const config = SIGNAL_WEIGHTS[action];
  const topics = article.interest_topics || [];

  for (const topic of topics) {
    // Signal on specific topic
    const specificKey = topic.specific;
    const specificEntry = ensureTopic(specificKey, 'specific', topic.broad);
    applySignal(specificEntry, config.positive, config.weight);

    // Signal on entity if present
    if (topic.entity) {
      const entityKey = topic.entity.toLowerCase().replace(/\s+/g, '-');
      const entityEntry = ensureTopic(entityKey, 'entity', specificKey);
      applySignal(entityEntry, config.positive, config.weight);
    }

    // Propagate to broad parent at reduced weight
    const broadEntry = ensureTopic(topic.broad, 'broad');
    applySignal(broadEntry, config.positive, config.weight * PARENT_SIGNAL_RATIO);
  }

  // Also signal on article.topics (the simple string array)
  for (const topicStr of article.topics || []) {
    const key = topicStr.toLowerCase().replace(/\s+/g, '-');
    const entry = ensureTopic(key, 'broad');
    applySignal(entry, config.positive, config.weight * 0.5);
  }

  logEvent('interest_signal', { action, article_id: article.id, topic_count: topics.length });
  saveInterestProfile();
}

function applySignal(entry: TopicInterest, positive: boolean, weight: number): void {
  if (positive) {
    entry.positive_signals += weight;
  } else {
    entry.negative_signals += weight;
  }
  entry.last_signal = Date.now();
  entry.interest_score = computeScore(entry);
}

export function markArticleSeen(article: Article): void {
  const topics = article.interest_topics || [];
  for (const topic of topics) {
    const entry = ensureTopic(topic.specific, 'specific', topic.broad);
    entry.articles_seen++;
    if (topic.entity) {
      const entityKey = topic.entity.toLowerCase().replace(/\s+/g, '-');
      const entityEntry = ensureTopic(entityKey, 'entity', topic.specific);
      entityEntry.articles_seen++;
    }
  }
}

// --- Scoring ---

function computeScore(entry: TopicInterest): number {
  const now = Date.now();
  const daysSinceSignal = (now - entry.last_signal) / (1000 * 60 * 60 * 24);
  const decay = Math.pow(0.5, daysSinceSignal / DECAY_HALF_LIFE_DAYS);

  const totalSignals = entry.positive_signals + entry.negative_signals;
  if (totalSignals === 0) return 0.5;

  const rawScore = entry.positive_signals / totalSignals;
  // Blend toward 0.5 for low signal counts (Bayesian smoothing)
  const confidence = Math.min(totalSignals / 10, 1);
  const smoothed = 0.5 * (1 - confidence) + rawScore * confidence;

  return smoothed * decay;
}

// --- Feed ranking ---

export function scoreArticle(article: Article, recentTopics: string[]): number {
  const interestMatch = computeInterestMatch(article);
  const freshness = computeFreshness(article);
  const discoveryBonus = computeDiscoveryBonus(article);
  const variety = computeVarietyPenalty(article, recentTopics);

  return (
    interestMatch * 0.40 +
    freshness * 0.25 +
    discoveryBonus * 0.20 +
    variety * 0.15
  );
}

function computeInterestMatch(article: Article): number {
  const topics = article.interest_topics || [];
  if (topics.length === 0) {
    // Fall back to article.topics string array
    const scores = (article.topics || []).map(t => {
      const key = t.toLowerCase().replace(/\s+/g, '-');
      return profile.topics[key]?.interest_score ?? 0.5;
    });
    return scores.length > 0 ? Math.max(...scores) : 0.5;
  }

  const scores = topics.map(t => {
    const specificScore = profile.topics[t.specific]?.interest_score ?? 0.5;
    const broadScore = profile.topics[t.broad]?.interest_score ?? 0.5;
    return Math.max(specificScore, broadScore * 0.7);
  });
  return Math.max(...scores);
}

function computeFreshness(article: Article): number {
  if (!article.date) return 0.5;
  const ageMs = Date.now() - new Date(article.date).getTime();
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  // Sigmoid decay: 1.0 at 0 days, 0.5 at 7 days, ~0.1 at 30 days
  return 1 / (1 + Math.pow(ageDays / 7, 2));
}

function computeDiscoveryBonus(article: Article): number {
  const topics = article.interest_topics || [];
  if (topics.length === 0) return 0.5;

  const unknownCount = topics.filter(t => {
    const entry = profile.topics[t.specific];
    return !entry || entry.articles_seen < 2;
  }).length;

  return unknownCount / topics.length;
}

function computeVarietyPenalty(article: Article, recentTopics: string[]): number {
  if (recentTopics.length === 0) return 1.0;

  const articleTopics = (article.interest_topics || []).map(t => t.specific);
  const overlap = articleTopics.filter(t => recentTopics.includes(t)).length;

  if (overlap === 0) return 1.0;
  // Penalize: 0.7 for 1 overlap, 0.4 for 2+
  return Math.max(0.3, 1.0 - overlap * 0.3);
}

// --- Debug / introspection ---

export function getTopTopics(n: number = 10): TopicInterest[] {
  return Object.values(profile.topics)
    .sort((a, b) => b.interest_score - a.interest_score)
    .slice(0, n);
}

export function getTopicScore(topicKey: string): number {
  return profile.topics[topicKey]?.interest_score ?? 0.5;
}

export function getTotalSignalCount(): number {
  return Object.values(profile.topics).reduce(
    (sum, t) => sum + t.positive_signals + t.negative_signals, 0
  );
}
