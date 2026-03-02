import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Share } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getStats, getSignals, getArticles, getByTopic, getReadingState } from '../data/store';
import { logEvent, getLogFiles, exportAllLogs, getLogDirectory } from '../data/logger';

function EventLogSection() {
  const [logFileList, setLogFileList] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    getLogFiles().then(setLogFileList);
  }, [expanded]);

  const handleExport = async () => {
    logEvent('logs_exported');
    const allLogs = await exportAllLogs();
    const lineCount = allLogs.split('\n').filter(Boolean).length;
    await Share.share({
      message: allLogs,
      title: `Petrarca interaction logs (${lineCount} events)`,
    });
  };

  return (
    <View style={styles.section}>
      <Pressable onPress={() => setExpanded(!expanded)}>
        <Text style={styles.sectionTitle}>Event Log</Text>
      </Pressable>
      <Text style={styles.sectionSubtitle}>
        {logFileList.length} log file{logFileList.length !== 1 ? 's' : ''} · {getLogDirectory()}
      </Text>

      {expanded && (
        <View style={{ marginTop: 8 }}>
          {logFileList.map(f => (
            <Text key={f} style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 2 }}>{f}</Text>
          ))}
          <Pressable style={[styles.refreshBtn, { marginTop: 8 }]} onPress={handleExport}>
            <Ionicons name="share-outline" size={16} color="#60a5fa" />
            <Text style={styles.refreshText}>Export all logs</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

export default function StatsScreen() {
  const [, forceUpdate] = useState(0);
  const stats = getStats();
  const articles = getArticles();
  const signals = getSignals();
  const topicMap = getByTopic();

  const totalTimeMin = Math.round(stats.totalTimeMs / 60000);

  // Topic reading depth breakdown
  const topicDepths = new Map<string, { summary: number; claims: number; sections: number; full: number }>();
  for (const a of articles) {
    const state = getReadingState(a.id);
    if (state.depth === 'unread') continue;
    for (const t of a.topics) {
      if (!topicDepths.has(t)) topicDepths.set(t, { summary: 0, claims: 0, sections: 0, full: 0 });
      topicDepths.get(t)![state.depth]++;
    }
  }

  const pct = stats.total > 0 ? Math.round((stats.read / stats.total) * 100) : 0;

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Reading progress */}
        <View style={styles.progressSection}>
          <Text style={styles.sectionTitle}>Reading Progress</Text>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${pct}%` }]} />
          </View>
          <Text style={styles.progressLabel}>{stats.read} / {stats.total} articles ({pct}%)</Text>
        </View>

        {/* Stats grid */}
        <View style={styles.statsGrid}>
          <View style={[styles.statBox, { borderLeftColor: '#2563eb' }]}>
            <Text style={styles.statNumber}>{stats.total}</Text>
            <Text style={styles.statLabel}>Articles</Text>
          </View>
          <View style={[styles.statBox, { borderLeftColor: '#10b981' }]}>
            <Text style={styles.statNumber}>{stats.full}</Text>
            <Text style={styles.statLabel}>Finished</Text>
          </View>
          <View style={[styles.statBox, { borderLeftColor: '#f59e0b' }]}>
            <Text style={styles.statNumber}>{stats.read - stats.full}</Text>
            <Text style={styles.statLabel}>In Progress</Text>
          </View>
          <View style={[styles.statBox, { borderLeftColor: '#8b5cf6' }]}>
            <Text style={styles.statNumber}>{totalTimeMin}</Text>
            <Text style={styles.statLabel}>Min Spent</Text>
          </View>
        </View>

        {/* Depth breakdown */}
        {stats.read > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Reading Depth</Text>
            <Text style={styles.sectionSubtitle}>How deep you've gone into articles</Text>
            <View style={styles.depthBreakdown}>
              {([['Summary', stats.summary, '#3b82f6'], ['Claims', stats.claims, '#8b5cf6'],
                ['Sections', stats.sections, '#f59e0b'], ['Full', stats.full, '#10b981']] as const).map(([label, count, color]) => (
                count > 0 && (
                  <View key={label} style={styles.depthRow}>
                    <View style={[styles.depthDot, { backgroundColor: color }]} />
                    <Text style={styles.depthLabel}>{label}</Text>
                    <Text style={styles.depthCount}>{count}</Text>
                  </View>
                )
              ))}
            </View>
          </View>
        )}

        {/* Topic coverage */}
        {topicDepths.size > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Topics Explored</Text>
            {[...topicDepths.entries()]
              .sort((a, b) => Object.values(b[1]).reduce((s, n) => s + n, 0) - Object.values(a[1]).reduce((s, n) => s + n, 0))
              .map(([topic, counts]) => {
                const total = Object.values(counts).reduce((s, n) => s + n, 0);
                return (
                  <View key={topic} style={styles.topicRow}>
                    <Text style={styles.topicName}>{topic}</Text>
                    <View style={styles.topicBar}>
                      {counts.summary > 0 && <View style={[styles.topicSegment, { width: `${(counts.summary / total) * 100}%`, backgroundColor: '#3b82f6' }]} />}
                      {counts.claims > 0 && <View style={[styles.topicSegment, { width: `${(counts.claims / total) * 100}%`, backgroundColor: '#8b5cf6' }]} />}
                      {counts.sections > 0 && <View style={[styles.topicSegment, { width: `${(counts.sections / total) * 100}%`, backgroundColor: '#f59e0b' }]} />}
                      {counts.full > 0 && <View style={[styles.topicSegment, { width: `${(counts.full / total) * 100}%`, backgroundColor: '#10b981' }]} />}
                    </View>
                    <Text style={styles.topicCount}>{total}</Text>
                  </View>
                );
              })}
          </View>
        )}

        {/* Content sources */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Content Sources</Text>
          {[...topicMap.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .slice(0, 10)
            .map(([topic, arts]) => (
              <View key={topic} style={styles.coverageRow}>
                <Text style={styles.coverageTopic}>{topic}</Text>
                <Text style={styles.coverageCount}>{arts.length} articles</Text>
              </View>
            ))}
        </View>

        {/* Refresh */}
        <Pressable style={styles.refreshBtn} onPress={() => { logEvent('stats_refresh'); forceUpdate(n => n + 1); }}>
          <Ionicons name="refresh" size={16} color="#60a5fa" />
          <Text style={styles.refreshText}>Refresh stats</Text>
        </Pressable>

        {/* Event log */}
        <EventLogSection />

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
  depthBreakdown: { gap: 6 },
  depthRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  depthDot: { width: 10, height: 10, borderRadius: 5 },
  depthLabel: { color: '#cbd5e1', fontSize: 14, flex: 1 },
  depthCount: { color: '#64748b', fontSize: 14, fontWeight: '600' },
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
