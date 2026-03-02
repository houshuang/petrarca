import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getStats, getSignals, getBookmarks, getByTopic } from '../data/store';

export default function StatsScreen() {
  const [, forceUpdate] = useState(0);
  const stats = getStats();
  const signals = getSignals();
  const bookmarks = getBookmarks();
  const topicMap = getByTopic();

  // Count signals by topic
  const signalsByTopic = new Map<string, { interesting: number; knewIt: number; deepDive: number }>();
  for (const s of signals) {
    const bm = bookmarks.find(b => b.id === s.bookmarkId);
    if (!bm) continue;
    const topics = bm._llm_summary?.topics ?? ['uncategorized'];
    for (const t of topics) {
      if (!signalsByTopic.has(t)) signalsByTopic.set(t, { interesting: 0, knewIt: 0, deepDive: 0 });
      const entry = signalsByTopic.get(t)!;
      if (s.signal === 'interesting') entry.interesting++;
      else if (s.signal === 'knew_it') entry.knewIt++;
      else if (s.signal === 'deep_dive') entry.deepDive++;
    }
  }

  const pct = stats.total > 0 ? Math.round((stats.triaged / stats.total) * 100) : 0;

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Progress bar */}
        <View style={styles.progressSection}>
          <Text style={styles.sectionTitle}>Triage Progress</Text>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${pct}%` }]} />
          </View>
          <Text style={styles.progressLabel}>{stats.triaged} / {stats.total} ({pct}%)</Text>
        </View>

        {/* Signal breakdown */}
        <View style={styles.statsGrid}>
          <View style={[styles.statBox, { borderLeftColor: '#10b981' }]}>
            <Text style={styles.statNumber}>{stats.interesting}</Text>
            <Text style={styles.statLabel}>Interesting</Text>
          </View>
          <View style={[styles.statBox, { borderLeftColor: '#f59e0b' }]}>
            <Text style={styles.statNumber}>{stats.deepDive}</Text>
            <Text style={styles.statLabel}>Deep Dive</Text>
          </View>
          <View style={[styles.statBox, { borderLeftColor: '#64748b' }]}>
            <Text style={styles.statNumber}>{stats.knewIt}</Text>
            <Text style={styles.statLabel}>Knew It</Text>
          </View>
          <View style={[styles.statBox, { borderLeftColor: '#475569' }]}>
            <Text style={styles.statNumber}>{stats.notRelevant}</Text>
            <Text style={styles.statLabel}>Not Relevant</Text>
          </View>
        </View>

        {/* Knowledge map */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Your Knowledge Map</Text>
          <Text style={styles.sectionSubtitle}>Topics where you marked "knew it" vs "new to me"</Text>

          {[...signalsByTopic.entries()]
            .sort((a, b) => (b[1].interesting + b[1].deepDive) - (a[1].interesting + a[1].deepDive))
            .map(([topic, counts]) => {
              const total = counts.interesting + counts.knewIt + counts.deepDive;
              const knewPct = total > 0 ? Math.round((counts.knewIt / total) * 100) : 0;
              const newPct = total > 0 ? Math.round((counts.interesting / total) * 100) : 0;
              const deepPct = total > 0 ? Math.round((counts.deepDive / total) * 100) : 0;
              return (
                <View key={topic} style={styles.topicRow}>
                  <Text style={styles.topicName}>{topic}</Text>
                  <View style={styles.topicBar}>
                    {knewPct > 0 && <View style={[styles.topicSegment, { width: `${knewPct}%`, backgroundColor: '#475569' }]} />}
                    {newPct > 0 && <View style={[styles.topicSegment, { width: `${newPct}%`, backgroundColor: '#10b981' }]} />}
                    {deepPct > 0 && <View style={[styles.topicSegment, { width: `${deepPct}%`, backgroundColor: '#f59e0b' }]} />}
                  </View>
                  <Text style={styles.topicCount}>{total}</Text>
                </View>
              );
            })}
        </View>

        {/* Content coverage */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Content Sources</Text>
          {[...topicMap.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .slice(0, 10)
            .map(([topic, bms]) => (
              <View key={topic} style={styles.coverageRow}>
                <Text style={styles.coverageTopic}>{topic}</Text>
                <Text style={styles.coverageCount}>{bms.length} items</Text>
              </View>
            ))}
        </View>

        {/* Refresh hint */}
        <Pressable style={styles.refreshBtn} onPress={() => forceUpdate(n => n + 1)}>
          <Ionicons name="refresh" size={16} color="#60a5fa" />
          <Text style={styles.refreshText}>Refresh stats</Text>
        </Pressable>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  scroll: { flex: 1, paddingHorizontal: 16, paddingTop: 12 },
  section: { marginBottom: 20 },
  sectionTitle: { color: '#f8fafc', fontSize: 18, fontWeight: '700', marginBottom: 4 },
  sectionSubtitle: { color: '#64748b', fontSize: 13, marginBottom: 12 },
  progressSection: { marginBottom: 20 },
  progressBar: { height: 8, backgroundColor: '#1e293b', borderRadius: 4, marginTop: 8, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#2563eb', borderRadius: 4 },
  progressLabel: { color: '#94a3b8', fontSize: 13, marginTop: 4 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 },
  statBox: { flex: 1, minWidth: '45%', backgroundColor: '#1e293b', borderRadius: 12, padding: 14, borderLeftWidth: 3 },
  statNumber: { color: '#f8fafc', fontSize: 28, fontWeight: '700' },
  statLabel: { color: '#94a3b8', fontSize: 13 },
  topicRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 8 },
  topicName: { color: '#cbd5e1', fontSize: 13, width: 100 },
  topicBar: { flex: 1, height: 12, backgroundColor: '#1e293b', borderRadius: 6, flexDirection: 'row', overflow: 'hidden' },
  topicSegment: { height: '100%' },
  topicCount: { color: '#64748b', fontSize: 12, width: 24, textAlign: 'right' },
  coverageRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  coverageTopic: { color: '#cbd5e1', fontSize: 14 },
  coverageCount: { color: '#64748b', fontSize: 13 },
  refreshBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, marginTop: 8 },
  refreshText: { color: '#60a5fa', fontSize: 14 },
});
