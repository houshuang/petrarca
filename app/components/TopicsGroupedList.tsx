import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import {
  getSyntheses, getArticles, getArticleById, getReadingState,
  isSynthesisCompleted, isDismissed, recordInterestSignal,
} from '../data/store';
import { getDisplayTitle, displayTopic } from '../lib/display-utils';
import { Article, TopicSynthesis } from '../data/types';

interface TopicsGroupedListProps {
  topicFilter?: string;
}

export default function TopicsGroupedList({ topicFilter }: TopicsGroupedListProps) {
  const router = useRouter();
  const allSyntheses = useMemo(() => getSyntheses(), []);
  const allArticles = useMemo(() => getArticles(), []);

  // Build set of all article IDs covered by any synthesis
  const coveredArticleIds = useMemo(() => {
    const ids = new Set<string>();
    for (const s of allSyntheses) {
      for (const id of s.article_ids) ids.add(id);
    }
    return ids;
  }, [allSyntheses]);

  // Filter syntheses by topic if active
  const filteredSyntheses = useMemo(() => {
    let synths = allSyntheses.sort((a, b) => b.total_articles - a.total_articles);
    if (topicFilter) {
      const filter = topicFilter.toLowerCase();
      // Keep syntheses whose label or any article's topics match the filter
      const articleTopicMap = new Map<string, string[]>();
      for (const a of allArticles) {
        const topics = (a.interest_topics || []).map(t => t.broad);
        const fallback = topics.length > 0 ? topics : a.topics;
        articleTopicMap.set(a.id, fallback);
      }
      synths = synths.filter(s => {
        if (s.label.toLowerCase().includes(filter)) return true;
        return s.article_ids.some(id => {
          const topics = articleTopicMap.get(id) || [];
          return topics.some(t => t.toLowerCase().includes(filter));
        });
      });
    }
    return synths;
  }, [allSyntheses, allArticles, topicFilter]);

  // Uncovered articles (not in any synthesis), grouped by topic
  const uncoveredGroups = useMemo(() => {
    const uncovered = allArticles.filter(a => {
      if (coveredArticleIds.has(a.id)) return false;
      if (isDismissed(a.id)) return false;
      const state = getReadingState(a.id);
      if (state && state.status === 'read') return false;
      return true;
    });

    if (topicFilter) {
      const filter = topicFilter.toLowerCase();
      const filtered = uncovered.filter(a => {
        const topics = (a.interest_topics || []).map(t => t.broad);
        const fallback = topics.length > 0 ? topics : a.topics;
        return fallback.some(t => t.toLowerCase().includes(filter));
      });
      return groupByTopic(filtered);
    }
    return groupByTopic(uncovered);
  }, [allArticles, coveredArticleIds, topicFilter]);

  if (filteredSyntheses.length === 0 && uncoveredGroups.length === 0) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>No topics found</Text>
      </View>
    );
  }

  const isWeb = Platform.OS === 'web';

  return (
    <View style={styles.container}>
      {/* Synthesis cards — 2-col grid on web */}
      {filteredSyntheses.length > 0 && (
        <View style={[styles.synthesesSection, isWeb && gridStyles.grid] as any}>
          {filteredSyntheses.map(s => (
            <RichSynthesisCard key={s.cluster_id} synthesis={s} />
          ))}
        </View>
      )}

      {/* Uncovered articles */}
      {uncoveredGroups.length > 0 && (
        <View style={styles.uncoveredSection}>
          {filteredSyntheses.length > 0 && (
            <Text style={styles.sectionHeader}>
              <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
              Other Articles
            </Text>
          )}
          {uncoveredGroups.map(group => (
            <TopicGroup key={group.topic} topic={group.topic} articles={group.articles} />
          ))}
        </View>
      )}
    </View>
  );
}

function groupByTopic(articles: Article[]): Array<{ topic: string; articles: Article[] }> {
  const groups = new Map<string, Article[]>();
  for (const a of articles) {
    const topics = (a.interest_topics || []).map(t => t.broad);
    const fallback = topics.length > 0 ? topics : a.topics.slice(0, 2);
    for (const t of fallback) {
      if (!groups.has(t)) groups.set(t, []);
      groups.get(t)!.push(a);
    }
  }
  return [...groups.entries()]
    .map(([topic, arts]) => ({ topic, articles: arts }))
    .sort((a, b) => b.articles.length - a.articles.length);
}

// --- Helpers ---

function extractPreview(markdown: string, maxLen = 200): string {
  for (const line of markdown.split('\n')) {
    const t = line.trim();
    if (t && !t.startsWith('#') && !t.startsWith('>') && !t.startsWith('<!--') && !t.startsWith('- ') && !t.startsWith('*') && t.length > 40) {
      const clean = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\*\*/g, '');
      return clean.length > maxLen ? clean.slice(0, maxLen).replace(/\s\S*$/, '') + '\u2026' : clean;
    }
  }
  return '';
}

function extractTensionLabels(tensions: TopicSynthesis['tensions']): string[] {
  return tensions.slice(0, 3).map(t =>
    typeof t === 'string' ? (t.length > 60 ? t.slice(0, 60) + '\u2026' : t) : t.label
  );
}

// --- Rich Synthesis Card ---

function RichSynthesisCard({ synthesis }: { synthesis: TopicSynthesis }) {
  const router = useRouter();
  const completed = isSynthesisCompleted(synthesis.cluster_id);
  const [hovered, setHovered] = useState(false);

  const preview = useMemo(() => extractPreview(synthesis.synthesis_markdown, 220), [synthesis]);
  const tensionLabels = useMemo(() => extractTensionLabels(synthesis.tensions), [synthesis]);
  const articleTitles = useMemo(() => {
    return synthesis.article_ids.slice(0, 4).map(id => {
      const a = getArticleById(id);
      return a ? getDisplayTitle(a) : null;
    }).filter(Boolean) as string[];
  }, [synthesis]);
  const remaining = synthesis.article_ids.length - articleTitles.length;

  return (
    <Pressable
      style={[
        richStyles.card,
        completed && richStyles.cardCompleted,
        hovered && richStyles.cardHovered,
      ] as any}
      onPress={() => {
        logEvent('synthesis_card_tap', { cluster_id: synthesis.cluster_id, label: synthesis.label });
        router.push({ pathname: '/synthesis-reader', params: { clusterId: synthesis.cluster_id } });
      }}
      {...(Platform.OS === 'web' ? {
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false),
      } as any : {})}
    >
      <Text style={richStyles.title} numberOfLines={2}>{synthesis.label}</Text>

      {preview ? (
        <Text style={richStyles.preview} numberOfLines={3}>{preview}</Text>
      ) : null}

      {tensionLabels.length > 0 && (
        <View style={richStyles.tensionRow}>
          <Text style={richStyles.tensionIcon}>{'\u26A1'}</Text>
          <Text style={richStyles.tensionText} numberOfLines={2}>
            {tensionLabels.join(' \u00b7 ')}
          </Text>
        </View>
      )}

      <View style={richStyles.sourcesSection}>
        {articleTitles.map((title, i) => (
          <Text key={i} style={richStyles.sourceTitle} numberOfLines={1}>
            {'\u00b7'} {title}
          </Text>
        ))}
        {remaining > 0 && (
          <Text style={richStyles.sourceMore}>+{remaining} more</Text>
        )}
      </View>

      <View style={richStyles.footer}>
        {completed ? (
          <Text style={richStyles.completedBadge}>{'\u2713'} Read</Text>
        ) : (
          <Text style={richStyles.readLink}>Read {'\u2192'}</Text>
        )}
        <Text style={richStyles.articleCount}>{synthesis.total_articles} articles</Text>
      </View>
    </Pressable>
  );
}

// --- Topic Group (for uncovered articles) ---

function TopicGroup({ topic, articles }: { topic: string; articles: Article[] }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const visibleCount = expanded ? articles.length : Math.min(3, articles.length);
  const hasMore = articles.length > 3;

  return (
    <View style={styles.group}>
      <Text style={styles.groupHeader}>
        <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
        {displayTopic(topic)}
      </Text>
      <View style={styles.groupArticles}>
        {articles.slice(0, visibleCount).map(article => (
          <Pressable
            key={article.id}
            style={styles.articleRow}
            onPress={() => {
              logEvent('topic_group_article_tap', { article_id: article.id, topic });
              recordInterestSignal('open_article', article.id);
              router.push({ pathname: '/reader', params: { id: article.id } });
            }}
          >
            <View style={styles.treeLine} />
            <View style={styles.articleContent}>
              <Text style={styles.articleTitle} numberOfLines={2}>
                {getDisplayTitle(article)}
              </Text>
              <Text style={styles.articleMeta}>
                {article.hostname} · {article.estimated_read_minutes} min
              </Text>
            </View>
          </Pressable>
        ))}
        {hasMore && !expanded && (
          <Pressable
            style={styles.expandRow}
            onPress={() => setExpanded(true)}
          >
            <View style={styles.treeLine} />
            <Text style={styles.expandText}>
              +{articles.length - 3} more ›
            </Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

// --- Styles ---

const gridStyles: Record<string, any> = Platform.OS === 'web' ? {
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '0 28px',
  },
} : {};

const richStyles: Record<string, any> = {
  card: {
    borderTopWidth: 2,
    borderTopColor: colors.rule,
    paddingTop: 14,
    paddingBottom: 12,
    paddingHorizontal: 2,
    ...(Platform.OS === 'web' ? { cursor: 'pointer', transition: 'border-color 0.15s' } as any : {}),
  },
  cardCompleted: {
    borderTopColor: colors.claimNew,
    opacity: 0.7,
  },
  cardHovered: {
    borderTopColor: colors.rubric,
  },
  title: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 18,
    lineHeight: 23,
    color: colors.ink,
    marginBottom: 6,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } as any : {}),
  },
  preview: {
    fontFamily: fonts.reading,
    fontSize: 13.5,
    lineHeight: 20,
    color: colors.textSecondary,
    marginBottom: 8,
  },
  tensionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
    marginBottom: 8,
    paddingLeft: 2,
  },
  tensionIcon: {
    fontSize: 10,
    color: '#b89840',
    marginTop: 2,
  },
  tensionText: {
    fontFamily: fonts.readingItalic,
    fontSize: 11.5,
    lineHeight: 16,
    color: colors.textSecondary,
    flex: 1,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } as any : {}),
  },
  sourcesSection: {
    marginBottom: 8,
  },
  sourceTitle: {
    fontFamily: fonts.ui,
    fontSize: 10.5,
    lineHeight: 16,
    color: colors.textMuted,
  },
  sourceMore: {
    fontFamily: fonts.ui,
    fontSize: 10.5,
    color: colors.textMuted,
    marginTop: 1,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  readLink: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
  completedBadge: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.claimNew,
  },
  articleCount: {
    fontFamily: fonts.ui,
    fontSize: 10.5,
    color: colors.textMuted,
  },
};

const styles = StyleSheet.create({
  container: {
    paddingBottom: 20,
  },
  synthesesSection: {
    paddingTop: 8,
  },
  uncoveredSection: {
    paddingTop: 4,
  },
  sectionHeader: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: 8,
    marginTop: 12,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  group: {
    paddingTop: 12,
    paddingBottom: 4,
  },
  groupHeader: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    color: colors.ink,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  groupArticles: {
    marginLeft: 4,
  },
  articleRow: {
    flexDirection: 'row',
    paddingVertical: 8,
    minHeight: 44,
  },
  treeLine: {
    width: 12,
    marginRight: 8,
    borderLeftWidth: 1,
    borderLeftColor: colors.rule,
    marginTop: 4,
  },
  articleContent: {
    flex: 1,
  },
  articleTitle: {
    ...type.entryTitle,
    fontSize: 14,
    lineHeight: 19,
    color: colors.textPrimary,
  },
  articleMeta: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 2,
  },
  expandRow: {
    flexDirection: 'row',
    paddingVertical: 6,
    alignItems: 'center',
  },
  expandText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
  },
  empty: {
    paddingVertical: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.textMuted,
  },
});
