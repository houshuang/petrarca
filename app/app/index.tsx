import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Dimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getArticles, getFeedArticles, getReadingState, getStats } from '../data/store';
import { Article, ReadingDepth } from '../data/types';
import { logEvent } from '../data/logger';

const DEPTH_LABELS: Record<ReadingDepth, string> = {
  unread: '',
  summary: 'Read summary',
  claims: 'Reviewed claims',
  sections: 'Reading',
  full: 'Finished',
};

const DEPTH_COLORS: Record<ReadingDepth, string> = {
  unread: '#475569',
  summary: '#3b82f6',
  claims: '#8b5cf6',
  sections: '#f59e0b',
  full: '#10b981',
};

function FeedCard({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);

  return (
    <Pressable
      style={styles.card}
      onPress={() => {
        logEvent('feed_item_tap', { article_id: article.id, title: article.title });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={styles.cardHeader}>
        <Text style={styles.hostname}>{article.hostname}</Text>
        <Text style={styles.readTime}>{article.estimated_read_minutes} min</Text>
      </View>

      <Text style={styles.title}>{article.title}</Text>

      {article.one_line_summary && article.one_line_summary !== '[dry run]' && (
        <Text style={styles.summary} numberOfLines={2}>{article.one_line_summary}</Text>
      )}

      <View style={styles.cardFooter}>
        <View style={styles.topics}>
          {article.topics.slice(0, 3).map(t => (
            <View key={t} style={styles.topicPill}>
              <Text style={styles.topicText}>{t}</Text>
            </View>
          ))}
        </View>

        {state.depth !== 'unread' && (
          <View style={[styles.depthBadge, { borderColor: DEPTH_COLORS[state.depth] }]}>
            <Text style={[styles.depthText, { color: DEPTH_COLORS[state.depth] }]}>
              {DEPTH_LABELS[state.depth]}
            </Text>
          </View>
        )}
      </View>

      {article.author ? (
        <Text style={styles.author}>{article.author}</Text>
      ) : null}
    </Pressable>
  );
}

export default function FeedScreen() {
  const [showAll, setShowAll] = useState(false);
  const [, forceUpdate] = useState(0);
  const feed = showAll ? getArticles() : getFeedArticles();
  const stats = getStats();

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.headerTitle}>
          {feed.length} article{feed.length !== 1 ? 's' : ''}
        </Text>
        <Pressable onPress={() => {
          logEvent('feed_toggle_filter', { show_all: !showAll });
          setShowAll(!showAll);
        }}>
          <Text style={styles.filterToggle}>{showAll ? 'Unread only' : 'Show all'}</Text>
        </Pressable>
        <Pressable onPress={() => forceUpdate(n => n + 1)}>
          <Ionicons name="refresh" size={18} color="#64748b" />
        </Pressable>
      </View>

      {stats.read > 0 && (
        <View style={styles.progressRow}>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${Math.round((stats.read / stats.total) * 100)}%` }]} />
          </View>
          <Text style={styles.progressLabel}>{stats.read}/{stats.total} read</Text>
        </View>
      )}

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {feed.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="checkmark-circle" size={48} color="#10b981" />
            <Text style={styles.emptyTitle}>All caught up!</Text>
            <Text style={styles.emptySubtitle}>No unread articles</Text>
          </View>
        ) : (
          feed.map(a => <FeedCard key={a.id} article={a} />)
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, gap: 12 },
  headerTitle: { color: '#f8fafc', fontSize: 16, fontWeight: '600', flex: 1 },
  filterToggle: { color: '#60a5fa', fontSize: 13 },
  progressRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 8, gap: 8 },
  progressBar: { flex: 1, height: 4, backgroundColor: '#1e293b', borderRadius: 2, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#2563eb', borderRadius: 2 },
  progressLabel: { color: '#64748b', fontSize: 12 },
  scroll: { flex: 1, paddingHorizontal: 16 },
  card: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  hostname: { color: '#60a5fa', fontSize: 12, fontWeight: '500' },
  readTime: { color: '#64748b', fontSize: 12 },
  title: { color: '#f8fafc', fontSize: 17, fontWeight: '600', lineHeight: 23, marginBottom: 4 },
  summary: { color: '#94a3b8', fontSize: 14, lineHeight: 20, marginBottom: 8 },
  author: { color: '#64748b', fontSize: 12, marginTop: 4 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  topics: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, flex: 1 },
  topicPill: { backgroundColor: '#334155', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  topicText: { color: '#94a3b8', fontSize: 11 },
  depthBadge: { borderWidth: 1, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  depthText: { fontSize: 11, fontWeight: '500' },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 100, gap: 8 },
  emptyTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  emptySubtitle: { color: '#94a3b8', fontSize: 14 },
});
