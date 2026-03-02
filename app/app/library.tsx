import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getLibraryArticles, getByTopic, getReadingState, getArticles } from '../data/store';
import { Article, ReadingDepth } from '../data/types';
import { logEvent } from '../data/logger';

const DEPTH_COLORS: Record<ReadingDepth, string> = {
  unread: '#475569',
  summary: '#3b82f6',
  claims: '#8b5cf6',
  sections: '#f59e0b',
  full: '#10b981',
};

const DEPTH_ICONS: Record<ReadingDepth, string> = {
  unread: 'ellipse-outline',
  summary: 'eye-outline',
  claims: 'list-outline',
  sections: 'book-outline',
  full: 'checkmark-circle',
};

function LibraryItem({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const timeMin = Math.round(state.time_spent_ms / 60000);
  const lastRead = state.last_read_at ? new Date(state.last_read_at).toLocaleDateString() : '';

  return (
    <Pressable
      style={styles.item}
      onPress={() => {
        logEvent('library_item_tap', { article_id: article.id, depth: state.depth });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={styles.itemLeft}>
        <Ionicons
          name={DEPTH_ICONS[state.depth] as any}
          size={20}
          color={DEPTH_COLORS[state.depth]}
        />
      </View>
      <View style={styles.itemContent}>
        <Text style={styles.itemTitle} numberOfLines={2}>{article.title}</Text>
        <View style={styles.itemMeta}>
          <Text style={styles.itemMetaText}>{article.hostname}</Text>
          {timeMin > 0 && <Text style={styles.itemMetaText}>{timeMin} min spent</Text>}
          {lastRead && <Text style={styles.itemMetaText}>{lastRead}</Text>}
        </View>
      </View>
    </Pressable>
  );
}

export default function LibraryScreen() {
  const [viewMode, setViewMode] = useState<'recent' | 'topic'>('recent');
  const [, forceUpdate] = useState(0);
  const library = getLibraryArticles();
  const allArticles = getArticles();
  const topicMap = getByTopic();

  return (
    <View style={styles.container}>
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'recent' && styles.toggleActive]}
          onPress={() => { logEvent('library_view_mode', { mode: 'recent' }); setViewMode('recent'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'recent' && styles.toggleTextActive]}>Recent</Text>
        </Pressable>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'topic' && styles.toggleActive]}
          onPress={() => { logEvent('library_view_mode', { mode: 'topic' }); setViewMode('topic'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'topic' && styles.toggleTextActive]}>By Topic</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable onPress={() => forceUpdate(n => n + 1)}>
          <Ionicons name="refresh" size={18} color="#64748b" />
        </Pressable>
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {viewMode === 'recent' ? (
          library.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="library-outline" size={48} color="#475569" />
              <Text style={styles.emptyTitle}>Nothing here yet</Text>
              <Text style={styles.emptySubtitle}>Articles you read will appear here</Text>
            </View>
          ) : (
            library.map(a => <LibraryItem key={a.id} article={a} />)
          )
        ) : (
          [...topicMap.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .map(([topic, articles]) => (
              <TopicGroup key={topic} topic={topic} articles={articles} />
            ))
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

function TopicGroup({ topic, articles }: { topic: string; articles: Article[] }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <View style={styles.topicGroup}>
      <Pressable
        onPress={() => {
          logEvent('library_topic_toggle', { topic, collapsed: !collapsed });
          setCollapsed(!collapsed);
        }}
        style={styles.topicHeader}
      >
        <Text style={styles.topicTitle}>{topic}</Text>
        <View style={styles.topicRight}>
          <Text style={styles.topicCount}>{articles.length}</Text>
          <Ionicons name={collapsed ? 'chevron-down' : 'chevron-up'} size={16} color="#64748b" />
        </View>
      </Pressable>
      {!collapsed && articles.map(a => <LibraryItem key={a.id} article={a} />)}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  toggleRow: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, gap: 8, alignItems: 'center' },
  toggleBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: 20, backgroundColor: '#1e293b' },
  toggleActive: { backgroundColor: '#2563eb' },
  toggleText: { color: '#94a3b8', fontSize: 14 },
  toggleTextActive: { color: '#f8fafc' },
  scroll: { flex: 1, paddingHorizontal: 16, paddingTop: 8 },

  item: { flexDirection: 'row', backgroundColor: '#1e293b', borderRadius: 10, padding: 14, marginBottom: 8, gap: 12 },
  itemLeft: { paddingTop: 2 },
  itemContent: { flex: 1 },
  itemTitle: { color: '#f8fafc', fontSize: 15, fontWeight: '500', lineHeight: 20, marginBottom: 4 },
  itemMeta: { flexDirection: 'row', gap: 8 },
  itemMetaText: { color: '#64748b', fontSize: 12 },

  topicGroup: { marginBottom: 4, borderRadius: 10, overflow: 'hidden', backgroundColor: '#1e293b' },
  topicHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14 },
  topicTitle: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  topicRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  topicCount: { color: '#64748b', fontSize: 13, backgroundColor: '#334155', paddingHorizontal: 8, paddingVertical: 1, borderRadius: 10 },

  empty: { justifyContent: 'center', alignItems: 'center', paddingTop: 100, gap: 8 },
  emptyTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  emptySubtitle: { color: '#94a3b8', fontSize: 14 },
});
