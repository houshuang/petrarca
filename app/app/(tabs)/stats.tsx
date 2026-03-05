import { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Share, Animated, Linking, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getStats, getSignals, getArticles, getByTopic, getReadingState, getTopicKnowledgeStats, getConcepts, getVoiceNotes, getArticleById, getConceptReview } from '../../data/store';
import { logEvent, getLogFiles, exportAllLogs, getLogDirectory } from '../../data/logger';
import { transcribeAllPending } from '../../data/transcription';
import { ResearchResult } from '../../data/types';
import { getResearchResults, fetchResearchResults } from '../../data/research';
import { useIsDesktopWeb } from '../../lib/use-responsive';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';

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
        <Text style={styles.sectionHead}>✦ EVENT LOG</Text>
      </Pressable>
      <Text style={styles.sectionSubtitle}>
        {logFileList.length} log file{logFileList.length !== 1 ? 's' : ''} · {getLogDirectory()}
      </Text>

      {expanded && (
        <View style={{ marginTop: 8 }}>
          {logFileList.map(f => (
            <Text key={f} style={styles.logFileName}>{f}</Text>
          ))}
          <Pressable style={[styles.actionBtn, { marginTop: 8 }]} onPress={handleExport}>
            <Ionicons name="share-outline" size={16} color={colors.rubric} />
            <Text style={styles.actionBtnText}>Export all logs</Text>
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
  const barAnims = useRef<Animated.Value[]>([]);

  const sortedTopics = concepts.length > 0
    ? [...topicStats.entries()].sort((a, b) => b[1].total - a[1].total)
    : [];

  // Initialize animation values
  if (barAnims.current.length !== sortedTopics.length) {
    barAnims.current = sortedTopics.map(() => new Animated.Value(0));
  }

  useEffect(() => {
    if (sortedTopics.length === 0) return;
    const animations = barAnims.current.map((anim, i) =>
      Animated.timing(anim, {
        toValue: 1,
        duration: 400,
        delay: i * 60,
        useNativeDriver: false,
      })
    );
    Animated.parallel(animations).start();
  }, [sortedTopics.length]);

  if (concepts.length === 0) {
    return (
      <View style={styles.section}>
        <Text style={styles.sectionHead}>✦ KNOWLEDGE BY TOPIC</Text>
        <Text style={styles.sectionSubtitle}>Concept tracking will appear here as you read and signal on claims</Text>
      </View>
    );
  }

  return (
    <View style={styles.section}>
      <Text style={styles.sectionHead}>✦ KNOWLEDGE BY TOPIC</Text>
      <Text style={styles.sectionSubtitle}>
        {stats.knownConcepts} known · {stats.encounteredConcepts} encountered · {concepts.length} total concepts
      </Text>

      {sortedTopics.map(([topic, counts], idx) => {
        const pct = counts.total > 0 ? ((counts.known + counts.encountered) / counts.total) * 100 : 0;
        const anim = barAnims.current[idx];
        const animatedWidth = anim
          ? anim.interpolate({ inputRange: [0, 1], outputRange: ['0%', `${pct}%`] })
          : `${pct}%` as `${number}%`;
        return (
          <View key={topic} style={styles.topicRow}>
            <View style={styles.topicLabelRow}>
              <Text style={styles.topicName} numberOfLines={1}>{topic}</Text>
              <Text style={styles.topicCount}>{counts.known + counts.encountered}</Text>
            </View>
            <View style={styles.topicBar}>
              <Animated.View style={[styles.topicFill, { width: animatedWidth }]} />
            </View>
          </View>
        );
      })}

      {sortedTopics.length > 0 && (
        <View style={styles.legendRow}>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: colors.ink }]} />
            <Text style={styles.legendLabel}>Known</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: colors.rubric }]} />
            <Text style={styles.legendLabel}>Encountered</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const STATUS_COLORS: Record<string, string> = {
  pending: colors.textMuted,
  processing: colors.info,
  completed: colors.success,
  failed: colors.rubric,
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
      <Text style={styles.sectionHead}>✦ VOICE NOTES</Text>
      <Text style={styles.sectionSubtitle}>
        {notes.length} note{notes.length !== 1 ? 's' : ''} · {totalDuration}s total · {uniqueArticles} article{uniqueArticles !== 1 ? 's' : ''}
        {transcribed > 0 ? ` · ${transcribed} transcribed` : ''}
      </Text>

      {pending > 0 && (
        <Pressable
          style={[styles.actionBtn, { marginBottom: 8, opacity: transcribing ? 0.5 : 1 }]}
          onPress={handleTranscribeAll}
          disabled={transcribing}
        >
          <Ionicons name={transcribing ? 'hourglass-outline' : 'cloud-upload-outline'} size={16} color={colors.rubric} />
          <Text style={styles.actionBtnText}>
            {transcribing ? 'Transcribing...' : `Transcribe All (${pending})`}
          </Text>
        </Pressable>
      )}

      {notes.slice(0, 10).map(n => {
        const article = getArticleById(n.article_id);
        const isExpanded = expandedNote === n.id;
        const statusColor = STATUS_COLORS[n.transcription_status] || colors.textMuted;
        return (
          <Pressable
            key={n.id}
            onPress={() => setExpandedNote(isExpanded ? null : n.id)}
            style={{ marginBottom: 8 }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={styles.rubricDot} />
              <Text style={styles.voiceNoteTitle} numberOfLines={1}>
                {article?.title || n.article_id}
              </Text>
              <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
              <Text style={styles.voiceNoteDuration}>
                {Math.round(n.duration_ms / 1000)}s
              </Text>
            </View>
            {isExpanded && n.transcript && (
              <View style={{ marginLeft: 20, marginTop: 4 }}>
                <Text style={styles.voiceNoteTranscript}>
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
                        <View key={c.id} style={styles.conceptTag}>
                          <Text style={styles.conceptTagText}>{c.name || c.text}</Text>
                        </View>
                      ))}
                    </View>
                  );
                })()}
              </View>
            )}
            {isExpanded && !n.transcript && (
              <Text style={styles.voiceNoteStatus}>
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

function ResearchResultsSection({ onRefresh }: { onRefresh: () => void }) {
  const [results, setResults] = useState<ResearchResult[]>([]);
  const [expandedResult, setExpandedResult] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    getResearchResults().then(setResults);
  }, []);

  const handleFetch = async () => {
    setFetching(true);
    logEvent('research_results_fetch_start');
    const count = await fetchResearchResults();
    const updated = await getResearchResults();
    setResults(updated);
    setFetching(false);
    if (count > 0) onRefresh();
  };

  if (results.length === 0) return null;

  const completed = results.filter(r => r.status === 'completed');
  const pendingResults = results.filter(r => r.status === 'pending' || r.status === 'processing');

  return (
    <View style={styles.section}>
      <Text style={styles.sectionHead}>✦ RESEARCH</Text>
      <Text style={styles.sectionSubtitle}>
        {completed.length} completed{pendingResults.length > 0 ? ` · ${pendingResults.length} in progress` : ''}
      </Text>

      <Pressable
        style={[styles.actionBtn, { marginBottom: 8, opacity: fetching ? 0.5 : 1 }]}
        onPress={handleFetch}
        disabled={fetching}
      >
        <Ionicons name={fetching ? 'hourglass-outline' : 'cloud-download-outline'} size={16} color={colors.rubric} />
        <Text style={styles.actionBtnText}>
          {fetching ? 'Checking...' : 'Check for new results'}
        </Text>
      </Pressable>

      {results.slice(0, 10).map(r => {
        const isExpanded = expandedResult === r.id;
        const statusColor = STATUS_COLORS[r.status] || colors.textMuted;
        return (
          <Pressable
            key={r.id}
            onPress={() => {
              setExpandedResult(isExpanded ? null : r.id);
              if (!isExpanded) {
                logEvent('research_result_viewed', { research_id: r.id, article_id: r.article_id });
              }
            }}
            style={styles.researchCard}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text style={styles.researchTitle} numberOfLines={1}>
                {r.article_title}
              </Text>
              <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
            </View>
            <Text style={styles.researchQuery} numberOfLines={isExpanded ? undefined : 1}>
              {r.query}
            </Text>

            {isExpanded && r.status === 'completed' && (
              <View style={{ marginTop: 10 }}>
                {r.perspectives && r.perspectives.length > 0 && (
                  <View style={{ marginBottom: 10 }}>
                    <Text style={styles.researchSubhead}>Perspectives</Text>
                    {r.perspectives.map((p, i) => (
                      <Text key={i} style={styles.researchItem}>{p}</Text>
                    ))}
                  </View>
                )}
                {r.recommendations && r.recommendations.length > 0 && (
                  <View style={{ marginBottom: 10 }}>
                    <Text style={styles.researchSubhead}>Recommendations</Text>
                    {r.recommendations.map((rec, i) => (
                      <Text key={i} style={styles.researchItem}>{rec}</Text>
                    ))}
                  </View>
                )}
                {r.connections && r.connections.length > 0 && (
                  <View>
                    <Text style={styles.researchSubhead}>Connections</Text>
                    {r.connections.map((c, i) => (
                      <Text key={i} style={styles.researchItem}>{c}</Text>
                    ))}
                  </View>
                )}
              </View>
            )}

            {isExpanded && r.status === 'failed' && r.error && (
              <Text style={styles.researchError}>
                {r.error}
              </Text>
            )}

            {isExpanded && (r.status === 'pending' || r.status === 'processing') && (
              <Text style={styles.researchPending}>
                Research in progress...
              </Text>
            )}
          </Pressable>
        );
      })}
    </View>
  );
}

export default function StatsScreen() {
  const router = useRouter();
  const isDesktop = useIsDesktopWeb();
  const [, forceUpdate] = useState(0);
  const stats = getStats();
  const articles = getArticles();
  const signals = getSignals();
  const topicMap = getByTopic();

  const totalTimeMin = Math.round(stats.totalTimeMs / 60000);
  const totalTimeH = Math.round(totalTimeMin / 60) || totalTimeMin;
  const timeLabel = totalTimeMin >= 60 ? `${totalTimeH}h` : `${totalTimeMin}m`;

  // Topic reading depth breakdown
  const topicDepths = new Map<string, { summary: number; claims: number; concepts: number; sections: number; full: number }>();
  for (const a of articles) {
    const state = getReadingState(a.id);
    if (state.depth === 'unread') continue;
    for (const t of a.topics) {
      if (!topicDepths.has(t)) topicDepths.set(t, { summary: 0, claims: 0, concepts: 0, sections: 0, full: 0 });
      topicDepths.get(t)![state.depth]++;
    }
  }

  const concepts = getConcepts();
  const crossLinks = concepts.filter(c => c.source_article_ids && c.source_article_ids.length > 1).length;

  return (
    <View style={[styles.container, isDesktop && styles.desktopContainer]}>
      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Header */}
        {!isDesktop && (
          <Pressable onPress={() => router.push('/')} style={styles.backLink}>
            <Text style={styles.backLinkText}>← Feed</Text>
          </Pressable>
        )}
        <Text style={styles.screenTitle}>Progress</Text>
        <Text style={styles.screenSubtitle}>Your reading journey at a glance</Text>

        {/* Double rule */}
        <View style={styles.doubleRule}>
          <View style={styles.ruleTop} />
          <View style={styles.ruleBottom} />
        </View>

        {/* Stats row */}
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statNumber}>{stats.total}</Text>
            <Text style={styles.statLabel}>ARTICLES</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNumber}>{concepts.length}</Text>
            <Text style={styles.statLabel}>CONCEPTS</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNumber}>{crossLinks}</Text>
            <Text style={styles.statLabel}>LINKS</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNumber}>{timeLabel}</Text>
            <Text style={styles.statLabel}>READING</Text>
          </View>
        </View>

        {/* Reading depth */}
        {stats.read > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionHead}>✦ READING DEPTH</Text>
            <View style={styles.depthGrid}>
              {([['Summary', stats.summary, false], ['Claims', stats.claims, true],
                ['Sections', stats.sections, false], ['Full', stats.full, false]] as const).map(([label, count, highlighted]) => (
                <View key={label} style={styles.depthCell}>
                  <Text style={[styles.depthNumber, highlighted && { color: colors.rubric }]}>{count}</Text>
                  <Text style={styles.depthLabel}>{label}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Topic coverage */}
        {topicDepths.size > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionHead}>✦ TOPICS EXPLORED</Text>
            {[...topicDepths.entries()]
              .sort((a, b) => Object.values(b[1]).reduce((s, n) => s + n, 0) - Object.values(a[1]).reduce((s, n) => s + n, 0))
              .map(([topic, counts]) => {
                const total = Object.values(counts).reduce((s, n) => s + n, 0);
                const pct = stats.read > 0 ? (total / stats.read) * 100 : 0;
                return (
                  <View key={topic} style={styles.topicRow}>
                    <View style={styles.topicLabelRow}>
                      <Text style={styles.topicName} numberOfLines={1}>{topic}</Text>
                      <Text style={styles.topicCount}>{total}</Text>
                    </View>
                    <View style={styles.topicBar}>
                      <View style={[styles.topicFill, { width: `${Math.min(pct, 100)}%` }]} />
                    </View>
                  </View>
                );
              })}
          </View>
        )}

        {/* Content sources */}
        <View style={styles.section}>
          <Text style={styles.sectionHead}>✦ CONTENT SOURCES</Text>
          {[...topicMap.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .slice(0, 10)
            .map(([topic, arts]) => (
              <View key={topic} style={styles.sourceRow}>
                <Text style={styles.sourceTopic} numberOfLines={1}>{topic}</Text>
                <Text style={styles.sourceCount}>{arts.length}</Text>
              </View>
            ))}
        </View>

        {/* Research results */}
        <ResearchResultsSection onRefresh={() => forceUpdate(n => n + 1)} />

        {/* Knowledge dashboard */}
        <KnowledgeDashboard />

        {/* Voice notes summary */}
        <VoiceNotesSection onRefresh={() => forceUpdate(n => n + 1)} />

        {/* Refresh */}
        <Pressable style={styles.actionBtn} onPress={() => { logEvent('stats_refresh'); forceUpdate(n => n + 1); }}>
          <Ionicons name="refresh" size={16} color={colors.rubric} />
          <Text style={styles.actionBtnText}>Refresh stats</Text>
        </Pressable>

        {/* Event log */}
        <EventLogSection />

        {/* User guide link */}
        <Pressable
          style={styles.actionBtn}
          onPress={() => {
            logEvent('user_guide_opened');
            const guideUrl = Platform.OS === 'web'
              ? '/guide/'
              : 'https://alifstian.duckdns.org/guide/';
            Linking.openURL(guideUrl);
          }}
        >
          <Ionicons name="book-outline" size={16} color={colors.rubric} />
          <Text style={styles.actionBtnText}>User Guide</Text>
        </Pressable>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  desktopContainer: { maxWidth: layout.contentMaxWidth, alignSelf: 'center' as const, width: '100%' as any },
  scroll: { flex: 1, paddingHorizontal: layout.screenPadding, paddingTop: 12 },

  // Header
  backLink: {
    marginBottom: 4,
  },
  backLinkText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textMuted,
  },
  screenTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  screenSubtitle: {
    ...type.screenSubtitle,
    color: colors.textMuted,
    marginTop: 2,
  },

  // Double rule
  doubleRule: {
    marginTop: 12,
    marginBottom: 16,
    gap: layout.doubleRuleGap,
  },
  ruleTop: {
    height: layout.doubleRuleTop,
    backgroundColor: colors.ink,
  },
  ruleBottom: {
    height: layout.doubleRuleBottom,
    backgroundColor: colors.ink,
  },

  // Stats row
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingBottom: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
    marginBottom: 20,
  },
  statItem: {
    alignItems: 'center',
  },
  statNumber: {
    ...type.statNumber,
    color: colors.ink,
  },
  statLabel: {
    ...type.statLabel,
    color: colors.textMuted,
    marginTop: 2,
  },

  // Sections
  section: { marginBottom: 24 },
  sectionHead: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 4,
  },
  sectionSubtitle: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginBottom: 12,
  },

  // Reading depth
  depthGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 8,
  },
  depthCell: {
    alignItems: 'center',
    flex: 1,
  },
  depthNumber: {
    fontFamily: fonts.body,
    fontSize: 18,
    color: colors.ink,
  },
  depthLabel: {
    fontFamily: fonts.ui,
    fontSize: 8,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: 2,
  },

  // Topic rows (shared by Topics Explored and Knowledge By Topic)
  topicRow: {
    marginBottom: 10,
  },
  topicLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 3,
  },
  topicName: {
    fontFamily: fonts.body,
    fontSize: 13.5,
    color: colors.ink,
    flex: 1,
    marginRight: 8,
  },
  topicCount: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
  topicBar: {
    height: layout.progressBarHeight,
    backgroundColor: colors.rule,
    overflow: 'hidden',
  },
  topicFill: {
    height: '100%',
    backgroundColor: colors.ink,
  },

  // Source rows
  sourceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  sourceTopic: {
    fontFamily: fonts.body,
    fontSize: 13.5,
    color: colors.ink,
    flex: 1,
    marginRight: 8,
  },
  sourceCount: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },

  // Legend
  legendRow: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 8,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  legendDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  legendLabel: {
    fontFamily: fonts.ui,
    fontSize: 9,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },

  // Action buttons
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    marginTop: 8,
  },
  actionBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },

  // Status dot
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },

  // Rubric dot
  rubricDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rubric,
  },

  // Voice notes
  voiceNoteTitle: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.ink,
    flex: 1,
  },
  voiceNoteDuration: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
  voiceNoteTranscript: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 19,
    color: colors.textSecondary,
  },
  voiceNoteStatus: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 4,
    marginLeft: 20,
  },
  conceptTag: {
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  conceptTagText: {
    fontFamily: fonts.body,
    fontSize: 11,
    color: colors.rubric,
  },

  // Research results
  researchCard: {
    paddingVertical: 10,
    paddingLeft: 12,
    marginBottom: 8,
    borderLeftWidth: 2,
    borderLeftColor: colors.rubric,
  },
  researchTitle: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.ink,
    flex: 1,
  },
  researchQuery: {
    fontFamily: fonts.reading,
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 4,
  },
  researchSubhead: {
    fontFamily: fonts.uiMedium,
    fontSize: 9,
    color: colors.rubric,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  researchItem: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 20,
    color: colors.textBody,
    marginBottom: 8,
    paddingLeft: 8,
    borderLeftWidth: 1,
    borderLeftColor: colors.rule,
  },
  researchError: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: colors.rubric,
    marginTop: 6,
  },
  researchPending: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: colors.warning,
    marginTop: 6,
  },

  // Event log
  logFileName: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.textSecondary,
    marginBottom: 2,
  },
});
