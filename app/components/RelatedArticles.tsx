import { useState, useMemo, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { Article } from '../data/types';
import { getArticles, getReadingState } from '../data/store';
import { getKnowledgeIndex } from '../data/knowledge-engine';
import { isQueued, addToQueue } from '../data/queue';
import { logEvent } from '../data/logger';
import { getDisplayTitle } from '../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../design/tokens';
import * as Haptics from 'expo-haptics';

const MAX_PER_GROUP = 3;

interface RelatedGroup {
  key: string;
  label: string;
  articles: Article[];
}

function extractHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

function findSameTopicArticles(article: Article, allArticles: Article[]): Article[] {
  const topics = article.interest_topics || [];
  if (topics.length === 0) return [];

  const topicSet = new Set(topics.map(t => t.specific));
  const broadSet = new Set(topics.map(t => t.broad));

  const scored: { article: Article; overlap: number }[] = [];
  for (const other of allArticles) {
    if (other.id === article.id) continue;
    const otherTopics = other.interest_topics || [];
    if (otherTopics.length === 0) continue;

    let overlap = 0;
    for (const t of otherTopics) {
      if (topicSet.has(t.specific)) overlap += 2;
      else if (broadSet.has(t.broad)) overlap += 1;
    }
    if (overlap > 0) scored.push({ article: other, overlap });
  }

  scored.sort((a, b) => b.overlap - a.overlap);
  return scored.slice(0, MAX_PER_GROUP).map(s => s.article);
}

function findSharedConceptArticles(article: Article, allArticles: Article[]): Article[] {
  const ki = getKnowledgeIndex();
  if (!ki) return [];

  const matrix = ki.article_novelty_matrix[article.id];
  if (!matrix) return [];

  const articleMap = new Map(allArticles.map(a => [a.id, a]));
  const scored: { article: Article; sharedClaims: number }[] = [];

  for (const [otherId, counts] of Object.entries(matrix)) {
    if (otherId === article.id) continue;
    const other = articleMap.get(otherId);
    if (!other) continue;
    // "extends" and "known" both indicate shared knowledge
    const shared = counts.extends + counts.known;
    if (shared > 0) scored.push({ article: other, sharedClaims: shared });
  }

  scored.sort((a, b) => b.sharedClaims - a.sharedClaims);
  return scored.slice(0, MAX_PER_GROUP).map(s => s.article);
}

function findSameSourceArticles(article: Article, allArticles: Article[]): Article[] {
  const hostname = article.hostname || extractHostname(article.source_url);
  if (!hostname) return [];

  const results: Article[] = [];
  for (const other of allArticles) {
    if (other.id === article.id) continue;
    const otherHostname = other.hostname || extractHostname(other.source_url);
    if (otherHostname === hostname) {
      results.push(other);
      if (results.length >= MAX_PER_GROUP) break;
    }
  }
  return results;
}

function ArticleRow({ article, group, sourceArticleId }: {
  article: Article;
  group: string;
  sourceArticleId: string;
}) {
  const router = useRouter();
  const readingState = getReadingState(article.id);
  const isRead = readingState.status === 'read';
  const [queued, setQueued] = useState(() => isQueued(article.id));

  const handleTitlePress = useCallback(() => {
    logEvent('related_article_tap', {
      source_article_id: sourceArticleId,
      target_article_id: article.id,
      group,
    });
    router.push({ pathname: '/reader', params: { id: article.id } });
  }, [article.id, sourceArticleId, group, router]);

  const handleQueuePress = useCallback(async () => {
    if (isRead || queued) return;
    await addToQueue(article.id);
    setQueued(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    logEvent('related_article_queue', { article_id: article.id, group });
  }, [article.id, isRead, queued, group]);

  const statusLabel = isRead ? '\u2713 Read' : queued ? '\u2713 Queued' : '+ Queue';
  const statusStyle = isRead || queued ? styles.actionMuted : styles.actionActive;

  return (
    <View style={styles.articleRow}>
      <Pressable style={styles.articleTitleArea} onPress={handleTitlePress}>
        <Text style={styles.articleTitle} numberOfLines={2}>
          {getDisplayTitle(article)}
        </Text>
        <Text style={styles.articleMeta}>
          {article.hostname || extractHostname(article.source_url)}
          {article.estimated_read_minutes ? ` \u00B7 ${article.estimated_read_minutes} min` : ''}
        </Text>
      </Pressable>
      <Pressable
        style={styles.actionButton}
        onPress={handleQueuePress}
        disabled={isRead || queued}
      >
        <Text style={statusStyle}>{statusLabel}</Text>
      </Pressable>
    </View>
  );
}

export default function RelatedArticles({ article }: { article: Article }) {
  const allArticles = useMemo(() => getArticles(), []);

  const groups = useMemo<RelatedGroup[]>(() => {
    const result: RelatedGroup[] = [];

    const sameTopic = findSameTopicArticles(article, allArticles);
    if (sameTopic.length > 0) {
      result.push({ key: 'same_topic', label: 'SAME TOPIC', articles: sameTopic });
    }

    const sharedConcepts = findSharedConceptArticles(article, allArticles);
    // Deduplicate against same topic
    const sameTopicIds = new Set(sameTopic.map(a => a.id));
    const uniqueShared = sharedConcepts.filter(a => !sameTopicIds.has(a.id));
    if (uniqueShared.length > 0) {
      result.push({ key: 'shared_concepts', label: 'SHARED CONCEPTS', articles: uniqueShared.slice(0, MAX_PER_GROUP) });
    }

    const sameSource = findSameSourceArticles(article, allArticles);
    // Deduplicate against previous groups
    const usedIds = new Set([...sameTopic, ...uniqueShared].map(a => a.id));
    const uniqueSource = sameSource.filter(a => !usedIds.has(a.id));
    if (uniqueSource.length > 0) {
      result.push({ key: 'same_source', label: 'FROM SAME SOURCE', articles: uniqueSource.slice(0, MAX_PER_GROUP) });
    }

    return result;
  }, [article.id, allArticles]);

  if (groups.length === 0) return null;

  return (
    <View style={styles.container}>
      {/* Double rule separator */}
      <View style={styles.doubleRuleTop} />
      <View style={{ height: layout.doubleRuleGap }} />
      <View style={styles.doubleRuleBottom} />

      {/* Section header */}
      <Text style={styles.sectionHeader}>{'\u2726'} RELATED READING</Text>

      {groups.map((group) => (
        <View key={group.key} style={styles.group}>
          <Text style={styles.groupLabel}>{group.label}</Text>
          {group.articles.map((a) => (
            <ArticleRow
              key={a.id}
              article={a}
              group={group.key}
              sourceArticleId={article.id}
            />
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 32,
    paddingBottom: 20,
  },

  // Double rule
  doubleRuleTop: {
    height: layout.doubleRuleTop,
    backgroundColor: colors.rubric,
  },
  doubleRuleBottom: {
    height: layout.doubleRuleBottom,
    backgroundColor: colors.rule,
  },

  // Section header
  sectionHeader: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    color: colors.rubric,
    marginTop: 16,
    marginBottom: 20,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // Group
  group: {
    marginBottom: 20,
  },
  groupLabel: {
    fontFamily: fonts.ui,
    fontSize: 11,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: 10,
  },

  // Article row
  articleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
    gap: 12,
  },
  articleTitleArea: {
    flex: 1,
    minHeight: layout.touchTarget,
    justifyContent: 'center',
  },
  articleTitle: {
    fontFamily: fonts.body,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textPrimary,
  },
  articleMeta: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginTop: 2,
  },

  // Action button
  actionButton: {
    minWidth: 72,
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    alignItems: 'flex-end',
    paddingLeft: 4,
  },
  actionActive: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
  },
  actionMuted: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
});
