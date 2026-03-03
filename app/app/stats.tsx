import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Share } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getStats, getSignals, getArticles, getByTopic, getReadingState, getTopicKnowledgeStats, getConcepts, getVoiceNotes, getArticleById, getConceptReview } from '../data/store';
import { logEvent, getLogFiles, exportAllLogs, getLogDirectory } from '../data/logger';
import { transcribeAllPending } from '../data/transcription';

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

function KnowledgeDashboard() {
  const concepts = getConcepts();
  const stats = getStats();
  const topicStats = getTopicKnowledgeStats();

  if (concepts.length === 0) {
    return (
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Knowledge Map</Text>
        <Text style={styles.sectionSubtitle}>Concept tracking will appear here as you read and signal on claims</Text>
      </View>
    );
  }

  const sortedTopics = [...topicStats.entries()]
    .sort((a, b) => b[1].total - a[1].total);

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Knowledge Map</Text>
      <Text style={styles.sectionSubtitle}>
        {stats.knownConcepts} known · {stats.encounteredConcepts} encountered · {concepts.length} total concepts
      </Text>

      {/* Overall progress */}
      <View style={[styles.progressBar, { marginTop: 8, marginBottom: 16 }]}>
        <View style={[styles.progressFill, {
          width: `${Math.round(((stats.knownConcepts + stats.encounteredConcepts) / Math.max(1, concepts.length)) * 100)}%`,
          backgroundColor: '#10b981',
        }]} />
      </View>

      {/* Per-topic breakdown */}
      {sortedTopics.map(([topic, counts]) => {
        const knownPct = counts.total > 0 ? (counts.known / counts.total) * 100 : 0;
        const encounteredPct = counts.total > 0 ? (counts.encountered / counts.total) * 100 : 0;
        return (
          <View key={topic} style={styles.topicRow}>
            <Text style={styles.topicName} numberOfLines={1}>{topic}</Text>
            <View style={styles.topicBar}>
              {counts.known > 0 && <View style={[styles.topicSegment, { width: `${knownPct}%`, backgroundColor: '#10b981' }]} />}
              {counts.encountered > 0 && <View style={[styles.topicSegment, { width: `${encounteredPct}%`, backgroundColor: '#f59e0b' }]} />}
            </View>
            <Text style={styles.topicCount}>{counts.known + counts.encountered}/{counts.total}</Text>
          </View>
        );
      })}

      {sortedTopics.length > 0 && (
        <View style={{ flexDirection: 'row', gap: 16, marginTop: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#10b981' }} />
            <Text style={{ color: '#64748b', fontSize: 11 }}>Known</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#f59e0b' }} />
            <Text style={{ color: '#64748b', fontSize: 11 }}>Encountered</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#64748b',
  processing: '#3b82f6',
  completed: '#10b981',
  failed: '#ef4444',
};

function VoiceNotesSection({ onRefresh }: { onRefresh: () => void }) {
  const notes = getVoiceNotes();
  const [expandedNote, setExpandedNote] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);

  if (notes.length === 0) return null;

  const totalDuration = Math.round(notes.reduce((s, n) => s + n.duration_ms, 0) / 1000);
  const transcribed = notes.filter(n => n.transcription_status === 'completed').length;
  const pending = notes.filter(n => n.transcription_status === 'pending').length;
  const uniqueArticles = new Set(notes.map(n => n.article_id)).size;

  const handleTranscribeAll = async () => {
    setTranscribing(true);
    logEvent('transcribe_all_start', { pending_count: pending });
    const completed = await transcribeAllPending(notes);
    logEvent('transcribe_all_complete', { completed_count: completed });
    setTranscribing(false);
    onRefresh();
  };

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Voice Notes</Text>
      <Text style={styles.sectionSubtitle}>
        {notes.length} note{notes.length !== 1 ? 's' : ''} · {totalDuration}s total · {uniqueArticles} article{uniqueArticles !== 1 ? 's' : ''}
        {transcribed > 0 ? ` · ${transcribed} transcribed` : ''}
      </Text>

      {pending > 0 && (
        <Pressable
          style={[styles.refreshBtn, { marginBottom: 8, opacity: transcribing ? 0.5 : 1 }]}
          onPress={handleTranscribeAll}
          disabled={transcribing}
        >
          <Ionicons name={transcribing ? 'hourglass-outline' : 'cloud-upload-outline'} size={16} color="#60a5fa" />
          <Text style={styles.refreshText}>
            {transcribing ? 'Transcribing...' : `Transcribe All (${pending})`}
          </Text>
        </Pressable>
      )}

      {notes.slice(0, 10).map(n => {
        const article = getArticleById(n.article_id);
        const isExpanded = expandedNote === n.id;
        const statusColor = STATUS_COLORS[n.transcription_status] || '#64748b';
        return (
          <Pressable
            key={n.id}
            onPress={() => setExpandedNote(isExpanded ? null : n.id)}
            style={{ marginBottom: 8 }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="mic" size={14} color="#60a5fa" />
              <Text style={{ color: '#cbd5e1', fontSize: 13, flex: 1 }} numberOfLines={1}>
                {article?.title || n.article_id}
              </Text>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: statusColor }} />
              <Text style={{ color: '#64748b', fontSize: 11 }}>
                {Math.round(n.duration_ms / 1000)}s
              </Text>
            </View>
            {isExpanded && n.transcript && (
              <View style={{ marginLeft: 22, marginTop: 4 }}>
                <Text style={{ color: '#94a3b8', fontSize: 13, lineHeight: 19 }}>
                  {n.transcript}
                </Text>
                {(() => {
                  const matched = getConcepts().filter(c => {
                    const review = getConceptReview(c.id);
                    return review?.notes.some(note => note.voice_note_id === n.id);
                  });
                  if (matched.length === 0) return null;
                  return (
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                      {matched.map(c => (
                        <View key={c.id} style={{ backgroundColor: '#3b1f7e', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 }}>
                          <Text style={{ color: '#c4b5fd', fontSize: 11 }}>{c.text}</Text>
                        </View>
                      ))}
                    </View>
                  );
                })()}
              </View>
            )}
            {isExpanded && !n.transcript && (
              <Text style={{ color: '#64748b', fontSize: 12, marginTop: 4, marginLeft: 22, fontStyle: 'italic' }}>
                {n.transcription_status === 'pending' ? 'Pending transcription' :
                 n.transcription_status === 'processing' ? 'Transcribing...' :
                 n.transcription_status === 'failed' ? 'Transcription failed' : 'No transcript'}
              </Text>
            )}
          </Pressable>
        );
      })}
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

        {/* Knowledge dashboard */}
        <KnowledgeDashboard />

        {/* Voice notes summary */}
        <VoiceNotesSection onRefresh={() => forceUpdate(n => n + 1)} />

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
