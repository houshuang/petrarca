import { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking,
  NativeSyntheticEvent, NativeScrollEvent, LayoutChangeEvent,
  Platform,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { getArticleById, getReadingState, updateReadingState, addSignal, processClaimSignalForConcepts, getRelatedArticles, addVoiceNote, getVoiceNotes } from '../data/store';
import { ReadingDepth, VoiceNote } from '../data/types';
import { logEvent } from '../data/logger';

// --- Local types for claim signal tracking ---

type ClaimSignalType = 'knew_it' | 'interesting' | 'save';

interface ClaimSignalState {
  [claimIndex: number]: ClaimSignalType;
}

// --- Depth zone definitions ---

const DEPTH_ZONES = ['summary', 'claims', 'sections', 'full'] as const;
type DepthZone = typeof DEPTH_ZONES[number];

const DEPTH_LABELS: Record<DepthZone, string> = {
  summary: 'Summary',
  claims: 'Claims',
  sections: 'Sections',
  full: 'Full Article',
};

// --- Implicit tracking constants ---

const PAUSE_THRESHOLD_MS = 3000;
const VELOCITY_SAMPLE_INTERVAL_MS = 200;
const REVISIT_SCROLL_BACK_PX = 150;

// --- Floating Depth Indicator ---

function FloatingDepthIndicator({ currentZone }: { currentZone: DepthZone }) {
  return (
    <View style={styles.depthIndicator}>
      {DEPTH_ZONES.map((zone, i) => {
        const active = zone === currentZone;
        const idx = DEPTH_ZONES.indexOf(zone);
        const currentIdx = DEPTH_ZONES.indexOf(currentZone);
        const reached = idx <= currentIdx;
        return (
          <View key={zone} style={styles.depthIndicatorItem}>
            {i > 0 && <Text style={styles.depthDot}>·</Text>}
            <Text style={[
              styles.depthLabel,
              active && styles.depthLabelActive,
              reached && !active && styles.depthLabelReached,
            ]}>
              {DEPTH_LABELS[zone]}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

// --- Claim signal pill (floating over inline claims) ---

function ClaimSignalPill({ currentSignal, onSignal, onDismiss }: {
  currentSignal?: ClaimSignalType;
  onSignal: (s: ClaimSignalType) => void;
  onDismiss: () => void;
}) {
  return (
    <Pressable style={styles.pillBackdrop} onPress={onDismiss}>
      <View style={styles.pillContainer}>
        {currentSignal && (
          <Text style={{ color: '#64748b', fontSize: 11, marginBottom: 4 }}>
            Already marked · tap to change
          </Text>
        )}
        <View style={{ flexDirection: 'row', gap: 4 }}>
          <Pressable style={[styles.pillBtn, currentSignal === 'knew_it' && { backgroundColor: '#334155' }]} onPress={() => onSignal('knew_it')}>
            <Text style={styles.pillBtnText}>{currentSignal === 'knew_it' ? '✓ ' : ''}Knew this</Text>
          </Pressable>
          <Pressable style={[styles.pillBtn, styles.pillBtnNew, currentSignal === 'interesting' && { backgroundColor: '#064e3b' }]} onPress={() => onSignal('interesting')}>
            <Text style={[styles.pillBtnText, { color: '#34d399' }]}>{currentSignal === 'interesting' ? '✓ ' : ''}New to me</Text>
          </Pressable>
          <Pressable style={[styles.pillBtn, styles.pillBtnSave, currentSignal === 'save' && { backgroundColor: '#1e3a5f' }]} onPress={() => onSignal('save')}>
            <Text style={[styles.pillBtnText, { color: '#60a5fa' }]}>{currentSignal === 'save' ? '✓ ' : ''}Save</Text>
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

// --- Simple markdown renderer ---

function MarkdownText({ content, claimHighlights, claimSignals, onClaimTap }: {
  content: string;
  claimHighlights?: string[];
  claimSignals?: ClaimSignalState;
  onClaimTap?: (claimIndex: number) => void;
}) {
  if (!content) return null;

  const paragraphs = content.split('\n\n').filter(Boolean);

  return (
    <View>
      {paragraphs.map((p, i) => {
        const trimmed = p.trim();

        // Heading
        const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/m);
        if (headingMatch) {
          const level = headingMatch[1].length;
          return (
            <Text key={i} style={[
              styles.markdownHeading,
              level === 1 && { fontSize: 22 },
              level === 2 && { fontSize: 19 },
              level === 3 && { fontSize: 17 },
            ]}>
              {headingMatch[2]}
            </Text>
          );
        }

        // List item
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          const items = trimmed.split('\n').filter(l => l.trim().startsWith('- ') || l.trim().startsWith('* '));
          return (
            <View key={i} style={styles.markdownList}>
              {items.map((item, j) => (
                <View key={j} style={styles.markdownListItem}>
                  <Text style={styles.markdownBullet}>·</Text>
                  <Text style={styles.markdownText}>{item.replace(/^[-*]\s+/, '')}</Text>
                </View>
              ))}
            </View>
          );
        }

        // Code block
        if (trimmed.startsWith('```')) {
          const code = trimmed.replace(/^```\w*\n?/, '').replace(/\n?```$/, '');
          return (
            <View key={i} style={styles.codeBlock}>
              <Text style={styles.codeText}>{code}</Text>
            </View>
          );
        }

        // Check for claim highlighting
        if (claimHighlights && claimHighlights.length > 0) {
          const matchedClaimIndex = findMatchingClaim(trimmed, claimHighlights);
          if (matchedClaimIndex >= 0) {
            const signal = claimSignals?.[matchedClaimIndex];
            const highlightStyle = signal === 'knew_it'
              ? styles.claimHighlightKnew
              : signal === 'interesting'
              ? styles.claimHighlightNew
              : signal === 'save'
              ? styles.claimHighlightSave
              : styles.claimHighlightUnsignaled;

            return (
              <Pressable
                key={i}
                onPress={() => onClaimTap?.(matchedClaimIndex)}
              >
                <Text style={[styles.markdownText, highlightStyle]}>{trimmed}</Text>
              </Pressable>
            );
          }
        }

        // Regular paragraph
        return (
          <Text key={i} style={styles.markdownText}>{trimmed}</Text>
        );
      })}
    </View>
  );
}

// Find if a paragraph contains text matching a claim
function findMatchingClaim(paragraph: string, claims: string[]): number {
  const normalizedParagraph = paragraph.toLowerCase().replace(/[^\w\s]/g, '');

  for (let i = 0; i < claims.length; i++) {
    const normalizedClaim = claims[i].toLowerCase().replace(/[^\w\s]/g, '');

    // Try exact substring first (most reliable)
    const matchFragment = normalizedClaim.slice(0, 60);
    if (matchFragment.length > 10 && normalizedParagraph.includes(matchFragment)) {
      return i;
    }

    // Fallback: content word overlap (handles paraphrased claims)
    const claimWords = normalizedClaim.split(/\s+/).filter(w => w.length > 3);
    if (claimWords.length < 3) continue;
    const paragraphWords = new Set(normalizedParagraph.split(/\s+/));
    const overlap = claimWords.filter(w => paragraphWords.has(w)).length;
    if (overlap / claimWords.length > 0.6) {
      return i;
    }
  }
  return -1;
}

// --- Section card (expandable) ---

function SectionCard({ section, index, expanded, onToggle }: {
  section: { heading: string; content: string; summary: string; key_claims: string[] };
  index: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <View style={styles.sectionCard}>
      <Pressable onPress={onToggle} style={styles.sectionHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.sectionHeading}>{section.heading}</Text>
          {!expanded && section.summary && (
            <Text style={styles.sectionSummary} numberOfLines={2}>{section.summary}</Text>
          )}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color="#64748b" />
      </Pressable>

      {expanded && (
        <View style={styles.sectionContent}>
          {section.key_claims.length > 0 && (
            <View style={styles.sectionClaims}>
              {section.key_claims.map((c, i) => (
                <View key={i} style={styles.claimRow}>
                  <Text style={styles.claimArrow}>→</Text>
                  <Text style={styles.claimRowText}>{c}</Text>
                </View>
              ))}
            </View>
          )}
          <MarkdownText content={section.content} />
        </View>
      )}
    </View>
  );
}

// --- Voice recording button ---

function VoiceRecordButton({ articleId, currentDepth }: {
  articleId: string;
  currentDepth: ReadingDepth;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [noteCount, setNoteCount] = useState(() => getVoiceNotes(articleId).length);

  const startRecording = useCallback(async () => {
    try {
      if (Platform.OS === 'web') {
        logEvent('voice_note_unavailable', { reason: 'web_platform' });
        return;
      }
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        logEvent('voice_note_permission_denied', { article_id: articleId });
        return;
      }
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      recordingRef.current = recording;
      setIsRecording(true);
      setRecordingDuration(0);
      timerRef.current = setInterval(() => setRecordingDuration(d => d + 1), 1000);
      logEvent('voice_note_start', { article_id: articleId, depth: currentDepth });
    } catch (e) {
      console.warn('[voice] failed to start recording:', e);
    }
  }, [articleId, currentDepth]);

  const stopRecording = useCallback(async () => {
    if (!recordingRef.current) return;
    try {
      if (timerRef.current) clearInterval(timerRef.current);
      await recordingRef.current.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });

      const uri = recordingRef.current.getURI();
      const status = await recordingRef.current.getStatusAsync();
      recordingRef.current = null;
      setIsRecording(false);

      if (uri) {
        const noteId = `vn_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
        const note: VoiceNote = {
          id: noteId,
          article_id: articleId,
          depth: currentDepth,
          recorded_at: Date.now(),
          duration_ms: status.durationMillis || recordingDuration * 1000,
          file_uri: uri,
          transcription_status: 'pending',
        };
        addVoiceNote(note);
        setNoteCount(n => n + 1);
      }
    } catch (e) {
      console.warn('[voice] failed to stop recording:', e);
      setIsRecording(false);
    }
  }, [articleId, currentDepth, recordingDuration]);

  if (Platform.OS === 'web') return null;

  return (
    <Pressable
      style={[styles.voiceBtn, isRecording && styles.voiceBtnRecording]}
      onPress={isRecording ? stopRecording : startRecording}
    >
      <Ionicons
        name={isRecording ? 'stop' : 'mic-outline'}
        size={18}
        color={isRecording ? '#ef4444' : '#60a5fa'}
      />
      {isRecording ? (
        <Text style={styles.voiceTimer}>{recordingDuration}s</Text>
      ) : noteCount > 0 ? (
        <Text style={styles.voiceCount}>{noteCount}</Text>
      ) : null}
    </Pressable>
  );
}

// ============================================================
// Main Reader Screen
// ============================================================

export default function ReaderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const article = getArticleById(id || '');

  // --- State ---
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [currentZone, setCurrentZone] = useState<DepthZone>('summary');
  const [claimSignals, setClaimSignals] = useState<ClaimSignalState>({});
  const [activeClaimPill, setActiveClaimPill] = useState<number | null>(null);
  const [signaledClaimCount, setSignaledClaimCount] = useState(0);

  // --- Refs ---
  const scrollRef = useRef<ScrollView>(null);
  const enterTime = useRef(Date.now());

  // Section layout positions for depth zone tracking
  const zonePositions = useRef<Record<DepthZone, number>>({
    summary: 0,
    claims: 0,
    sections: 0,
    full: 0,
  });

  // Implicit tracking refs
  const lastScrollY = useRef(0);
  const lastScrollTime = useRef(Date.now());
  const maxScrollY = useRef(0);
  const currentZoneRef = useRef<DepthZone>('summary');
  const zoneEnterTime = useRef<Record<string, number>>({});
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastVelocityLog = useRef(Date.now());

  // --- Initialize reading state ---
  useEffect(() => {
    if (!article) return;
    const state = getReadingState(article.id);
    if (state.depth === 'unread') {
      updateReadingState(article.id, { depth: 'summary', started_at: Date.now(), last_read_at: Date.now() });
    }
    logEvent('reader_open', { article_id: article.id, title: article.title, previous_depth: state.depth });
    zoneEnterTime.current = { summary: Date.now() };

    return () => {
      const elapsed = Date.now() - enterTime.current;
      const currentState = getReadingState(article.id);
      updateReadingState(article.id, {
        time_spent_ms: (currentState.time_spent_ms || 0) + elapsed,
        last_read_at: Date.now(),
      });
      // Log final zone exit
      const zone = currentZoneRef.current;
      if (zoneEnterTime.current[zone]) {
        const zoneTime = Date.now() - zoneEnterTime.current[zone];
        logEvent('reader_section_exit', { article_id: article.id, section: zone, time_ms: zoneTime });
      }
      logEvent('reader_close', { article_id: article.id, time_spent_ms: elapsed, final_depth: currentZoneRef.current });
      if (pauseTimer.current) clearTimeout(pauseTimer.current);
    };
  }, []);

  // --- Compute which depth zone the user is in based on scroll position ---
  const updateDepthZone = useCallback((scrollY: number) => {
    if (!article) return;
    const positions = zonePositions.current;
    let zone: DepthZone = 'summary';
    // Walk through zones in order; last one whose position we've passed is current
    for (const z of DEPTH_ZONES) {
      if (positions[z] > 0 && scrollY >= positions[z] - 80) {
        zone = z;
      }
    }
    if (zone !== currentZoneRef.current) {
      const prevZone = currentZoneRef.current;
      const now = Date.now();

      // Log exit from previous zone
      if (zoneEnterTime.current[prevZone]) {
        const zoneTime = now - zoneEnterTime.current[prevZone];
        logEvent('reader_section_exit', { article_id: article.id, section: prevZone, time_ms: zoneTime });
      }

      // Log enter new zone
      logEvent('reader_section_enter', { article_id: article.id, section: zone });
      zoneEnterTime.current[zone] = now;

      currentZoneRef.current = zone;
      setCurrentZone(zone);

      // Update reading state depth
      const depthMap: Record<DepthZone, ReadingDepth> = {
        summary: 'summary',
        claims: 'claims',
        sections: 'sections',
        full: 'full',
      };
      const currentDepthIdx = DEPTH_ZONES.indexOf(zone);
      const savedState = getReadingState(article.id);
      const savedDepthIdx = DEPTH_ZONES.indexOf(savedState.depth as DepthZone);
      // Only advance depth, never go backwards
      if (currentDepthIdx > savedDepthIdx || savedState.depth === 'unread') {
        updateReadingState(article.id, { depth: depthMap[zone], last_read_at: now });
      }

      logEvent('reader_scroll_depth', { article_id: article.id, depth: zone, scroll_y: scrollY });
    }
  }, [article]);

  // --- Scroll handler with implicit tracking ---
  const handleScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (!article) return;
    const scrollY = event.nativeEvent.contentOffset.y;
    const now = Date.now();

    // Update depth zone
    updateDepthZone(scrollY);

    // --- Scroll velocity tracking ---
    const dt = now - lastScrollTime.current;
    if (dt > VELOCITY_SAMPLE_INTERVAL_MS && now - lastVelocityLog.current > 1000) {
      const dy = Math.abs(scrollY - lastScrollY.current);
      const velocity = dy / (dt / 1000); // px/sec
      if (velocity > 50) {
        logEvent('reader_scroll_velocity', {
          article_id: article.id,
          velocity: Math.round(velocity),
          direction: scrollY > lastScrollY.current ? 'down' : 'up',
          section: currentZoneRef.current,
        });
        lastVelocityLog.current = now;
      }
    }

    // --- Revisit detection ---
    if (scrollY < lastScrollY.current - REVISIT_SCROLL_BACK_PX && scrollY < maxScrollY.current - REVISIT_SCROLL_BACK_PX) {
      logEvent('reader_revisit', {
        article_id: article.id,
        from_y: Math.round(lastScrollY.current),
        to_y: Math.round(scrollY),
        section: currentZoneRef.current,
      });
    }

    // Track max scroll position
    if (scrollY > maxScrollY.current) {
      maxScrollY.current = scrollY;
    }

    // --- Pause detection ---
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    pauseTimer.current = setTimeout(() => {
      logEvent('reader_pause', {
        article_id: article.id,
        scroll_y: Math.round(scrollY),
        section: currentZoneRef.current,
        pause_duration_ms: PAUSE_THRESHOLD_MS,
      });
    }, PAUSE_THRESHOLD_MS);

    lastScrollY.current = scrollY;
    lastScrollTime.current = now;
  }, [article, updateDepthZone]);

  // --- Zone layout tracking ---
  const onZoneLayout = useCallback((zone: DepthZone) => (event: LayoutChangeEvent) => {
    zonePositions.current[zone] = event.nativeEvent.layout.y;
  }, []);

  // --- Section toggle ---
  const toggleSection = useCallback((index: number) => {
    if (!article) return;
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      logEvent('reader_section_toggle', {
        article_id: article.id,
        section_index: index,
        heading: article.sections[index]?.heading,
        expanded: next.has(index),
      });
      return next;
    });
  }, [article]);

  // --- Claim signals (in claims list) ---
  const handleClaimSignal = useCallback((claimIndex: number, signal: ClaimSignalType) => {
    if (!article) return;
    setClaimSignals(prev => {
      const wasSignaled = prev[claimIndex] !== undefined;
      const next = { ...prev, [claimIndex]: signal };
      if (!wasSignaled) {
        setSignaledClaimCount(c => c + 1);
      }
      return next;
    });
    const mappedSignal = signal === 'interesting' ? 'interesting' : signal === 'save' ? 'save' : 'knew_it';
    addSignal({ article_id: article.id, signal: mappedSignal, timestamp: Date.now(), depth: 'claims' });
    processClaimSignalForConcepts(article.id, article.key_claims[claimIndex] || '', mappedSignal);
    logEvent('reader_claim_signal_inline', {
      article_id: article.id,
      claim_index: claimIndex,
      claim_text: article.key_claims[claimIndex],
      signal,
      context: 'claims_list',
    });
  }, [article]);

  // --- Inline claim tap (in full article text) ---
  const handleInlineClaimTap = useCallback((claimIndex: number) => {
    setActiveClaimPill(claimIndex);
  }, []);

  const handleInlineClaimSignal = useCallback((signal: ClaimSignalType) => {
    if (!article || activeClaimPill === null) return;
    handleClaimSignal(activeClaimPill, signal);
    logEvent('reader_claim_signal_inline', {
      article_id: article.id,
      claim_index: activeClaimPill,
      claim_text: article.key_claims[activeClaimPill],
      signal,
      context: 'full_text_inline',
    });
    setActiveClaimPill(null);
  }, [article, activeClaimPill, handleClaimSignal]);

  // --- Computed values ---
  const totalClaims = article?.key_claims.length || 0;

  // --- Error state ---
  if (!article) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>Article not found</Text>
        <Pressable onPress={() => router.back()}>
          <Text style={styles.backLink}>Back to feed</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color="#f8fafc" />
        </Pressable>
        <View style={{ flex: 1 }} />
        <VoiceRecordButton articleId={article.id} currentDepth={currentZone} />
        <Pressable onPress={() => {
          logEvent('reader_open_source', { article_id: article.id, url: article.source_url });
          Linking.openURL(article.source_url);
        }}>
          <Ionicons name="open-outline" size={20} color="#60a5fa" />
        </Pressable>
      </View>

      {/* Sticky floating depth indicator */}
      <FloatingDepthIndicator currentZone={currentZone} />

      {/* Main scrollable content */}
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        scrollEventThrottle={16}
        onScroll={handleScroll}
      >
        {/* ═══════════ HEADER ZONE ═══════════ */}
        <View onLayout={onZoneLayout('summary')}>
          <Text style={styles.articleTitle}>{article.title}</Text>
          <View style={styles.metaRow}>
            {article.author ? <Text style={styles.metaText}>{article.author}</Text> : null}
            <Text style={styles.metaText}>{article.hostname}</Text>
            {article.date ? <Text style={styles.metaText}>{article.date}</Text> : null}
            <Text style={styles.metaText}>{article.estimated_read_minutes} min · {article.word_count} words</Text>
          </View>

          {/* Time guidance */}
          <View style={styles.timeGuideRow}>
            <View style={styles.timeGuideItem}>
              <Ionicons name="flash-outline" size={12} color="#3b82f6" />
              <Text style={styles.timeGuideText}>30s summary</Text>
            </View>
            <View style={styles.timeGuideItem}>
              <Ionicons name="bulb-outline" size={12} color="#8b5cf6" />
              <Text style={styles.timeGuideText}>2m claims</Text>
            </View>
            {article.sections.length > 1 && (
              <View style={styles.timeGuideItem}>
                <Ionicons name="document-text-outline" size={12} color="#f59e0b" />
                <Text style={styles.timeGuideText}>{Math.ceil(article.estimated_read_minutes / 2)}m sections</Text>
              </View>
            )}
            <View style={styles.timeGuideItem}>
              <Ionicons name="book-outline" size={12} color="#10b981" />
              <Text style={styles.timeGuideText}>{article.estimated_read_minutes}m full</Text>
            </View>
          </View>

          {/* Topics */}
          <View style={styles.topicsRow}>
            {article.topics.map(t => (
              <View key={t} style={styles.topicPill}>
                <Text style={styles.topicText}>{t}</Text>
              </View>
            ))}
          </View>

          {/* Summary */}
          <Text style={styles.fullSummary}>{article.full_summary}</Text>
        </View>

        {/* ═══════════ CLAIMS ZONE ═══════════ */}
        <View onLayout={onZoneLayout('claims')}>
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>Key Claims</Text>
            <View style={styles.dividerLine} />
          </View>

          {/* Claims progress */}
          {totalClaims > 0 && (
            <Text style={styles.claimsProgress}>
              {signaledClaimCount} of {totalClaims} claims reviewed
            </Text>
          )}

          {article.key_claims.map((claim, i) => {
            const signal = claimSignals[i];
            return (
              <View key={i} style={[
                styles.claimCard,
                signal === 'knew_it' && styles.claimCardKnew,
                signal === 'interesting' && styles.claimCardNew,
                signal === 'save' && styles.claimCardSave,
              ]}>
                <Text style={styles.claimCardText}>{claim}</Text>
                <View style={styles.claimActions}>
                  <Pressable
                    style={[styles.claimBtn, signal === 'knew_it' && styles.claimBtnActiveKnew]}
                    onPress={() => handleClaimSignal(i, 'knew_it')}
                  >
                    <Text style={[styles.claimBtnText, signal === 'knew_it' && { color: '#94a3b8' }]}>Knew this</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.claimBtn, styles.claimBtnNewBorder, signal === 'interesting' && styles.claimBtnActiveNew]}
                    onPress={() => handleClaimSignal(i, 'interesting')}
                  >
                    <Text style={[styles.claimBtnText, { color: '#34d399' }, signal === 'interesting' && { color: '#ffffff' }]}>New to me</Text>
                  </Pressable>
                </View>
              </View>
            );
          })}
        </View>

        {/* ═══════════ SECTIONS ZONE ═══════════ */}
        {article.sections.length > 1 && (
          <View onLayout={onZoneLayout('sections')}>
            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>Sections</Text>
              <View style={styles.dividerLine} />
            </View>

            {article.sections.map((section, i) => (
              <SectionCard
                key={i}
                section={section}
                index={i}
                expanded={expandedSections.has(i)}
                onToggle={() => toggleSection(i)}
              />
            ))}
          </View>
        )}

        {/* ═══════════ FULL ARTICLE ZONE ═══════════ */}
        <View onLayout={onZoneLayout('full')}>
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>Full Article</Text>
            <View style={styles.dividerLine} />
          </View>

          <MarkdownText
            content={article.content_markdown}
            claimHighlights={article.key_claims}
            claimSignals={claimSignals}
            onClaimTap={handleInlineClaimTap}
          />
        </View>

        {/* Related articles (connection prompting) */}
        {(() => {
          const related = getRelatedArticles(article.id);
          if (related.length === 0) return null;
          return (
            <View style={styles.relatedSection}>
              <View style={styles.divider}>
                <View style={styles.dividerLine} />
                <Text style={styles.dividerText}>Related Reading</Text>
                <View style={styles.dividerLine} />
              </View>
              {related.map(({ article: rel, sharedConcepts }) => (
                <Pressable
                  key={rel.id}
                  style={styles.relatedCard}
                  onPress={() => {
                    logEvent('reader_related_tap', {
                      from_article: article.id,
                      to_article: rel.id,
                      shared_concepts: sharedConcepts.length,
                    });
                    router.push({ pathname: '/reader', params: { id: rel.id } });
                  }}
                >
                  <Text style={styles.relatedTitle} numberOfLines={2}>{rel.title}</Text>
                  <Text style={styles.relatedConnection} numberOfLines={2}>
                    Connects via: {sharedConcepts.slice(0, 2).join(' · ')}
                  </Text>
                </Pressable>
              ))}
            </View>
          );
        })()}

        {/* Source attribution */}
        {article.sources.length > 0 && article.sources[0].tweet_text && (
          <View style={styles.sourceBox}>
            <Text style={styles.sourceLabel}>
              Found via @{article.sources[0].author_username}
            </Text>
            <Text style={styles.sourceText} numberOfLines={3}>
              {article.sources[0].tweet_text}
            </Text>
          </View>
        )}

        <View style={{ height: 80 }} />
      </ScrollView>

      {/* Floating claim signal pill */}
      {activeClaimPill !== null && (
        <ClaimSignalPill
          currentSignal={claimSignals[activeClaimPill]}
          onSignal={handleInlineClaimSignal}
          onDismiss={() => setActiveClaimPill(null)}
        />
      )}
    </View>
  );
}

// ============================================================
// Styles
// ============================================================

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  topBar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingTop: 56, paddingBottom: 8, gap: 12,
  },
  backButton: { padding: 4 },
  scroll: { flex: 1, paddingHorizontal: 20 },
  errorText: { color: '#ef4444', fontSize: 16, textAlign: 'center', marginTop: 100 },
  backLink: { color: '#60a5fa', fontSize: 14, textAlign: 'center', marginTop: 12 },

  // Floating depth indicator
  depthIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    backgroundColor: '#0f172aee',
  },
  depthIndicatorItem: { flexDirection: 'row', alignItems: 'center' },
  depthDot: { color: '#334155', fontSize: 14, marginHorizontal: 8 },
  depthLabel: { color: '#475569', fontSize: 12, fontWeight: '500' },
  depthLabelActive: { color: '#f8fafc', fontWeight: '700' },
  depthLabelReached: { color: '#94a3b8' },

  // Article header
  articleTitle: {
    color: '#f8fafc', fontSize: 26, fontWeight: '700',
    lineHeight: 34, marginBottom: 10, letterSpacing: -0.3,
  },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  metaText: { color: '#64748b', fontSize: 13 },
  topicsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 20 },
  topicPill: { backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  topicText: { color: '#94a3b8', fontSize: 12 },

  // Summary
  fullSummary: {
    color: '#e2e8f0', fontSize: 17, lineHeight: 28,
    marginBottom: 24, letterSpacing: 0.1,
  },

  // Dividers between zones
  divider: {
    flexDirection: 'row', alignItems: 'center',
    marginTop: 28, marginBottom: 20, gap: 12,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: '#1e293b' },
  dividerText: { color: '#64748b', fontSize: 13, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1 },

  // Claims progress
  claimsProgress: {
    color: '#64748b', fontSize: 12, marginBottom: 12,
    textAlign: 'center',
  },

  // Claims list
  claimCard: {
    backgroundColor: '#1e293b', borderRadius: 12, padding: 16,
    marginBottom: 10, borderLeftWidth: 3, borderLeftColor: '#334155',
  },
  claimCardKnew: { borderLeftColor: '#64748b', opacity: 0.7 },
  claimCardNew: { borderLeftColor: '#34d399' },
  claimCardSave: { borderLeftColor: '#60a5fa' },
  claimCardText: { color: '#e2e8f0', fontSize: 15, lineHeight: 23, marginBottom: 10 },
  claimActions: { flexDirection: 'row', gap: 8 },
  claimBtn: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 8, backgroundColor: '#334155',
  },
  claimBtnNewBorder: { borderColor: '#34d399', borderWidth: 1, backgroundColor: 'transparent' },
  claimBtnActiveKnew: { backgroundColor: '#475569' },
  claimBtnActiveNew: { backgroundColor: '#065f46', borderColor: '#34d399' },
  claimBtnText: { color: '#94a3b8', fontSize: 12, fontWeight: '500' },

  // Section cards
  sectionCard: { backgroundColor: '#1e293b', borderRadius: 12, marginBottom: 10, overflow: 'hidden' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 8 },
  sectionHeading: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  sectionSummary: { color: '#94a3b8', fontSize: 13, lineHeight: 18, marginTop: 4 },
  sectionContent: { paddingHorizontal: 16, paddingBottom: 16 },
  sectionClaims: { marginBottom: 12, paddingLeft: 4 },
  claimRow: { flexDirection: 'row', marginBottom: 6 },
  claimArrow: { color: '#60a5fa', marginRight: 8, fontSize: 13 },
  claimRowText: { color: '#94a3b8', fontSize: 13, lineHeight: 19, flex: 1 },

  // Markdown rendering
  markdownHeading: {
    color: '#f8fafc', fontWeight: '700',
    marginTop: 20, marginBottom: 10, lineHeight: 28,
  },
  markdownText: {
    color: '#cbd5e1', fontSize: 16, lineHeight: 26,
    marginBottom: 14, letterSpacing: 0.15,
  },
  markdownList: { marginBottom: 14 },
  markdownListItem: { flexDirection: 'row', marginBottom: 6, paddingRight: 8 },
  markdownBullet: { color: '#60a5fa', marginRight: 10, fontSize: 16 },
  codeBlock: { backgroundColor: '#1e293b', borderRadius: 8, padding: 14, marginBottom: 14 },
  codeText: { color: '#94a3b8', fontSize: 13, fontFamily: 'monospace' },

  // Inline claim highlights in full text
  claimHighlightUnsignaled: {
    backgroundColor: '#1e3a5f20', borderRadius: 4,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: '#3b82f680',
  },
  claimHighlightKnew: {
    backgroundColor: '#47556920', borderRadius: 4,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: '#64748b',
  },
  claimHighlightNew: {
    backgroundColor: '#065f4620', borderRadius: 4,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: '#34d399',
  },
  claimHighlightSave: {
    backgroundColor: '#1e40af20', borderRadius: 4,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: '#60a5fa',
  },

  // Floating signal pill
  pillBackdrop: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: '#00000060', justifyContent: 'center', alignItems: 'center',
  },
  pillContainer: {
    flexDirection: 'row', backgroundColor: '#1e293b',
    borderRadius: 16, padding: 6, gap: 4,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 12, elevation: 8,
  },
  pillBtn: {
    paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: 12, backgroundColor: '#334155',
  },
  pillBtnNew: { backgroundColor: '#065f46' },
  pillBtnSave: { backgroundColor: '#1e3a5f' },
  pillBtnText: { color: '#e2e8f0', fontSize: 13, fontWeight: '600' },

  // Source attribution
  sourceBox: {
    backgroundColor: '#1e293b', borderRadius: 12, padding: 16,
    marginTop: 24, borderLeftWidth: 3, borderLeftColor: '#334155',
  },
  sourceLabel: { color: '#60a5fa', fontSize: 12, marginBottom: 6 },
  sourceText: { color: '#64748b', fontSize: 13, lineHeight: 19 },

  // Time guidance
  timeGuideRow: {
    flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12,
    paddingVertical: 8, paddingHorizontal: 12,
    backgroundColor: '#1e293b', borderRadius: 8,
  },
  timeGuideItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  timeGuideText: { color: '#94a3b8', fontSize: 12 },

  // Related articles
  relatedSection: { marginTop: 16 },
  relatedCard: {
    backgroundColor: '#1e293b', borderRadius: 12, padding: 14,
    marginBottom: 8, borderLeftWidth: 3, borderLeftColor: '#8b5cf6',
  },
  relatedTitle: { color: '#f8fafc', fontSize: 14, fontWeight: '600', marginBottom: 4 },
  relatedConnection: { color: '#a78bfa', fontSize: 12, lineHeight: 16 },

  // Voice recording
  voiceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 16, backgroundColor: '#1e293b', marginRight: 10,
  },
  voiceBtnRecording: { backgroundColor: '#7f1d1d' },
  voiceTimer: { color: '#ef4444', fontSize: 12, fontWeight: '700' },
  voiceCount: { color: '#64748b', fontSize: 11 },
});
