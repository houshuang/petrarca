import { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, Platform, ActivityIndicator } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { setFeedbackContext } from '../lib/feedback-context';
import { RESEARCH_BASE } from '../lib/chat-api';
import DoubleRule from '../components/DoubleRule';

interface Node {
  id: string;
  title: string;
  description: string;
  level: number;
  parent_id: string | null;
  prerequisites: string[];
  obscurity: number;
}

interface Answer {
  familiarity: 'new_to_me' | 'knew_some' | 'knew_all';
  interest: 'interested' | 'star' | 'skip';
  title: string;
}

export default function CurriculumScanScreen() {
  const router = useRouter();
  const { domainId } = useLocalSearchParams<{ domainId: string }>();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [domainTitle, setDomainTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [queue, setQueue] = useState<Node[]>([]);
  const [current, setCurrent] = useState(0);
  const [answered, setAnswered] = useState<Record<string, Answer>>({});
  const [history, setHistory] = useState<{ nodeId: string; index: number }[]>([]);
  const [selectedInterest, setSelectedInterest] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<string | null>(null);
  const sortedRef = useRef<Node[]>([]);

  useEffect(() => {
    setFeedbackContext({ screen: 'curriculum-scan' });
  }, []);

  // Load curriculum
  useEffect(() => {
    if (!domainId) return;
    fetch(`${RESEARCH_BASE}/curriculum/${domainId}`)
      .then(r => r.json())
      .then(data => {
        const allNodes = (data.nodes || []).filter((n: Node) => n.level >= 2);
        setNodes(allNodes);
        setDomainTitle(data.title || domainId);
        // Sort: level 2 first (major topics), then level 3, then by obscurity
        const sorted = [...allNodes].sort((a: Node, b: Node) => {
          if (a.level !== b.level) return a.level - b.level;
          return Math.abs(a.obscurity - 2.5) - Math.abs(b.obscurity - 2.5);
        });
        sortedRef.current = sorted;
        setQueue(sorted);
        setLoading(false);
        logEvent('curriculum_scan_start', { domain_id: domainId, node_count: data.nodes?.length });
      })
      .catch(() => setLoading(false));
  }, [domainId]);

  // Skip children of "new to me" nodes
  const skipChildren = useCallback((nodeId: string, q: Node[]) => {
    return q.filter(n => {
      if (n.parent_id === nodeId) return false;
      if (n.prerequisites?.includes(nodeId)) return false;
      return true;
    });
  }, []);

  // Handle answer
  const handleAnswer = useCallback((familiarity: Answer['familiarity']) => {
    if (current >= queue.length) return;
    const node = queue[current];
    const interest = (selectedInterest as Answer['interest']) || 'interested';

    const newAnswered = { ...answered, [node.id]: { familiarity, interest, title: node.title } };
    const newHistory = [...history, { nodeId: node.id, index: current }];

    let newQueue = [...queue];
    if (familiarity === 'new_to_me') {
      newQueue = skipChildren(node.id, newQueue);
    }

    setAnswered(newAnswered);
    setHistory(newHistory);
    setQueue(newQueue);
    setSelectedInterest(null);

    const nextIdx = current + 1;
    if (nextIdx >= newQueue.length) {
      setDone(true);
      saveResults(newAnswered);
    } else {
      setCurrent(nextIdx);
    }
  }, [current, queue, answered, history, selectedInterest, skipChildren]);

  // Go back
  const goBack = useCallback(() => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    const newHistory = history.slice(0, -1);
    const newAnswered = { ...answered };
    delete newAnswered[prev.nodeId];

    // Rebuild queue from sorted, applying skip-children for all remaining "new_to_me" answers
    let rebuilt = [...sortedRef.current];
    for (const [id, ans] of Object.entries(newAnswered)) {
      if (ans.familiarity === 'new_to_me') {
        rebuilt = rebuilt.filter(n => n.parent_id !== id && !n.prerequisites?.includes(id));
      }
    }

    const newCurrent = rebuilt.findIndex(n => n.id === prev.nodeId);
    setHistory(newHistory);
    setAnswered(newAnswered);
    setQueue(rebuilt);
    setCurrent(newCurrent >= 0 ? newCurrent : 0);
    setSelectedInterest(null);
  }, [history, answered]);

  // Save results to server
  const saveResults = async (answers: Record<string, Answer>) => {
    setSaving(true);
    try {
      const resp = await fetch(`${RESEARCH_BASE}/curriculum/knowledge/import-assessment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: domainId, answers }),
      });
      const data = await resp.json();
      if (resp.ok) {
        setSaveResult(`Saved ${data.imported} nodes`);
        logEvent('curriculum_scan_complete', { domain_id: domainId, imported: data.imported, by_level: data.by_level });
      } else {
        setSaveResult(`Save failed: ${data.error}`);
      }
    } catch (e: any) {
      setSaveResult(`Save failed: ${e.message}`);
    }
    setSaving(false);
  };

  // Web keyboard shortcuts
  useEffect(() => {
    if (Platform.OS !== 'web' || done) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === '1') handleAnswer('new_to_me');
      else if (e.key === '2') handleAnswer('knew_some');
      else if (e.key === '3') handleAnswer('knew_all');
      else if (e.key === 'q' || e.key === 'Q') setSelectedInterest(prev => prev === 'skip' ? null : 'skip');
      else if (e.key === 'e' || e.key === 'E') setSelectedInterest(prev => prev === 'star' ? null : 'star');
      else if (e.key === 'Backspace') { e.preventDefault(); goBack(); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleAnswer, goBack, done]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.rubric} size="large" />
      </View>
    );
  }

  const totalNodes = nodes.length;
  const answeredCount = Object.keys(answered).length;
  const progressPct = totalNodes > 0 ? (answeredCount / totalNodes) * 100 : 0;
  const currentNode = !done && current < queue.length ? queue[current] : null;

  const isWeb = Platform.OS === 'web';
  const containerStyle = isWeb
    ? [styles.container, { maxWidth: layout.readingMeasure, alignSelf: 'center' as const, width: '100%' as any }]
    : styles.container;

  // Results summary
  if (done) {
    const groups = { knew_all: [] as string[], knew_some: [] as string[], new_to_me: [] as string[] };
    for (const [, ans] of Object.entries(answered)) {
      groups[ans.familiarity].push(ans.title);
    }
    const skipped = totalNodes - answeredCount;

    return (
      <ScrollView style={{ flex: 1, backgroundColor: colors.parchment }}>
        <View style={containerStyle}>
          <View style={styles.header}>
            <Pressable onPress={() => router.back()} hitSlop={12}>
              <Text style={styles.backText}>← Knowledge Map</Text>
            </Pressable>
            <Text style={styles.pageTitle}>Scan Complete</Text>
            <Text style={styles.subtitle}>{domainTitle}</Text>
          </View>
          <DoubleRule />

          <View style={styles.resultSection}>
            {saving ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <ActivityIndicator color={colors.rubric} size="small" />
                <Text style={styles.saveText}>Saving...</Text>
              </View>
            ) : saveResult ? (
              <Text style={[styles.saveText, { color: saveResult.startsWith('Saved') ? colors.claimNew : colors.rubric }]}>
                ✦ {saveResult}
              </Text>
            ) : null}

            {groups.knew_all.length > 0 && (
              <View style={styles.resultGroup}>
                <Text style={styles.resultGroupLabel}>✦ Already knew all this ({groups.knew_all.length})</Text>
                {groups.knew_all.map((t, i) => <Text key={i} style={styles.resultItem}>{t}</Text>)}
              </View>
            )}
            {groups.knew_some.length > 0 && (
              <View style={styles.resultGroup}>
                <Text style={styles.resultGroupLabel}>✦ Knew some of this ({groups.knew_some.length})</Text>
                {groups.knew_some.map((t, i) => <Text key={i} style={styles.resultItem}>{t}</Text>)}
              </View>
            )}
            {groups.new_to_me.length > 0 && (
              <View style={styles.resultGroup}>
                <Text style={styles.resultGroupLabel}>✦ New to me ({groups.new_to_me.length})</Text>
                {groups.new_to_me.map((t, i) => <Text key={i} style={styles.resultItem}>{t}</Text>)}
              </View>
            )}
            {skipped > 0 && (
              <Text style={styles.skippedText}>+ {skipped} skipped (children of unknown topics)</Text>
            )}

            <Pressable style={styles.doneButton} onPress={() => router.back()}>
              <Text style={styles.doneButtonText}>← Back to Knowledge Map</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.parchment }}>
      <View style={[containerStyle, styles.scanColumn]}>
        {/* Header */}
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12}>
            <Text style={styles.backText}>← Knowledge Map</Text>
          </Pressable>
          <Text style={styles.subtitle} numberOfLines={3} ellipsizeMode="tail">
            {domainTitle}
          </Text>
        </View>

        {/* Progress bar */}
        <View style={styles.progressSection}>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progressPct}%` as any }]} />
          </View>
          <View style={styles.progressLabels}>
            <Text style={styles.progressText}>{answeredCount} / {totalNodes} assessed</Text>
            <Text style={styles.progressText}>{queue.length - current} remaining</Text>
          </View>
        </View>

        {/* Card */}
        {currentNode && (
          <View style={styles.card}>
            <View style={styles.cardTop}>
              <Text style={styles.questionNum}>Question {answeredCount + 1}</Text>
              {history.length > 0 && (
                <Pressable style={styles.backBtn} onPress={goBack}>
                  <Text style={styles.backBtnText}>← Back</Text>
                </Pressable>
              )}
            </View>

            <ScrollView
              style={styles.cardScroll}
              contentContainerStyle={styles.cardScrollContent}
              keyboardShouldPersistTaps="handled"
              nestedScrollEnabled
              showsVerticalScrollIndicator
            >
              <Text style={styles.cardTitle}>{currentNode.title}</Text>
              <Text style={styles.cardPrompt}>Read the description, then: did you already know this?</Text>
              <Text style={styles.cardDesc}>{currentNode.description}</Text>
            </ScrollView>

            <View style={styles.cardActions}>
              {/* Familiarity buttons */}
              <View style={styles.responseRow}>
                <Pressable style={styles.respBtn} onPress={() => handleAnswer('new_to_me')}>
                  {isWeb && <Text style={styles.keyHint}>1</Text>}
                  <Text style={styles.respText}>New to me</Text>
                </Pressable>
                <Pressable style={styles.respBtn} onPress={() => handleAnswer('knew_some')}>
                  {isWeb && <Text style={styles.keyHint}>2</Text>}
                  <Text style={styles.respText}>Knew some</Text>
                </Pressable>
                <Pressable style={styles.respBtn} onPress={() => handleAnswer('knew_all')}>
                  {isWeb && <Text style={styles.keyHint}>3</Text>}
                  <Text style={styles.respText}>Knew all</Text>
                </Pressable>
              </View>

              {/* Interest buttons */}
              <View style={styles.interestRow}>
                <Pressable
                  style={[styles.intBtn, selectedInterest === 'skip' && styles.intBtnActive]}
                  onPress={() => setSelectedInterest(selectedInterest === 'skip' ? null : 'skip')}
                >
                  {isWeb && <Text style={styles.keyHint}>Q</Text>}
                  <Text style={styles.intText}>– Only if prereq</Text>
                </Pressable>
                <Pressable
                  style={[styles.intBtn, selectedInterest === 'star' && styles.intBtnActive]}
                  onPress={() => setSelectedInterest(selectedInterest === 'star' ? null : 'star')}
                >
                  {isWeb && <Text style={styles.keyHint}>E</Text>}
                  <Text style={styles.intText}>★ Fascinating</Text>
                </Pressable>
              </View>

              {isWeb && (
                <Text style={styles.keyLegend}>1-3 familiarity · Q skip / E star (optional) · Backspace back</Text>
              )}
            </View>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scanColumn: {
    flex: 1,
    minHeight: 0,
  },
  container: {
    flex: 1,
    paddingHorizontal: layout.screenPadding,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.parchment,
  },
  header: {
    paddingTop: 12,
    paddingBottom: 8,
  },
  backText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.rubric,
    marginBottom: 8,
  },
  pageTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  subtitle: {
    ...type.screenSubtitle,
    color: colors.textSecondary,
    marginTop: 2,
  },

  // Progress
  progressSection: {
    paddingVertical: 12,
  },
  progressTrack: {
    height: 4,
    backgroundColor: colors.rule,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.rubric,
    borderRadius: 2,
  },
  progressLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  progressText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },

  // Card — flex so long descriptions scroll; actions stay on screen
  card: {
    flex: 1,
    minHeight: 0,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 6,
    padding: 24,
    marginTop: 8,
    marginBottom: 8,
  },
  cardScroll: {
    flex: 1,
    minHeight: 0,
  },
  cardScrollContent: {
    flexGrow: 1,
    paddingBottom: 8,
  },
  cardActions: {
    flexShrink: 0,
    paddingTop: 16,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  questionNum: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  backBtn: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 16,
  },
  backBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
  cardTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 22,
    color: colors.ink,
    marginBottom: 12,
    lineHeight: 28,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  cardPrompt: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textSecondary,
    fontStyle: 'italic',
    marginBottom: 12,
  },
  cardDesc: {
    fontFamily: fonts.reading,
    fontSize: 15,
    lineHeight: 23,
    color: colors.textBody,
  },

  // Response buttons
  responseRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  respBtn: {
    flex: 1,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 4,
    alignItems: 'center',
    gap: 4,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  respText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.ink,
  },

  // Interest buttons
  interestRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 8,
  },
  intBtn: {
    flex: 1,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 4,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 4,
  },
  intBtnActive: {
    borderColor: colors.rubric,
    backgroundColor: 'rgba(139,37,0,0.05)',
  },
  intText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.textSecondary,
  },

  keyHint: {
    fontFamily: fonts.uiSemiBold,
    fontSize: 10,
    color: colors.textMuted,
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 3,
    overflow: 'hidden',
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  keyLegend: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 4,
  },

  // Results
  resultSection: {
    paddingTop: 20,
    paddingBottom: 60,
  },
  saveText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textMuted,
    marginBottom: 16,
  },
  resultGroup: {
    marginBottom: 20,
  },
  resultGroupLabel: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 8,
  },
  resultItem: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 22,
    color: colors.textBody,
    paddingLeft: 12,
  },
  skippedText: {
    fontFamily: fonts.readingItalic,
    fontSize: 13,
    color: colors.textMuted,
    marginTop: 8,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  doneButton: {
    backgroundColor: colors.ink,
    paddingVertical: 14,
    borderRadius: 4,
    alignItems: 'center',
    marginTop: 24,
  },
  doneButtonText: {
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.parchment,
  },
});
