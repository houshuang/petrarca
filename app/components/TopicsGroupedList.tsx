import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getArticlesGroupedByTopic, getReadingState, recordInterestSignal } from '../data/store';
import { getDisplayTitle, displayTopic } from '../lib/display-utils';
import { Article } from '../data/types';
import { useState } from 'react';

interface TopicsGroupedListProps {
  topicFilter?: string;
}

export default function TopicsGroupedList({ topicFilter }: TopicsGroupedListProps) {
  const router = useRouter();
  const allGroups = getArticlesGroupedByTopic();

  const groups = topicFilter
    ? allGroups.filter(g => g.topic.toLowerCase().includes(topicFilter.toLowerCase()))
    : allGroups;

  if (groups.length === 0) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>No topics found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {groups.map(group => (
        <TopicGroup key={group.topic} topic={group.topic} articles={group.articles} />
      ))}
    </View>
  );
}

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
        <Text style={styles.groupCount}>  {articles.length}</Text>
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

const styles = StyleSheet.create({
  container: {
    paddingBottom: 20,
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
  groupCount: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    textTransform: 'none',
    letterSpacing: 0,
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
