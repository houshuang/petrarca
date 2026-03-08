import { useState, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { getArticles, getReadingState } from '../../data/store';
import { Article } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle } from '../../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';
import { isKnowledgeReady, getDeltaReportForTopic } from '../../data/knowledge-engine';

// --- Compact Article Row ---

function CompactArticleRow({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const dotColor = state.status === 'reading'
    ? colors.rubric
    : state.status === 'read'
      ? colors.claimNew
      : colors.rule;

  return (
    <Pressable
      style={({ pressed }) => [
        styles.compactRow,
        pressed && { opacity: 0.9 },
      ]}
      onPress={() => {
        logEvent('topics_article_tap', { article_id: article.id });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={[styles.statusDot, { backgroundColor: dotColor }]} />
      <View style={styles.compactContent}>
        <Text style={styles.compactTitle} numberOfLines={1}>
          {getDisplayTitle(article)}
        </Text>
        <Text style={styles.compactMeta}>
          {article.hostname} {'\u00b7'} {article.estimated_read_minutes} min
        </Text>
      </View>
    </Pressable>
  );
}

// --- Topic Cluster ---

function TopicCluster({ topic, articles, expanded, onToggle }: {
  topic: string;
  articles: Article[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const knowledgeReady = isKnowledgeReady();
  const delta = knowledgeReady ? getDeltaReportForTopic(topic) : null;

  // Count reading states
  const readCount = articles.filter(a => getReadingState(a.id).status === 'read').length;
  const readingCount = articles.filter(a => getReadingState(a.id).status === 'reading').length;

  return (
    <View style={styles.cluster}>
      <Pressable
        style={({ pressed }) => [
          styles.clusterHeader,
          pressed && { opacity: 0.85 },
        ]}
        onPress={() => {
          onToggle();
          logEvent('topics_cluster_toggle', { topic, expanded: !expanded });
        }}
      >
        <View style={styles.clusterHeaderLeft}>
          <Text style={styles.clusterName}>{topic}</Text>
          <Text style={styles.clusterCount}>
            {articles.length} article{articles.length !== 1 ? 's' : ''}
            {readCount > 0 ? ` \u00b7 ${readCount} read` : ''}
            {readingCount > 0 ? ` \u00b7 ${readingCount} in progress` : ''}
          </Text>
        </View>
        <Text style={styles.clusterChevron}>{expanded ? '\u2013' : '+'}</Text>
      </Pressable>

      {/* Knowledge progress bar */}
      {delta && delta.claim_count > 0 ? (
        <View style={styles.knowledgeBar}>
          <View style={[
            styles.knowledgeBarNew,
            { flex: delta.top_claims.length },
          ]} />
          <View style={[
            styles.knowledgeBarKnown,
            { flex: delta.claim_count - delta.top_claims.length },
          ]} />
        </View>
      ) : null}

      {expanded ? (
        <View style={styles.clusterBody}>
          {/* Delta report */}
          {delta && delta.summary ? (
            <View style={styles.deltaSection}>
              <Text style={styles.sectionHead}>
                <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
                {"What\u2019s new in "}{topic}
              </Text>
              <Text style={styles.deltaSummary}>{delta.summary}</Text>
              {delta.top_claims.slice(0, 3).map((claim, i) => (
                <View key={i} style={styles.deltaClaim}>
                  <Text style={styles.deltaClaimText}>{claim.text}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {/* Article list */}
          {articles.map(a => (
            <CompactArticleRow key={a.id} article={a} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

// --- Topics Screen ---

export default function TopicsScreen() {
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null);

  const topicGroups = useMemo(() => {
    const articles = getArticles();
    const groups = new Map<string, Article[]>();

    for (const article of articles) {
      const topics = article.interest_topics || [];
      const broad = topics[0]?.broad || article.topics[0] || 'Other';
      if (!groups.has(broad)) groups.set(broad, []);
      groups.get(broad)!.push(article);
    }

    return [...groups.entries()]
      .sort((a, b) => b[1].length - a[1].length);
  }, []);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Topics</Text>
        <Text style={styles.headerSubtitle}>
          {topicGroups.length} topic{topicGroups.length !== 1 ? 's' : ''} across your reading
        </Text>
      </View>

      {/* Double rule */}
      <View style={styles.doubleRule}>
        <View style={styles.doubleRuleTop} />
        <View style={styles.doubleRuleGap} />
        <View style={styles.doubleRuleBottom} />
      </View>

      <View style={styles.body}>
        <Text style={styles.sectionHead}>
          <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
          Your Topics
        </Text>

        {topicGroups.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No topics yet</Text>
            <Text style={styles.emptySubtitle}>
              Topics will appear as articles are imported
            </Text>
          </View>
        ) : null}

        {topicGroups.map(([topic, articles]) => (
          <TopicCluster
            key={topic}
            topic={topic}
            articles={articles}
            expanded={expandedTopic === topic}
            onToggle={() => setExpandedTopic(
              expandedTopic === topic ? null : topic
            )}
          />
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  contentContainer: {
    paddingBottom: 40,
  },

  // Header
  header: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 8,
  },
  headerTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  headerSubtitle: {
    ...type.screenSubtitle,
    color: colors.textMuted,
    marginTop: 2,
  },

  // Double rule
  doubleRule: {
    paddingHorizontal: layout.screenPadding,
  },
  doubleRuleTop: {
    borderTopWidth: layout.doubleRuleTop,
    borderTopColor: colors.ink,
  },
  doubleRuleGap: {
    height: layout.doubleRuleGap,
  },
  doubleRuleBottom: {
    borderTopWidth: layout.doubleRuleBottom,
    borderTopColor: colors.ink,
  },

  // Body
  body: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 16,
  },
  sectionHead: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 12,
  },

  // Topic cluster
  cluster: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
    marginBottom: 4,
  },
  clusterHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  clusterHeaderLeft: {
    flex: 1,
  },
  clusterName: {
    fontFamily: fonts.bodyItalic,
    fontSize: 16,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  clusterCount: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 2,
  },
  clusterChevron: {
    fontFamily: fonts.display,
    fontSize: 18,
    color: colors.textMuted,
    paddingLeft: 12,
  },

  // Knowledge bar
  knowledgeBar: {
    flexDirection: 'row',
    height: layout.progressBarHeight,
    marginBottom: 4,
  },
  knowledgeBarNew: {
    backgroundColor: colors.claimNew,
  },
  knowledgeBarKnown: {
    backgroundColor: colors.claimKnown,
  },

  // Cluster body
  clusterBody: {
    paddingBottom: 8,
  },

  // Delta report
  deltaSection: {
    paddingVertical: 8,
    marginBottom: 4,
  },
  deltaSummary: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textBody,
    marginBottom: 8,
  },
  deltaClaim: {
    borderLeftWidth: layout.claimBorderWidth,
    borderLeftColor: colors.claimNew,
    paddingLeft: 10,
    marginBottom: 6,
  },
  deltaClaimText: {
    fontFamily: fonts.reading,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textBody,
  },

  // Compact article row
  compactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    minHeight: 44,
  },
  statusDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    marginRight: 10,
  },
  compactContent: {
    flex: 1,
  },
  compactTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    fontSize: 14,
  },
  compactMeta: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 1,
  },

  // Empty state
  empty: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 60,
    gap: 8,
  },
  emptyTitle: {
    ...type.screenTitle,
    color: colors.ink,
    fontSize: 20,
  },
  emptySubtitle: {
    ...type.entrySummary,
    color: colors.textSecondary,
    textAlign: 'center',
  },
});
