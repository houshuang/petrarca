import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getBookmarks, addSignal, getSignalForBookmark } from '../data/store';
import { Bookmark } from '../data/types';
import { logEvent } from '../data/logger';

interface ClaimWithSource {
  claim: string;
  bookmark: Bookmark;
  topicGroup: string;
}

function extractAllClaims(): ClaimWithSource[] {
  const bookmarks = getBookmarks();
  const claims: ClaimWithSource[] = [];

  for (const b of bookmarks) {
    const summary = b._llm_summary;
    if (!summary?.key_claims) continue;
    const mainTopic = summary.topics?.[0] ?? 'uncategorized';

    for (const claim of summary.key_claims) {
      claims.push({ claim, bookmark: b, topicGroup: mainTopic });
    }
  }

  return claims;
}

function ClaimCard({ item, onSignal }: { item: ClaimWithSource; onSignal: (signal: string) => void }) {
  const [showSource, setShowSource] = useState(false);
  const signal = getSignalForBookmark(item.bookmark.id);

  return (
    <View style={styles.claimCard}>
      <Text style={styles.claimText}>{item.claim}</Text>

      <View style={styles.sourceRow}>
        <Pressable onPress={() => {
          logEvent('claim_source_toggle', { bookmark_id: item.bookmark.id, claim: item.claim.slice(0, 80), show: !showSource });
          setShowSource(!showSource);
        }}>
          <Text style={styles.sourceAuthor}>@{item.bookmark.author_username}</Text>
        </Pressable>
        <Text style={styles.topicBadge}>{item.topicGroup}</Text>
      </View>

      {showSource && (
        <View style={styles.sourceExpanded}>
          <Text style={styles.sourceContext}>{item.bookmark._llm_summary?.summary ?? item.bookmark.text.slice(0, 300)}</Text>
          {item.bookmark.urls?.[0] && (
            <Pressable onPress={() => {
              logEvent('link_open', { bookmark_id: item.bookmark.id, url: item.bookmark.urls[0], screen: 'claims' });
              Linking.openURL(item.bookmark.urls[0]);
            }}>
              <Text style={styles.linkText}>Open source ↗</Text>
            </Pressable>
          )}
        </View>
      )}

      <View style={styles.signalRow}>
        <Pressable
          style={[styles.signalBtn, signal?.signal === 'knew_it' && styles.signalActive]}
          onPress={() => onSignal('knew_it')}
        >
          <Text style={styles.signalText}>Knew this</Text>
        </Pressable>
        <Pressable
          style={[styles.signalBtn, styles.signalNew, signal?.signal === 'interesting' && styles.signalNewActive]}
          onPress={() => onSignal('interesting')}
        >
          <Ionicons name="sparkles" size={12} color={signal?.signal === 'interesting' ? '#0f172a' : '#10b981'} />
          <Text style={[styles.signalText, { color: signal?.signal === 'interesting' ? '#0f172a' : '#10b981' }]}>New to me</Text>
        </Pressable>
        <Pressable
          style={[styles.signalBtn, styles.signalDeep, signal?.signal === 'deep_dive' && styles.signalDeepActive]}
          onPress={() => onSignal('deep_dive')}
        >
          <Text style={[styles.signalText, { color: signal?.signal === 'deep_dive' ? '#0f172a' : '#f59e0b' }]}>Dig deeper</Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function ClaimsScreen() {
  const [, forceUpdate] = useState(0);
  const allClaims = extractAllClaims();

  // Group by topic
  const grouped = new Map<string, ClaimWithSource[]>();
  for (const c of allClaims) {
    if (!grouped.has(c.topicGroup)) grouped.set(c.topicGroup, []);
    grouped.get(c.topicGroup)!.push(c);
  }

  const handleSignal = (bookmarkId: string, signal: string) => {
    logEvent('claim_signal', { bookmark_id: bookmarkId, signal, screen: 'claims' });
    addSignal({ bookmarkId, signal: signal as any, timestamp: Date.now() });
    forceUpdate(n => n + 1);
  };

  return (
    <View style={styles.container}>
      <Text style={styles.header}>{allClaims.length} claims extracted</Text>
      <Text style={styles.subheader}>Individual insights from your Claude Code bookmarks. Mark what's new to you.</Text>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {[...grouped.entries()].sort((a, b) => b[1].length - a[1].length).map(([topic, claims]) => (
          <View key={topic}>
            <Text style={styles.topicHeader}>{topic} ({claims.length})</Text>
            {claims.map((c, i) => (
              <ClaimCard
                key={`${c.bookmark.id}-${i}`}
                item={c}
                onSignal={(s) => handleSignal(c.bookmark.id, s)}
              />
            ))}
          </View>
        ))}
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  header: { color: '#f8fafc', fontSize: 20, fontWeight: '700', paddingHorizontal: 16, paddingTop: 12 },
  subheader: { color: '#64748b', fontSize: 13, paddingHorizontal: 16, paddingBottom: 8 },
  scroll: { flex: 1, paddingHorizontal: 16 },
  topicHeader: { color: '#60a5fa', fontSize: 14, fontWeight: '600', marginTop: 16, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  claimCard: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
  },
  claimText: { color: '#e2e8f0', fontSize: 15, lineHeight: 22, marginBottom: 8 },
  sourceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  sourceAuthor: { color: '#60a5fa', fontSize: 12 },
  topicBadge: { color: '#64748b', fontSize: 11, backgroundColor: '#334155', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  sourceExpanded: { backgroundColor: '#0f172a', padding: 10, borderRadius: 8, marginTop: 6, marginBottom: 6 },
  sourceContext: { color: '#94a3b8', fontSize: 13, lineHeight: 18 },
  linkText: { color: '#60a5fa', fontSize: 13, marginTop: 6 },
  signalRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  signalBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: '#334155' },
  signalActive: { backgroundColor: '#475569' },
  signalNew: { borderColor: '#10b981', borderWidth: 1, backgroundColor: 'transparent' },
  signalNewActive: { backgroundColor: '#10b981' },
  signalDeep: { borderColor: '#f59e0b', borderWidth: 1, backgroundColor: 'transparent' },
  signalDeepActive: { backgroundColor: '#f59e0b' },
  signalText: { color: '#94a3b8', fontSize: 12 },
});
