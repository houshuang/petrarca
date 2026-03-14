import AsyncStorage from '@react-native-async-storage/async-storage';
import { logEvent } from './logger';
import type {
  KnowledgeIndex,
  DeltaReport,
  ClaimKnowledgeEntry,
  ClaimClassification,
  ParagraphDimming,
  ArticleNovelty,
  NoveltyClassification,
} from './types';

const LEDGER_KEY = '@petrarca/knowledge_ledger';

const KNOWN_THRESHOLD = 0.78;
const EXTENDS_THRESHOLD = 0.68;
const FORGOTTEN_THRESHOLD = 0.3;

const STABILITY_SKIM = 9;
const STABILITY_READ = 30;
const STABILITY_HIGHLIGHT = 60;
const REINFORCEMENT_FACTOR = 2.5;

// --- Module state ---

let knowledgeIndex: KnowledgeIndex | null = null;
let knowledgeLedger: Record<string, ClaimKnowledgeEntry> = {};
let similarityLookup: Map<string, Array<{ target: string; score: number }>> = new Map();

// --- FSRS Decay ---

function getRetrievability(entry: ClaimKnowledgeEntry): number {
  const daysSince = (Date.now() - entry.first_seen_at) / (1000 * 60 * 60 * 24);
  return Math.exp(-daysSince / entry.stability_days);
}

// --- Init ---

export async function initKnowledgeEngine(cachedIndex: KnowledgeIndex | null): Promise<void> {
  if (cachedIndex) {
    knowledgeIndex = cachedIndex;
    buildSimilarityLookup();
    logEvent('knowledge_index_loaded', {
      claims: knowledgeIndex.stats.total_claims,
      similarities: knowledgeIndex.stats.total_similarity_pairs,
    });
  }

  try {
    const raw = await AsyncStorage.getItem(LEDGER_KEY);
    if (raw) {
      knowledgeLedger = JSON.parse(raw);
    }
  } catch (e) {
    console.warn('[knowledge-engine] failed to load ledger:', e);
  }

  logEvent('knowledge_engine_init', {
    index_loaded: !!knowledgeIndex,
    ledger_size: Object.keys(knowledgeLedger).length,
  });
}

function buildSimilarityLookup(): void {
  similarityLookup = new Map();
  if (!knowledgeIndex) return;

  for (const { a, b, score } of knowledgeIndex.similarities) {
    if (!similarityLookup.has(a)) similarityLookup.set(a, []);
    if (!similarityLookup.has(b)) similarityLookup.set(b, []);
    similarityLookup.get(a)!.push({ target: b, score });
    similarityLookup.get(b)!.push({ target: a, score });
  }
}

// --- Getters ---

export function isKnowledgeReady(): boolean {
  return knowledgeIndex !== null;
}

export function getKnowledgeIndex(): KnowledgeIndex | null {
  return knowledgeIndex;
}

// --- LLM Verdict Lookup ---

function getLlmVerdict(claimA: string, claimB: string): 'ENTAILS' | 'EXTENDS' | 'UNRELATED' | null {
  if (!knowledgeIndex?.llm_verdicts) return null;
  return knowledgeIndex.llm_verdicts[`${claimA}::${claimB}`]
    ?? knowledgeIndex.llm_verdicts[`${claimB}::${claimA}`]
    ?? null;
}

// --- Claim Classification ---

export function classifyArticleClaims(articleId: string): ClaimClassification[] {
  if (!knowledgeIndex) return [];

  const claimIds = knowledgeIndex.article_claims[articleId];
  if (!claimIds) return [];

  const classifications: ClaimClassification[] = [];

  for (const claimId of claimIds) {
    const claim = knowledgeIndex.claims[claimId];
    if (!claim) continue;

    let classification: NoveltyClassification = 'NEW';
    let highestScore = 0;

    const similars = similarityLookup.get(claimId) || [];
    for (const { target, score } of similars) {
      if (score <= highestScore) continue;

      const ledgerEntry = knowledgeLedger[target];
      if (!ledgerEntry) continue;

      const retrievability = getRetrievability(ledgerEntry);
      if (retrievability < FORGOTTEN_THRESHOLD) continue;

      highestScore = score;
      if (score >= KNOWN_THRESHOLD) {
        classification = 'KNOWN';
      } else if (score >= EXTENDS_THRESHOLD) {
        const verdict = getLlmVerdict(claimId, target);
        if (verdict === 'UNRELATED') {
          classification = 'NEW';
        } else if (verdict === 'ENTAILS') {
          classification = 'KNOWN';
        } else {
          classification = 'EXTENDS';
        }
      }
    }

    // Also check if this exact claim is in the ledger
    if (knowledgeLedger[claimId]) {
      const retrievability = getRetrievability(knowledgeLedger[claimId]);
      if (retrievability >= FORGOTTEN_THRESHOLD) {
        highestScore = Math.max(highestScore, 1.0);
        classification = 'KNOWN';
      }
    }

    classifications.push({
      claim_id: claimId,
      text: claim.text,
      classification,
      similarity_score: highestScore,
      source_paragraphs: claim.source_paragraphs,
      claim_type: claim.claim_type,
    });
  }

  classifications.sort((a, b) => {
    const aMin = a.source_paragraphs.length > 0 ? Math.min(...a.source_paragraphs) : Infinity;
    const bMin = b.source_paragraphs.length > 0 ? Math.min(...b.source_paragraphs) : Infinity;
    return aMin - bMin;
  });

  return classifications;
}

// --- Paragraph Dimming ---

export function computeParagraphDimming(articleId: string): ParagraphDimming[] {
  const classifications = classifyArticleClaims(articleId);
  if (classifications.length === 0) return [];

  const paragraphClaims = new Map<number, ClaimClassification[]>();
  for (const c of classifications) {
    for (const p of c.source_paragraphs) {
      if (!paragraphClaims.has(p)) paragraphClaims.set(p, []);
      paragraphClaims.get(p)!.push(c);
    }
  }

  const result: ParagraphDimming[] = [];

  for (const [paragraphIndex, claims] of paragraphClaims) {
    const counts = { new: 0, extends: 0, known: 0 };
    for (const c of claims) {
      if (c.classification === 'NEW') counts.new++;
      else if (c.classification === 'EXTENDS') counts.extends++;
      else counts.known++;
    }

    const total = counts.new + counts.extends + counts.known;
    const newRatio = counts.new / total;
    const extendsRatio = counts.extends / total;

    let opacity: number;
    let novelty: ParagraphDimming['novelty'];

    if (counts.known === total) {
      opacity = 0.55;
      novelty = 'familiar';
    } else if (counts.new === total) {
      opacity = 1.0;
      novelty = 'novel';
    } else {
      opacity = 0.55 + 0.45 * (newRatio + extendsRatio * 0.5);
      if (newRatio >= 0.7) novelty = 'mostly_novel';
      else if (newRatio + extendsRatio >= 0.5) novelty = 'mixed';
      else novelty = 'mostly_familiar';
    }

    result.push({ paragraph_index: paragraphIndex, opacity, novelty, claim_counts: counts });
  }

  result.sort((a, b) => a.paragraph_index - b.paragraph_index);
  return result;
}

// --- Article Novelty ---

export function getArticleNovelty(articleId: string): ArticleNovelty {
  const classifications = classifyArticleClaims(articleId);

  const counts = { new: 0, extends: 0, known: 0 };
  for (const c of classifications) {
    if (c.classification === 'NEW') counts.new++;
    else if (c.classification === 'EXTENDS') counts.extends++;
    else counts.known++;
  }

  const total = classifications.length;
  const noveltyRatio = total > 0 ? counts.new / total : 1;

  // Curiosity score: Gaussian peak at 70% novelty
  const gaussian = Math.exp(-Math.pow(noveltyRatio - 0.7, 2) / (2 * Math.pow(0.15, 2)));
  const contextBonus = Math.min(1.0, (1 - noveltyRatio) * 3);
  const sizeFactor = Math.min(1.0, total / 15);

  const curiosityScore = gaussian * 0.6 + contextBonus * 0.3 + sizeFactor * 0.2;

  return {
    article_id: articleId,
    total_claims: total,
    new_claims: counts.new,
    extends_claims: counts.extends,
    known_claims: counts.known,
    novelty_ratio: noveltyRatio,
    curiosity_score: Math.min(1.0, curiosityScore),
  };
}

// --- Knowledge Ledger Updates ---

async function saveLedger(): Promise<void> {
  try {
    await AsyncStorage.setItem(LEDGER_KEY, JSON.stringify(knowledgeLedger));
  } catch (e) {
    console.warn('[knowledge-engine] failed to save ledger:', e);
  }
}

export function markArticleEncountered(
  articleId: string,
  engagement: 'skim' | 'read' | 'highlight',
): void {
  if (!knowledgeIndex) return;

  const claimIds = knowledgeIndex.article_claims[articleId];
  if (!claimIds) return;

  const stabilityMap = { skim: STABILITY_SKIM, read: STABILITY_READ, highlight: STABILITY_HIGHLIGHT };
  const stability = stabilityMap[engagement];
  const now = Date.now();

  for (const claimId of claimIds) {
    const existing = knowledgeLedger[claimId];
    if (existing) {
      existing.stability_days = Math.min(existing.stability_days * REINFORCEMENT_FACTOR, 365);
      if (engagement === 'highlight' || engagement === 'read') {
        existing.engagement = engagement;
      }
    } else {
      knowledgeLedger[claimId] = {
        claim_id: claimId,
        first_seen_at: now,
        article_id: articleId,
        engagement,
        stability_days: stability,
      };
    }
  }

  logEvent('knowledge_article_encountered', {
    article_id: articleId,
    engagement,
    claims_count: claimIds.length,
  });

  saveLedger();
}

export function markArticleReadUpTo(
  articleId: string,
  maxParagraphIndex: number,
  engagement: 'skim' | 'read',
): void {
  if (!knowledgeIndex) return;

  const claimIds = knowledgeIndex.article_claims[articleId];
  if (!claimIds) return;

  const stabilityMap = { skim: STABILITY_SKIM, read: STABILITY_READ };
  const stability = stabilityMap[engagement];
  const now = Date.now();

  let readCount = 0;
  let skippedCount = 0;

  for (const claimId of claimIds) {
    const claim = knowledgeIndex.claims[claimId];
    if (!claim) continue;

    const inViewedRange = claim.source_paragraphs.some(p => p <= maxParagraphIndex);
    if (!inViewedRange) {
      skippedCount++;
      continue;
    }

    readCount++;
    const existing = knowledgeLedger[claimId];
    if (existing) {
      existing.stability_days = Math.min(existing.stability_days * REINFORCEMENT_FACTOR, 365);
      if (engagement === 'read') {
        existing.engagement = engagement;
      }
    } else {
      knowledgeLedger[claimId] = {
        claim_id: claimId,
        first_seen_at: now,
        article_id: articleId,
        engagement,
        stability_days: stability,
      };
    }
  }

  logEvent('knowledge_article_read_up_to', {
    article_id: articleId,
    engagement,
    max_paragraph: maxParagraphIndex,
    claims_read: readCount,
    claims_skipped: skippedCount,
  });

  saveLedger();
}

export function getArticleParagraphCount(articleId: string): number {
  if (!knowledgeIndex) return 0;
  const claimIds = knowledgeIndex.article_claims[articleId];
  if (!claimIds) return 0;

  let maxPara = 0;
  for (const claimId of claimIds) {
    const claim = knowledgeIndex.claims[claimId];
    if (!claim) continue;
    for (const p of claim.source_paragraphs) {
      if (p > maxPara) maxPara = p;
    }
  }
  return maxPara + 1;
}

export function markClaimEncountered(
  claimId: string,
  engagement: 'skim' | 'read' | 'highlight',
  articleId: string = '',
): void {
  const stabilityMap = { skim: STABILITY_SKIM, read: STABILITY_READ, highlight: STABILITY_HIGHLIGHT };
  const stability = stabilityMap[engagement];
  const now = Date.now();

  const existing = knowledgeLedger[claimId];
  if (existing) {
    existing.stability_days = Math.min(existing.stability_days * REINFORCEMENT_FACTOR, 365);
    if (engagement === 'highlight' || engagement === 'read') {
      existing.engagement = engagement;
    }
  } else {
    knowledgeLedger[claimId] = {
      claim_id: claimId,
      first_seen_at: now,
      article_id: articleId,
      engagement,
      stability_days: stability,
    };
  }

  saveLedger();
}

export function markClaimsEncountered(
  claimIds: string[],
  engagement: 'skim' | 'read' | 'highlight',
): number {
  const stabilityMap = { skim: STABILITY_SKIM, read: STABILITY_READ, highlight: STABILITY_HIGHLIGHT };
  const stability = stabilityMap[engagement];
  const now = Date.now();
  let count = 0;

  for (const claimId of claimIds) {
    const existing = knowledgeLedger[claimId];
    if (existing) {
      existing.stability_days = Math.min(existing.stability_days * REINFORCEMENT_FACTOR, 365);
      if (engagement === 'highlight' || engagement === 'read') {
        existing.engagement = engagement;
      }
    } else {
      knowledgeLedger[claimId] = {
        claim_id: claimId,
        first_seen_at: now,
        article_id: '',
        engagement,
        stability_days: stability,
      };
    }
    count++;
  }

  logEvent('knowledge_claims_bulk_encountered', {
    engagement,
    claims_count: count,
  });

  saveLedger();
  return count;
}

export function markClaimHighlighted(claimId: string): void {
  const existing = knowledgeLedger[claimId];
  if (existing) {
    existing.engagement = 'highlight';
    existing.stability_days = Math.max(existing.stability_days, STABILITY_HIGHLIGHT);
  } else {
    knowledgeLedger[claimId] = {
      claim_id: claimId,
      first_seen_at: Date.now(),
      article_id: '',
      engagement: 'highlight',
      stability_days: STABILITY_HIGHLIGHT,
    };
  }

  logEvent('knowledge_claim_highlighted', { claim_id: claimId });
  saveLedger();
}

// --- Cross-Article Connections ---

export interface CrossArticleConnection {
  articleId: string;
  sharedClaimCount: number;
  maxSimilarity: number;
  claimPairs: Array<{
    localClaimId: string;
    remoteClaimId: string;
    localText: string;
    remoteText: string;
    score: number;
    localParagraphs: number[];
  }>;
}

export function getCrossArticleConnections(
  articleId: string,
  threshold: number = 0.78,
  maxResults: number = 5,
): CrossArticleConnection[] {
  if (!knowledgeIndex) return [];

  const claimIds = knowledgeIndex.article_claims[articleId];
  if (!claimIds) return [];

  const connectionMap = new Map<string, CrossArticleConnection>();

  for (const claimId of claimIds) {
    const similars = similarityLookup.get(claimId) || [];
    for (const { target, score } of similars) {
      if (score < threshold) continue;

      const targetClaim = knowledgeIndex.claims[target];
      if (!targetClaim || targetClaim.article_id === articleId) continue;

      const targetArticleId = targetClaim.article_id;

      if (!connectionMap.has(targetArticleId)) {
        connectionMap.set(targetArticleId, {
          articleId: targetArticleId,
          sharedClaimCount: 0,
          maxSimilarity: 0,
          claimPairs: [],
        });
      }

      const conn = connectionMap.get(targetArticleId)!;
      conn.sharedClaimCount++;
      conn.maxSimilarity = Math.max(conn.maxSimilarity, score);

      const localClaim = knowledgeIndex.claims[claimId];
      conn.claimPairs.push({
        localClaimId: claimId,
        remoteClaimId: target,
        localText: localClaim?.text || '',
        remoteText: targetClaim.text,
        score,
        localParagraphs: localClaim?.source_paragraphs || [],
      });
    }
  }

  return Array.from(connectionMap.values())
    .sort((a, b) => b.sharedClaimCount - a.sharedClaimCount)
    .slice(0, maxResults);
}

export function getParagraphConnections(
  articleId: string,
  threshold: number = 0.78,
): Map<number, Array<{ articleId: string; claimText: string }>> {
  const connections = getCrossArticleConnections(articleId, threshold, 10);
  const paragraphMap = new Map<number, Array<{ articleId: string; claimText: string }>>();

  for (const conn of connections) {
    for (const pair of conn.claimPairs) {
      for (const paraIdx of pair.localParagraphs) {
        if (!paragraphMap.has(paraIdx)) paragraphMap.set(paraIdx, []);
        const existing = paragraphMap.get(paraIdx)!;
        if (!existing.some(e => e.articleId === conn.articleId)) {
          existing.push({ articleId: conn.articleId, claimText: pair.remoteText });
        }
      }
    }
  }

  return paragraphMap;
}

// --- Delta Reports ---

export function getDeltaReports(): Record<string, DeltaReport> {
  if (!knowledgeIndex) return {};
  return knowledgeIndex.delta_reports;
}

export function getDeltaReportForTopic(topic: string): DeltaReport | null {
  if (!knowledgeIndex) return null;
  return knowledgeIndex.delta_reports[topic] || null;
}

// --- Stats ---

export function getKnowledgeStats(): {
  total_known: number;
  total_encountered: number;
  topics_covered: string[];
} {
  const entries = Object.values(knowledgeLedger);
  const activeEntries = entries.filter(e => getRetrievability(e) >= FORGOTTEN_THRESHOLD);

  const topicSet = new Set<string>();
  if (knowledgeIndex) {
    for (const entry of activeEntries) {
      const claim = knowledgeIndex.claims[entry.claim_id];
      if (claim) {
        for (const topic of claim.topics) {
          topicSet.add(topic);
        }
      }
    }
  }

  return {
    total_known: activeEntries.length,
    total_encountered: entries.length,
    topics_covered: Array.from(topicSet).sort(),
  };
}
