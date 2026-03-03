import { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking,
  NativeSyntheticEvent, NativeScrollEvent, LayoutChangeEvent,
  Platform, Animated,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { getArticleById, getReadingState, updateReadingState, addSignal, processClaimSignalForConcepts, processImplicitEncounter, getRelatedArticles, getConceptConnections, addVoiceNote, getVoiceNotes, getHighlightBlockIndices, addHighlight, removeHighlight } from '../data/store';
import { ReadingDepth, VoiceNote, Highlight } from '../data/types';
import * as Haptics from 'expo-haptics';
import { logEvent } from '../data/logger';
import { isSectionValid, parseInlineMarkdown, splitMarkdownBlocks, parseMarkdownBlock } from './markdown-utils';
import { transcribeVoiceNote } from '../data/transcription';
import { triggerResearch, getResearchResultsForArticle } from '../data/research';

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
const IMPLICIT_ENCOUNTER_DWELL_MS = 60000; // 60s in a zone triggers implicit encounter
const SCROLL_POSITION_SAVE_INTERVAL_MS = 2000;

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

// --- Connection indicator pill (shown below claims) ---

function ConnectionIndicator({ articleId, claimText }: {
  articleId: string;
  claimText: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const connection = getConceptConnections(articleId, claimText);
  if (!connection) return null;

  const { concept, otherArticles } = connection;
  const count = otherArticles.length;

  useEffect(() => {
    logEvent('reader_connection_shown', {
      article_id: articleId,
      concept_id: concept.id,
      other_article_count: count,
    });
  }, []);

  return (
    <Pressable
      style={styles.connectionPill}
      onPress={() => {
        setExpanded(e => !e);
        if (!expanded) {
          logEvent('reader_connection_tap', {
            article_id: articleId,
            concept_id: concept.id,
          });
        }
      }}
    >
      <Text style={styles.connectionText}>
        {concept.topic} · seen in {count} other {count === 1 ? 'article' : 'articles'}
      </Text>
      {expanded && (
        <View style={styles.connectionExpanded}>
          {otherArticles.map(a => (
            <Text key={a.id} style={styles.connectionArticleTitle} numberOfLines={1}>
              {a.title}
            </Text>
          ))}
        </View>
      )}
    </Pressable>
  );
}

// --- Inline markdown rendering (converts parsed segments to React elements) ---

function renderInlineMarkdown(text: string): (string | React.ReactElement)[] {
  const segments = parseInlineMarkdown(text);
  return segments.map((seg, i) => {
    switch (seg.type) {
      case 'link':
        return (
          <Text
            key={`link-${i}`}
            style={styles.markdownLink}
            onPress={() => Linking.openURL(seg.url)}
          >
            {seg.text}
          </Text>
        );
      case 'bold':
        return (
          <Text key={`bold-${i}`} style={styles.markdownBold}>
            {seg.text}
          </Text>
        );
      case 'italic':
        return (
          <Text key={`italic-${i}`} style={styles.markdownItalic}>
            {seg.text}
          </Text>
        );
      case 'code':
        return (
          <Text key={`code-${i}`} style={styles.markdownInlineCode}>
            {seg.text}
          </Text>
        );
      default:
        return seg.text;
    }
  });
}

// --- Simple markdown renderer ---

// Re-export for tests
export { isSectionValid } from './markdown-utils';

function MarkdownText({ content, claimHighlights, claimSignals, onClaimTap, highlightedBlocks, onBlockLongPress }: {
  content: string;
  claimHighlights?: string[];
  claimSignals?: ClaimSignalState;
  onClaimTap?: (claimIndex: number) => void;
  highlightedBlocks?: Set<number>;
  onBlockLongPress?: (blockIndex: number, text: string) => void;
}) {
  if (!content) return null;

  const blocks = splitMarkdownBlocks(content);

  return (
    <View>
      {blocks.map((raw, i) => {
        const block = parseMarkdownBlock(raw);
        const isHighlighted = highlightedBlocks?.has(i);

        switch (block.type) {
          case 'heading':
            return (
              <Text key={i} style={[
                styles.markdownHeading,
                block.level === 1 && { fontSize: 22 },
                block.level === 2 && { fontSize: 19 },
                (block.level ?? 3) >= 3 && { fontSize: 17 },
              ]}>
                {renderInlineMarkdown(block.content)}
              </Text>
            );

          case 'hr':
            return <View key={i} style={styles.markdownHr} />;

          case 'ul':
            return (
              <View key={i} style={[styles.markdownList, isHighlighted && styles.paragraphHighlight]}>
                {onBlockLongPress && (
                  <Pressable
                    style={StyleSheet.absoluteFill}
                    onLongPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); }}
                  />
                )}
                {(block.items || []).map((item, j) => (
                  <View key={j} style={styles.markdownListItem}>
                    <Text style={styles.markdownBullet}>{'\u00B7'}</Text>
                    <Text style={styles.markdownText}>
                      {renderInlineMarkdown(item)}
                    </Text>
                  </View>
                ))}
              </View>
            );

          case 'ol':
            return (
              <View key={i} style={[styles.markdownList, isHighlighted && styles.paragraphHighlight]}>
                {onBlockLongPress && (
                  <Pressable
                    style={StyleSheet.absoluteFill}
                    onLongPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); }}
                  />
                )}
                {(block.items || []).map((item, j) => (
                  <View key={j} style={styles.markdownListItem}>
                    <Text style={styles.markdownOrderedBullet}>{j + 1}.</Text>
                    <Text style={styles.markdownText}>
                      {renderInlineMarkdown(item)}
                    </Text>
                  </View>
                ))}
              </View>
            );

          case 'code':
            return (
              <View key={i} style={[styles.codeBlock, isHighlighted && styles.paragraphHighlight]}>
                <Text style={styles.codeText}>{block.content}</Text>
              </View>
            );

          case 'blockquote':
            return (
              <Pressable
                key={i}
                onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
                style={[styles.markdownBlockquote, isHighlighted && styles.paragraphHighlight]}
              >
                <Text style={styles.markdownBlockquoteText}>
                  {renderInlineMarkdown(block.content)}
                </Text>
              </Pressable>
            );

          default: {
            // Regular paragraph — check for claim highlighting
            if (claimHighlights && claimHighlights.length > 0) {
              const matchedClaimIndex = findMatchingClaim(block.content, claimHighlights);
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
                    onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, block.content); } : undefined}
                    style={isHighlighted ? styles.paragraphHighlight : undefined}
                  >
                    <Text style={[styles.markdownText, highlightStyle]}>
                      {renderInlineMarkdown(block.content)}
                    </Text>
                  </Pressable>
                );
              }
            }

            return (
              <Pressable
                key={i}
                onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, block.content); } : undefined}
                style={isHighlighted ? styles.paragraphHighlight : undefined}
              >
                <Text style={styles.markdownText}>
                  {renderInlineMarkdown(block.content)}
                </Text>
              </Pressable>
            );
          }
        }
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

function VoiceRecordButton({ articleId, currentDepth, onTranscribed }: {
  articleId: string;
  currentDepth: ReadingDepth;
  onTranscribed?: (transcript: string, noteId: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
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

        // Auto-trigger transcription in background
        setTranscribing(true);
        transcribeVoiceNote(note).then((transcript) => {
          setTranscribing(false);
          if (transcript && onTranscribed) {
            onTranscribed(transcript, noteId);
          }
        }).catch(() => setTranscribing(false));
      }
    } catch (e) {
      console.warn('[voice] failed to stop recording:', e);
      setIsRecording(false);
    }
  }, [articleId, currentDepth, recordingDuration, onTranscribed]);

  if (Platform.OS === 'web') return null;

  return (
    <Pressable
      style={[styles.voiceBtn, isRecording && styles.voiceBtnRecording]}
      onPress={isRecording ? stopRecording : startRecording}
    >
      <Ionicons
        name={isRecording ? 'stop' : transcribing ? 'hourglass-outline' : 'mic-outline'}
        size={18}
        color={isRecording ? '#ef4444' : transcribing ? '#f59e0b' : '#60a5fa'}
      />
      {isRecording ? (
        <Text style={styles.voiceTimer}>{recordingDuration}s</Text>
      ) : noteCount > 0 ? (
        <Text style={styles.voiceCount}>{noteCount}</Text>
      ) : null}
    </Pressable>
  );
}

// --- Research trigger banner (shows after voice note transcription) ---

function ResearchBanner({ transcript, articleId, articleTitle, articleSummary, concepts, voiceNoteId, onDismiss }: {
  transcript: string;
  articleId: string;
  articleTitle: string;
  articleSummary: string;
  concepts: string[];
  voiceNoteId: string;
  onDismiss: () => void;
}) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleResearch = useCallback(async () => {
    setSending(true);
    await triggerResearch({
      query: transcript,
      articleId,
      articleTitle,
      articleSummary,
      concepts,
      voiceNoteId,
    });
    setSending(false);
    setSent(true);
    logEvent('research_triggered', {
      article_id: articleId,
      voice_note_id: voiceNoteId,
      query_length: transcript.length,
    });
    setTimeout(onDismiss, 2000);
  }, [transcript, articleId, articleTitle, articleSummary, concepts, voiceNoteId, onDismiss]);

  if (sent) {
    return (
      <View style={styles.researchBanner}>
        <Ionicons name="checkmark-circle" size={16} color="#10b981" />
        <Text style={styles.researchBannerText}>Research agent dispatched</Text>
      </View>
    );
  }

  return (
    <View style={styles.researchBanner}>
      <Text style={styles.researchTranscript} numberOfLines={2}>{transcript}</Text>
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
        <Pressable
          style={[styles.researchBtn, sending && { opacity: 0.5 }]}
          onPress={handleResearch}
          disabled={sending}
        >
          <Ionicons name="search" size={14} color="#f8fafc" />
          <Text style={styles.researchBtnText}>
            {sending ? 'Sending...' : 'Research this?'}
          </Text>
        </Pressable>
        <Pressable style={styles.researchDismissBtn} onPress={onDismiss}>
          <Ionicons name="close" size={14} color="#64748b" />
        </Pressable>
      </View>
    </View>
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
  const [researchBanner, setResearchBanner] = useState<{ transcript: string; noteId: string } | null>(null);
  const [highlightedBlocks, setHighlightedBlocks] = useState<Set<number>>(new Set());
  const [articleResearchCount, setArticleResearchCount] = useState(0);
  const [showRestoredIndicator, setShowRestoredIndicator] = useState(false);
  const restoredIndicatorOpacity = useRef(new Animated.Value(1)).current;

  // --- Refs ---
  const scrollRef = useRef<ScrollView>(null);
  const enterTime = useRef(Date.now());
  const lastPositionSaveTime = useRef(0);

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
  const implicitEncounterFired = useRef(false);

  // --- Initialize reading state ---
  useEffect(() => {
    if (!article) return;
    const state = getReadingState(article.id);
    if (state.depth === 'unread') {
      updateReadingState(article.id, { depth: 'summary', started_at: Date.now(), last_read_at: Date.now() });
    }
    logEvent('reader_open', { article_id: article.id, title: article.title, previous_depth: state.depth });
    zoneEnterTime.current = { summary: Date.now() };

    // Restore scroll position if saved
    const savedY = state.scroll_position_y || 0;
    if (savedY > 0) {
      setTimeout(() => {
        scrollRef.current?.scrollTo({ y: savedY, animated: false });
        logEvent('reader_position_restored', { article_id: article.id, scroll_y: savedY });
        setShowRestoredIndicator(true);
        setTimeout(() => {
          Animated.timing(restoredIndicatorOpacity, {
            toValue: 0,
            duration: 500,
            useNativeDriver: true,
          }).start(() => setShowRestoredIndicator(false));
        }, 2000);
      }, 300);
    }

    return () => {
      const elapsed = Date.now() - enterTime.current;
      const currentState = getReadingState(article.id);
      updateReadingState(article.id, {
        time_spent_ms: (currentState.time_spent_ms || 0) + elapsed,
        last_read_at: Date.now(),
        scroll_position_y: lastScrollY.current,
      });
      // Log final zone exit and check implicit encounter
      const zone = currentZoneRef.current;
      if (zoneEnterTime.current[zone]) {
        const zoneTime = Date.now() - zoneEnterTime.current[zone];
        logEvent('reader_section_exit', { article_id: article.id, section: zone, time_ms: zoneTime });

        if (!implicitEncounterFired.current && zone !== 'summary' && zoneTime >= IMPLICIT_ENCOUNTER_DWELL_MS) {
          implicitEncounterFired.current = true;
          const updatedConcepts = processImplicitEncounter(article.id);
          if (updatedConcepts.length > 0) {
            logEvent('implicit_concept_encounter', {
              article_id: article.id,
              trigger_zone: zone,
              dwell_ms: zoneTime,
              concepts_updated: updatedConcepts.length,
              concept_ids: updatedConcepts,
            });
          }
        }
      }
      logEvent('reader_close', { article_id: article.id, time_spent_ms: elapsed, final_depth: currentZoneRef.current });
      if (pauseTimer.current) clearTimeout(pauseTimer.current);
    };
  }, []);

  // --- Fire implicit concept encounter if dwell threshold met ---
  const checkImplicitEncounter = useCallback((zone: DepthZone, dwellMs: number) => {
    if (!article || implicitEncounterFired.current) return;
    // Only fire for claims/sections/full zones with meaningful dwell time
    if (zone === 'summary') return;
    if (dwellMs < IMPLICIT_ENCOUNTER_DWELL_MS) return;

    implicitEncounterFired.current = true;
    const updatedConcepts = processImplicitEncounter(article.id);
    if (updatedConcepts.length > 0) {
      logEvent('implicit_concept_encounter', {
        article_id: article.id,
        trigger_zone: zone,
        dwell_ms: dwellMs,
        concepts_updated: updatedConcepts.length,
        concept_ids: updatedConcepts,
      });
    }
  }, [article]);

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
        checkImplicitEncounter(prevZone, zoneTime);
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
        const depthUpdate: Partial<{ depth: ReadingDepth; last_read_at: number; scroll_position_y: number }> = {
          depth: depthMap[zone],
          last_read_at: now,
        };
        if (zone === 'full') {
          depthUpdate.scroll_position_y = 0;
        }
        updateReadingState(article.id, depthUpdate);
      }

      logEvent('reader_scroll_depth', { article_id: article.id, depth: zone, scroll_y: scrollY });
    }
  }, [article, checkImplicitEncounter]);

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

    // --- Throttled scroll position save ---
    if (now - lastPositionSaveTime.current >= SCROLL_POSITION_SAVE_INTERVAL_MS) {
      lastPositionSaveTime.current = now;
      updateReadingState(article.id, { scroll_position_y: Math.round(scrollY) });
    }

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

  // --- Highlight handler ---
  const [highlightAction, setHighlightAction] = useState<{ blockIndex: number; text: string } | null>(null);

  const handleBlockLongPress = useCallback((blockIndex: number, text: string) => {
    if (!article) return;
    const indices = getHighlightBlockIndices(article.id);
    if (indices.has(blockIndex)) {
      removeHighlight(article.id, blockIndex);
      setHighlightedBlocks(prev => {
        const next = new Set(prev);
        next.delete(blockIndex);
        return next;
      });
    } else {
      addHighlight({
        id: `hl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        article_id: article.id,
        block_index: blockIndex,
        text: text.slice(0, 500),
        highlighted_at: Date.now(),
        zone: currentZone,
      });
      setHighlightedBlocks(prev => new Set(prev).add(blockIndex));
      setHighlightAction({ blockIndex, text: text.slice(0, 500) });
      setTimeout(() => setHighlightAction(null), 4000);
    }
  }, [article, currentZone]);

  const handleResearchHighlight = useCallback(async () => {
    if (!article || !highlightAction) return;
    await triggerResearch({
      query: highlightAction.text,
      articleId: article.id,
      articleTitle: article.title,
      articleSummary: article.full_summary,
      concepts: article.topics,
    });
    logEvent('research_triggered_from_highlight', {
      article_id: article.id,
      block_index: highlightAction.blockIndex,
      text_preview: highlightAction.text.slice(0, 80),
    });
    setHighlightAction(null);
  }, [article, highlightAction]);

  // --- Initialize highlights + research results from store ---
  useEffect(() => {
    if (!article) return;
    setHighlightedBlocks(getHighlightBlockIndices(article.id));
    getResearchResultsForArticle(article.id).then(results => {
      const completed = results.filter(r => r.status === 'completed').length;
      setArticleResearchCount(completed);
    });
  }, [article?.id]);

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
        <VoiceRecordButton
          articleId={article.id}
          currentDepth={currentZone}
          onTranscribed={(transcript, noteId) => setResearchBanner({ transcript, noteId })}
        />
        {articleResearchCount > 0 && (
          <Pressable
            style={styles.researchBadge}
            onPress={() => {
              logEvent('reader_research_badge_tap', { article_id: article.id, count: articleResearchCount });
              router.push('/stats');
            }}
          >
            <Ionicons name="flask" size={14} color="#a78bfa" />
            <Text style={styles.researchBadgeText}>{articleResearchCount}</Text>
          </Pressable>
        )}
        <Pressable onPress={() => {
          logEvent('reader_open_source', { article_id: article.id, url: article.source_url });
          Linking.openURL(article.source_url);
        }}>
          <Ionicons name="open-outline" size={20} color="#60a5fa" />
        </Pressable>
      </View>

      {/* Sticky floating depth indicator */}
      <FloatingDepthIndicator currentZone={currentZone} />

      {/* Research trigger banner after voice note transcription */}
      {researchBanner && article && (
        <ResearchBanner
          transcript={researchBanner.transcript}
          articleId={article.id}
          articleTitle={article.title}
          articleSummary={article.full_summary}
          concepts={article.topics}
          voiceNoteId={researchBanner.noteId}
          onDismiss={() => setResearchBanner(null)}
        />
      )}

      {/* Position restored indicator */}
      {showRestoredIndicator && (
        <Animated.View style={[styles.restoredIndicator, { opacity: restoredIndicatorOpacity }]}>
          <Text style={styles.restoredText}>Continuing where you left off</Text>
        </Animated.View>
      )}

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

          {/* Dedup banner */}
          {article.similar_articles && article.similar_articles.length > 0 && (() => {
            const readSimilar = article.similar_articles!.filter(sa => {
              const state = getReadingState(sa.id);
              return state.depth !== 'unread';
            });
            if (readSimilar.length === 0) return null;
            return (
              <Pressable
                style={styles.dedupBanner}
                onPress={() => {
                  logEvent('dedup_banner_tap', { article_id: article.id, similar_id: readSimilar[0].id });
                  router.push({ pathname: '/reader', params: { id: readSimilar[0].id } });
                }}
              >
                <Ionicons name="copy-outline" size={14} color="#f59e0b" />
                <Text style={styles.dedupBannerText}>
                  Similar to: {readSimilar[0].title}
                </Text>
              </Pressable>
            );
          })()}
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
              <View key={i}>
                <View style={[
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
                <ConnectionIndicator articleId={article.id} claimText={claim} />
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

            {article.sections.filter(isSectionValid).map((section, i) => (
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
            highlightedBlocks={highlightedBlocks}
            onBlockLongPress={handleBlockLongPress}
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

      {/* Highlight action bar */}
      {highlightAction && (
        <View style={styles.highlightActionBar}>
          <Ionicons name="checkmark-circle" size={16} color="#f59e0b" />
          <Text style={styles.highlightActionText}>Highlighted</Text>
          <Pressable style={styles.highlightResearchBtn} onPress={handleResearchHighlight}>
            <Ionicons name="search" size={14} color="#a78bfa" />
            <Text style={styles.highlightResearchText}>Research this</Text>
          </Pressable>
          <Pressable onPress={() => setHighlightAction(null)}>
            <Ionicons name="close" size={16} color="#64748b" />
          </Pressable>
        </View>
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
  markdownOrderedBullet: { color: '#60a5fa', marginRight: 10, fontSize: 14, minWidth: 20 },
  codeBlock: { backgroundColor: '#1e293b', borderRadius: 8, padding: 14, marginBottom: 14 },
  codeText: { color: '#94a3b8', fontSize: 13, fontFamily: 'monospace' },
  markdownLink: { color: '#60a5fa', textDecorationLine: 'underline' as const },
  markdownBold: { color: '#f8fafc', fontWeight: '700' as const },
  markdownItalic: { color: '#cbd5e1', fontStyle: 'italic' as const },
  markdownInlineCode: { color: '#94a3b8', fontFamily: 'monospace', backgroundColor: '#1e293b', paddingHorizontal: 4 },
  markdownBlockquote: {
    borderLeftWidth: 3, borderLeftColor: '#475569',
    paddingLeft: 14, marginBottom: 14, marginLeft: 4,
  },
  markdownBlockquoteText: {
    color: '#94a3b8', fontSize: 15, lineHeight: 24, fontStyle: 'italic' as const,
  },
  markdownHr: { height: 1, backgroundColor: '#334155', marginVertical: 20 },

  // Dedup banner
  dedupBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#78350f30',
    borderLeftWidth: 3,
    borderLeftColor: '#f59e0b',
    padding: 12,
    borderRadius: 8,
    marginTop: 12,
  },
  dedupBannerText: {
    color: '#fbbf24',
    fontSize: 13,
    flex: 1,
  },

  // Paragraph highlighting (long-press)
  paragraphHighlight: {
    backgroundColor: '#78350f20',
    borderLeftWidth: 3,
    borderLeftColor: '#f59e0b',
    paddingLeft: 8,
    borderRadius: 4,
    marginLeft: -8,
  },

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

  // Connection indicators
  connectionPill: {
    marginTop: -4,
    marginBottom: 10,
    marginLeft: 12,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: '#1e1b2e',
    borderRadius: 8,
    alignSelf: 'flex-start',
    borderLeftWidth: 2,
    borderLeftColor: '#7c3aed40',
  },
  connectionText: {
    color: '#8b7fb8',
    fontSize: 11,
    fontWeight: '500' as const,
  },
  connectionExpanded: {
    marginTop: 4,
    paddingTop: 4,
    borderTopWidth: 1,
    borderTopColor: '#2d2640',
  },
  connectionArticleTitle: {
    color: '#a78bfa',
    fontSize: 11,
    lineHeight: 16,
    marginBottom: 2,
  },

  // Voice recording
  voiceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 16, backgroundColor: '#1e293b', marginRight: 10,
  },
  voiceBtnRecording: { backgroundColor: '#7f1d1d' },
  voiceTimer: { color: '#ef4444', fontSize: 12, fontWeight: '700' },
  voiceCount: { color: '#64748b', fontSize: 11 },

  // Restored position indicator
  restoredIndicator: {
    alignItems: 'center',
    paddingVertical: 6,
    backgroundColor: '#1e293b',
  },
  restoredText: {
    color: '#94a3b8',
    fontSize: 12,
  },

  // Research banner
  researchBanner: {
    backgroundColor: '#1a1a2e',
    borderLeftWidth: 3,
    borderLeftColor: '#8b5cf6',
    marginHorizontal: 16,
    marginVertical: 8,
    padding: 12,
    borderRadius: 10,
  },
  researchTranscript: {
    color: '#cbd5e1',
    fontSize: 13,
    lineHeight: 19,
    fontStyle: 'italic' as const,
  },
  researchBtn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    backgroundColor: '#7c3aed',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  researchBtnText: {
    color: '#f8fafc',
    fontSize: 13,
    fontWeight: '600' as const,
  },
  researchDismissBtn: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#1e293b',
  },
  researchBannerText: {
    color: '#10b981',
    fontSize: 13,
    fontWeight: '500' as const,
  },

  // Highlight action bar
  highlightActionBar: {
    position: 'absolute',
    bottom: 24,
    left: 16,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  highlightActionText: {
    color: '#f59e0b',
    fontSize: 13,
    fontWeight: '600' as const,
    flex: 1,
  },
  highlightResearchBtn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    backgroundColor: '#1a1a2e',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  highlightResearchText: {
    color: '#a78bfa',
    fontSize: 12,
    fontWeight: '500' as const,
  },

  // Research results badge in top bar
  researchBadge: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    backgroundColor: '#1a1a2e',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    marginRight: 4,
  },
  researchBadgeText: {
    color: '#a78bfa',
    fontSize: 11,
    fontWeight: '600' as const,
  },
});
