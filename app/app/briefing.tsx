import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getByTopic, getBookmarks, addSignal, getSignalForBookmark } from '../data/store';
import { Bookmark } from '../data/types';
import { logEvent } from '../data/logger';

function BookmarkItem({ bookmark, depth = 0 }: { bookmark: Bookmark; depth?: number }) {
  const [expanded, setExpanded] = useState(false);
  const signal = getSignalForBookmark(bookmark.id);
  const summary = bookmark._llm_summary;
  const claims = summary?.key_claims ?? [];

  const signalColors: Record<string, string> = {
    interesting: '#10b981',
    deep_dive: '#f59e0b',
    knew_it: '#64748b',
    not_relevant: '#475569',
  };

  return (
    <View style={[styles.item, depth > 0 && styles.nestedItem]}>
      <Pressable onPress={() => {
        logEvent('briefing_item_toggle', { bookmark_id: bookmark.id, expanded: !expanded });
        setExpanded(!expanded);
      }} style={styles.itemHeader}>
        <View style={styles.itemLeft}>
          {signal && <View style={[styles.signalDot, { backgroundColor: signalColors[signal.signal] }]} />}
          <Text style={styles.itemAuthor}>@{bookmark.author_username}</Text>
          {summary?.content_type && summary.content_type !== 'unknown' && (
            <Text style={styles.contentType}>{summary.content_type.replace('_', ' ')}</Text>
          )}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color="#64748b" />
      </Pressable>

      {/* Level 1: Summary (always visible) */}
      <Text style={styles.summaryText} numberOfLines={expanded ? undefined : 2}>
        {summary?.summary && summary.summary !== '[dry run]' ? summary.summary : bookmark.text.slice(0, 200)}
      </Text>

      {expanded && (
        <>
          {/* Level 2: Key claims */}
          {claims.length > 0 && (
            <View style={styles.claimsBox}>
              {claims.map((c, i) => (
                <View key={i} style={styles.claimRow}>
                  <Text style={styles.bullet}>→</Text>
                  <Text style={styles.claimText}>{c}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Level 3: Original tweet */}
          <View style={styles.originalBox}>
            <Text style={styles.originalLabel}>Original:</Text>
            <Text style={styles.originalText}>{bookmark.text}</Text>
          </View>

          {/* Action buttons */}
          <View style={styles.actions}>
            <Pressable style={styles.actionBtn} onPress={() => {
              logEvent('briefing_signal', { bookmark_id: bookmark.id, signal: 'knew_it' });
              addSignal({ bookmarkId: bookmark.id, signal: 'knew_it', timestamp: Date.now() });
            }}>
              <Text style={styles.actionText}>Knew it</Text>
            </Pressable>
            <Pressable style={[styles.actionBtn, styles.actionInteresting]} onPress={() => {
              logEvent('briefing_signal', { bookmark_id: bookmark.id, signal: 'interesting' });
              addSignal({ bookmarkId: bookmark.id, signal: 'interesting', timestamp: Date.now() });
            }}>
              <Text style={[styles.actionText, { color: '#10b981' }]}>Interesting</Text>
            </Pressable>
            <Pressable style={[styles.actionBtn, styles.actionDeep]} onPress={() => {
              logEvent('briefing_signal', { bookmark_id: bookmark.id, signal: 'deep_dive' });
              addSignal({ bookmarkId: bookmark.id, signal: 'deep_dive', timestamp: Date.now() });
            }}>
              <Text style={[styles.actionText, { color: '#f59e0b' }]}>Deep dive</Text>
            </Pressable>
            {bookmark.urls?.[0] && (
              <Pressable style={styles.actionBtn} onPress={() => {
                logEvent('link_open', { bookmark_id: bookmark.id, url: bookmark.urls[0], screen: 'briefing' });
                Linking.openURL(bookmark.urls[0]);
              }}>
                <Ionicons name="open-outline" size={14} color="#60a5fa" />
              </Pressable>
            )}
          </View>
        </>
      )}
    </View>
  );
}

function TopicSection({ topic, bookmarks }: { topic: string; bookmarks: Bookmark[] }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <View style={styles.section}>
      <Pressable onPress={() => {
        logEvent('briefing_topic_toggle', { topic, collapsed: !collapsed, item_count: bookmarks.length });
        setCollapsed(!collapsed);
      }} style={styles.sectionHeader}>
        <View style={styles.sectionLeft}>
          <Text style={styles.sectionTitle}>{topic}</Text>
          <Text style={styles.sectionCount}>{bookmarks.length}</Text>
        </View>
        <Ionicons name={collapsed ? 'chevron-down' : 'chevron-up'} size={18} color="#64748b" />
      </Pressable>

      {!collapsed && bookmarks.map(b => (
        <BookmarkItem key={b.id} bookmark={b} />
      ))}
    </View>
  );
}

export default function BriefingScreen() {
  const [viewMode, setViewMode] = useState<'topic' | 'all'>('topic');
  const topicMap = getByTopic();
  const all = getBookmarks();

  // Sort topics by number of bookmarks
  const topicEntries = [...topicMap.entries()].sort((a, b) => b[1].length - a[1].length);

  return (
    <View style={styles.container}>
      {/* View toggle */}
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'topic' && styles.toggleActive]}
          onPress={() => { logEvent('briefing_view_mode', { mode: 'topic' }); setViewMode('topic'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'topic' && styles.toggleTextActive]}>By Topic</Text>
        </Pressable>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'all' && styles.toggleActive]}
          onPress={() => { logEvent('briefing_view_mode', { mode: 'all' }); setViewMode('all'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'all' && styles.toggleTextActive]}>All ({all.length})</Text>
        </Pressable>
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {viewMode === 'topic' ? (
          topicEntries.map(([topic, bookmarks]) => (
            <TopicSection key={topic} topic={topic} bookmarks={bookmarks} />
          ))
        ) : (
          all.map(b => <BookmarkItem key={b.id} bookmark={b} />)
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  toggleRow: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 8, gap: 8 },
  toggleBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: 20, backgroundColor: '#1e293b' },
  toggleActive: { backgroundColor: '#2563eb' },
  toggleText: { color: '#94a3b8', fontSize: 14 },
  toggleTextActive: { color: '#f8fafc' },
  scroll: { flex: 1, paddingHorizontal: 16, paddingTop: 8 },
  section: { marginBottom: 8, borderRadius: 12, overflow: 'hidden', backgroundColor: '#1e293b' },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14 },
  sectionLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sectionTitle: { color: '#f8fafc', fontSize: 16, fontWeight: '600' },
  sectionCount: { color: '#64748b', fontSize: 13, backgroundColor: '#334155', paddingHorizontal: 8, paddingVertical: 1, borderRadius: 10 },
  item: { paddingHorizontal: 14, paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#334155' },
  nestedItem: { paddingLeft: 28 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  itemLeft: { flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 },
  signalDot: { width: 8, height: 8, borderRadius: 4 },
  itemAuthor: { color: '#60a5fa', fontSize: 13, fontWeight: '500' },
  contentType: { color: '#64748b', fontSize: 11, backgroundColor: '#334155', paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 },
  summaryText: { color: '#cbd5e1', fontSize: 14, lineHeight: 20 },
  claimsBox: { marginTop: 8, paddingLeft: 4 },
  claimRow: { flexDirection: 'row', marginBottom: 4 },
  bullet: { color: '#60a5fa', marginRight: 8, fontSize: 13 },
  claimText: { color: '#94a3b8', fontSize: 13, lineHeight: 18, flex: 1 },
  originalBox: { marginTop: 10, padding: 10, backgroundColor: '#0f172a', borderRadius: 8 },
  originalLabel: { color: '#475569', fontSize: 11, marginBottom: 4 },
  originalText: { color: '#64748b', fontSize: 13, lineHeight: 18 },
  actions: { flexDirection: 'row', gap: 8, marginTop: 10 },
  actionBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: '#334155' },
  actionInteresting: { borderColor: '#10b981', borderWidth: 1, backgroundColor: 'transparent' },
  actionDeep: { borderColor: '#f59e0b', borderWidth: 1, backgroundColor: 'transparent' },
  actionText: { color: '#94a3b8', fontSize: 13 },
});
