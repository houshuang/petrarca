import { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking, TextInput,
  NativeSyntheticEvent, NativeScrollEvent, LayoutChangeEvent,
  Platform, Animated, Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { getArticleById, getReadingState, updateReadingState, addSignal, processClaimSignalForConcepts, processImplicitEncounter, processTranscriptForConcepts, getRelatedArticles, getConceptConnections, addVoiceNote, getVoiceNotes, getHighlightBlockIndices, addHighlight, removeHighlight, updateHighlightNote, dismissArticle, getConceptsForArticleWithState, updateConceptState, getConceptState, getConcepts } from '../data/store';
import { ReadingDepth, VoiceNote, Highlight, Concept, ConceptKnowledgeLevel } from '../data/types';
import * as Haptics from 'expo-haptics';
import { logEvent } from '../data/logger';
import { isSectionValid, parseInlineMarkdown, splitMarkdownBlocks, parseMarkdownBlock } from '../lib/markdown-utils';
import { transcribeVoiceNote } from '../data/transcription';
import { triggerResearch, getResearchResultsForArticle } from '../data/research';
import { getDisplayTitle } from '../lib/display-utils';
import { useIsDesktopWeb } from '../lib/use-responsive';
import { colors, fonts, type, spacing, layout } from '../design/tokens';

// --- Local types for claim signal tracking ---

type ClaimSignalType = 'knew_it' | 'interesting' | 'save';

interface ClaimSignalState {
  [claimIndex: number]: ClaimSignalType;
}

// --- Depth zone definitions ---

const DEPTH_ZONES = ['summary', 'concepts', 'sections', 'full'] as const;
type DepthZone = typeof DEPTH_ZONES[number];

const DEPTH_LABELS: Record<DepthZone, string> = {
  summary: 'Summary',
  concepts: 'Concepts',
  sections: 'Sections',
  full: 'Full Article',
};

// --- Implicit tracking constants ---

const PAUSE_THRESHOLD_MS = 3000;
const VELOCITY_SAMPLE_INTERVAL_MS = 200;
const REVISIT_SCROLL_BACK_PX = 150;
const IMPLICIT_ENCOUNTER_DWELL_MS = 60000; // 60s in a zone triggers implicit encounter
const SCROLL_POSITION_SAVE_INTERVAL_MS = 2000;

// --- Helpers ---

function stripLeadingTitle(text: string, title: string): string {
  if (!text) return '';
  const lines = text.split('\n');
  const firstLine = lines[0].replace(/^#+\s*/, '').trim();
  if (firstLine === title.trim()) {
    return lines.slice(1).join('\n').trimStart();
  }
  return text;
}

// --- Floating Depth Indicator ---

function FloatingDepthIndicator({ currentZone, conceptCount, sectionCount }: {
  currentZone: DepthZone;
  conceptCount: number;
  sectionCount: number;
}) {
  const zoneCounts: Partial<Record<DepthZone, number>> = {};
  if (conceptCount > 0) zoneCounts.concepts = conceptCount;
  if (sectionCount > 0) zoneCounts.sections = sectionCount;

  return (
    <View style={styles.depthIndicator}>
      {DEPTH_ZONES.map((zone, i) => {
        const active = zone === currentZone;
        const count = zoneCounts[zone];
        return (
          <View key={zone} style={styles.depthIndicatorItem}>
            <Text style={[
              styles.depthLabel,
              active && styles.depthLabelActive,
            ]}>
              {DEPTH_LABELS[zone]}
              {count != null && (
                <Text style={styles.depthCount}> ({count})</Text>
              )}
            </Text>
            {active && <View style={styles.depthUnderline} />}
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
          <Text style={{ color: colors.textMuted, fontFamily: fonts.ui, fontSize: 11, marginBottom: 4 }}>
            Already marked · tap to change
          </Text>
        )}
        <View style={{ flexDirection: 'row', gap: 4 }}>
          <Pressable style={[styles.pillBtn, currentSignal === 'knew_it' && { backgroundColor: colors.rule }]} onPress={() => onSignal('knew_it')}>
            <Text style={styles.pillBtnText}>{currentSignal === 'knew_it' ? '✓ ' : ''}Knew this</Text>
          </Pressable>
          <Pressable style={[styles.pillBtn, styles.pillBtnNew, currentSignal === 'interesting' && { backgroundColor: '#d4edda' }]} onPress={() => onSignal('interesting')}>
            <Text style={[styles.pillBtnText, { color: colors.claimNew }]}>{currentSignal === 'interesting' ? '✓ ' : ''}New to me</Text>
          </Pressable>
          <Pressable style={[styles.pillBtn, styles.pillBtnSave, currentSignal === 'save' && { backgroundColor: '#f5e6d0' }]} onPress={() => onSignal('save')}>
            <Text style={[styles.pillBtnText, { color: colors.rubric }]}>{currentSignal === 'save' ? '✓ ' : ''}Save</Text>
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

// --- Connection callout card (shown below claims) ---

function ConnectionIndicator({ articleId, claimText }: {
  articleId: string;
  claimText: string;
}) {
  const router = useRouter();
  const connection = getConceptConnections(articleId, claimText);

  useEffect(() => {
    if (!connection) return;
    logEvent('reader_connection_shown', {
      article_id: articleId,
      concept_id: connection.concept.id,
      other_article_count: connection.otherArticles.length,
    });
  }, [articleId, claimText]);

  if (!connection) return null;

  const { concept, otherArticles } = connection;
  const count = otherArticles.length;
  const displayArticles = otherArticles.slice(0, 3);

  return (
    <View style={styles.connectionCard}>
      <View style={styles.connectionHeader}>
        <Text style={styles.connectionLabel}>Also explored in:</Text>
      </View>
      {displayArticles.map(a => (
        <Pressable
          key={a.id}
          style={styles.connectionArticleRow}
          onPress={() => {
            logEvent('reader_connection_tap', {
              article_id: articleId,
              concept_id: concept.id,
              target_article: a.id,
            });
            router.push({ pathname: '/reader', params: { id: a.id } });
          }}
        >
          <Text style={styles.connectionArticleTitle} numberOfLines={1}>{a.title}</Text>
          <Ionicons name="chevron-forward" size={12} color={colors.textMuted} />
        </Pressable>
      ))}
      {count > 3 && (
        <Text style={styles.connectionMore}>+{count - 3} more</Text>
      )}
    </View>
  );
}

// --- Concept detail sheet (bottom sheet overlay) ---

function ConceptSheet({ concept, currentState, currentArticleId, onClose, onStateChange, onConceptTap }: {
  concept: Concept;
  currentState: ConceptKnowledgeLevel;
  currentArticleId: string;
  onClose: () => void;
  onStateChange: (level: ConceptKnowledgeLevel) => void;
  onConceptTap: (concept: Concept, state: ConceptKnowledgeLevel) => void;
}) {
  const router = useRouter();
  const allConcepts = getConcepts();

  const otherArticles = concept.source_article_ids
    .filter(id => id !== currentArticleId)
    .map(id => getArticleById(id))
    .filter(Boolean);

  const relatedConcepts = (concept.related_concepts || [])
    .map(id => allConcepts.find(c => c.id === id))
    .filter(Boolean)
    .slice(0, 6);

  const stateOptions: { level: ConceptKnowledgeLevel; label: string }[] = [
    { level: 'unknown', label: 'Unknown' },
    { level: 'encountered', label: 'Learning' },
    { level: 'known', label: 'Know this' },
  ];

  return (
    <Pressable style={styles.conceptSheetBackdrop} onPress={onClose}>
      <Pressable style={styles.conceptSheetContainer} onPress={e => e.stopPropagation()}>
        <View style={styles.conceptSheetHandle} />

        <Text style={styles.conceptSheetName}>{concept.name || concept.text}</Text>
        {concept.description ? (
          <Text style={styles.conceptSheetDesc}>{concept.description}</Text>
        ) : null}

        <View style={styles.conceptSheetStateRow}>
          {stateOptions.map(({ level, label }) => (
            <Pressable
              key={level}
              style={[
                styles.conceptSheetStateBtn,
                currentState === level && styles.conceptSheetStateBtnActive,
              ]}
              onPress={() => {
                logEvent('concept_state_change', { concept_id: concept.id, from: currentState, to: level });
                onStateChange(level);
              }}
            >
              <Text style={[
                styles.conceptSheetStateBtnText,
                currentState === level && styles.conceptSheetStateBtnTextActive,
              ]}>{label}</Text>
            </Pressable>
          ))}
        </View>

        {otherArticles.length > 0 && (
          <View style={styles.conceptSheetSection}>
            <Text style={styles.conceptSheetSectionTitle}>Also in</Text>
            {otherArticles.slice(0, 3).map(art => (
              <Pressable
                key={art!.id}
                style={styles.conceptSheetArticleRow}
                onPress={() => {
                  logEvent('concept_sheet_article_tap', { concept_id: concept.id, target_article: art!.id });
                  onClose();
                  router.push({ pathname: '/reader', params: { id: art!.id } });
                }}
              >
                <Text style={styles.conceptSheetArticleTitle} numberOfLines={1}>{art!.title}</Text>
                <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
              </Pressable>
            ))}
          </View>
        )}

        {relatedConcepts.length > 0 && (
          <View style={styles.conceptSheetSection}>
            <Text style={styles.conceptSheetSectionTitle}>Related</Text>
            <View style={styles.conceptSheetRelatedChips}>
              {relatedConcepts.map(rc => {
                const rcState = getConceptState(rc!.id)?.state || 'unknown';
                return (
                  <Pressable
                    key={rc!.id}
                    style={[styles.conceptChip, styles.conceptSheetRelatedChip]}
                    onPress={() => {
                      logEvent('concept_sheet_related_tap', { from_concept: concept.id, to_concept: rc!.id });
                      onConceptTap(rc!, rcState);
                    }}
                  >
                    <Text style={styles.conceptChipText}>{rc!.name || rc!.text}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        )}

        <Pressable
          style={styles.conceptSheetExploreBtn}
          onPress={() => {
            logEvent('concept_explore_tap', { concept_id: concept.id, concept_name: concept.name || concept.text });
            Alert.alert('Queued', `"${concept.name || concept.text}" added to exploration queue.`);
          }}
        >
          <Ionicons name="compass-outline" size={16} color={colors.parchment} />
          <Text style={styles.conceptSheetExploreBtnText}>Explore more</Text>
        </Pressable>
      </Pressable>
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
            {...(Platform.OS === 'web' ? { accessibilityRole: 'link', href: seg.url, hrefAttrs: { target: '_blank', rel: 'noopener noreferrer' } } as any : {})}
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
export { isSectionValid } from '../lib/markdown-utils';

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
                    <Text style={styles.markdownBullet}>{'·'}</Text>
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

          case 'table':
            return (
              <View key={i} style={styles.tableContainer}>
                {block.headers && block.headers.length > 0 && (
                  <View style={styles.tableRow}>
                    {block.headers.map((h, hi) => (
                      <View key={hi} style={[styles.tableCell, styles.tableHeaderCell]}>
                        <Text style={styles.tableHeaderText}>{renderInlineMarkdown(h)}</Text>
                      </View>
                    ))}
                  </View>
                )}
                {(block.rows || []).map((row, ri) => (
                  <View key={ri} style={[styles.tableRow, ri % 2 === 1 && styles.tableRowAlt]}>
                    {row.map((cell, ci) => (
                      <View key={ci} style={styles.tableCell}>
                        <Text style={styles.tableCellText}>{renderInlineMarkdown(cell)}</Text>
                      </View>
                    ))}
                  </View>
                ))}
              </View>
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
            <Text style={styles.sectionSummary} numberOfLines={Platform.OS === 'web' ? undefined : 2}>{section.summary}</Text>
          )}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMuted} />
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

// --- Text note input (web replacement for voice recording) ---

function TextNoteInput({ articleId, currentDepth, onNoteSubmitted }: {
  articleId: string;
  currentDepth: ReadingDepth;
  onNoteSubmitted?: (text: string, noteId: string) => void;
}) {
  const [text, setText] = useState('');
  const [expanded, setExpanded] = useState(false);

  const handleSubmit = useCallback(() => {
    if (!text.trim()) return;
    const noteId = `tn_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const note: VoiceNote = {
      id: noteId,
      article_id: articleId,
      depth: currentDepth,
      recorded_at: Date.now(),
      duration_ms: 0,
      file_uri: '',
      transcription_status: 'completed',
      transcript: text.trim(),
    };
    addVoiceNote(note);
    logEvent('text_note_added', { article_id: articleId, depth: currentDepth, length: text.length });
    const submitted = text.trim();
    setText('');
    setExpanded(false);
    if (onNoteSubmitted) onNoteSubmitted(submitted, noteId);
  }, [text, articleId, currentDepth, onNoteSubmitted]);

  if (!expanded) {
    return (
      <Pressable style={styles.textNoteBtn} onPress={() => setExpanded(true)}>
        <Ionicons name="create-outline" size={16} color={colors.rubric} />
        <Text style={styles.textNoteBtnText}>Add note</Text>
      </Pressable>
    );
  }

  return (
    <View style={styles.textNoteContainer}>
      <TextInput
        style={styles.textNoteInput}
        placeholder="Your thoughts..."
        placeholderTextColor={colors.textMuted}
        multiline
        value={text}
        onChangeText={setText}
        autoFocus
      />
      <View style={styles.textNoteActions}>
        <Pressable style={styles.textNoteCancelBtn} onPress={() => { setText(''); setExpanded(false); }}>
          <Text style={styles.textNoteCancelText}>Cancel</Text>
        </Pressable>
        <Pressable
          style={[styles.textNoteSubmitBtn, !text.trim() && { opacity: 0.4 }]}
          onPress={handleSubmit}
          disabled={!text.trim()}
        >
          <Ionicons name="send" size={14} color={colors.parchment} />
          <Text style={styles.textNoteSubmitText}>Save</Text>
        </Pressable>
      </View>
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
        color={isRecording ? colors.rubric : transcribing ? colors.warning : colors.ink}
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
        <Ionicons name="checkmark-circle" size={16} color={colors.success} />
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
          <Ionicons name="search" size={14} color={colors.parchment} />
          <Text style={styles.researchBtnText}>
            {sending ? 'Sending...' : 'Research this?'}
          </Text>
        </Pressable>
        <Pressable style={styles.researchDismissBtn} onPress={onDismiss}>
          <Ionicons name="close" size={14} color={colors.textMuted} />
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
  const isDesktop = useIsDesktopWeb();
  const article = getArticleById(id || '');

  // --- State ---
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [currentZone, setCurrentZone] = useState<DepthZone>('summary');
  const [claimSignals, setClaimSignals] = useState<ClaimSignalState>({});
  const [activeClaimPill, setActiveClaimPill] = useState<number | null>(null);
  const [signaledClaimCount, setSignaledClaimCount] = useState(0);
  const [researchBanner, setResearchBanner] = useState<{ transcript: string; noteId: string } | null>(null);
  const [selectedConcept, setSelectedConcept] = useState<{ concept: Concept; state: ConceptKnowledgeLevel } | null>(null);
  const [highlightedBlocks, setHighlightedBlocks] = useState<Set<number>>(new Set());
  const [articleResearchCount, setArticleResearchCount] = useState(0);
  const [showRestoredIndicator, setShowRestoredIndicator] = useState(false);
  const [showDismissMenu, setShowDismissMenu] = useState(false);
  const restoredIndicatorOpacity = useRef(new Animated.Value(1)).current;

  // --- Refs ---
  const scrollRef = useRef<ScrollView>(null);
  const enterTime = useRef(Date.now());
  const lastPositionSaveTime = useRef(0);

  // Section layout positions for depth zone tracking
  const zonePositions = useRef<Record<DepthZone, number>>({
    summary: 0,
    concepts: 0,
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
        concepts: 'concepts',
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
    addSignal({ article_id: article.id, signal: mappedSignal, timestamp: Date.now(), depth: 'concepts' });
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
  const [highlightNoteMode, setHighlightNoteMode] = useState(false);
  const [highlightNoteText, setHighlightNoteText] = useState('');

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
      <View style={[styles.container, isDesktop && styles.desktopContainer]}>
        <Text style={styles.errorText}>Article not found</Text>
        <Pressable onPress={() => router.back()}>
          <Text style={styles.backLink}>Back to feed</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={[styles.container, isDesktop && styles.desktopContainer]}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Text style={styles.backLinkText}>{'← Feed'}</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        {Platform.OS === 'web' ? (
          <TextNoteInput
            articleId={article.id}
            currentDepth={currentZone}
            onNoteSubmitted={(text, noteId) => {
              processTranscriptForConcepts(article.id, text, noteId);
              setResearchBanner({ transcript: text, noteId });
            }}
          />
        ) : (
          <VoiceRecordButton
            articleId={article.id}
            currentDepth={currentZone}
            onTranscribed={(transcript, noteId) => setResearchBanner({ transcript, noteId })}
          />
        )}
        {articleResearchCount > 0 && (
          <Pressable
            style={styles.researchBadge}
            onPress={() => {
              logEvent('reader_research_badge_tap', { article_id: article.id, count: articleResearchCount });
              router.push('/stats');
            }}
          >
            <Ionicons name="flask" size={14} color={colors.rubric} />
            <Text style={styles.researchBadgeText}>{articleResearchCount}</Text>
          </Pressable>
        )}
        <Pressable onPress={() => {
          if (Platform.OS === 'web') {
            setShowDismissMenu(true);
          } else {
            Alert.alert('Dismiss article', 'Why are you dismissing this?', [
              { text: 'Not useful', onPress: () => { dismissArticle(article.id, 'low_quality'); router.back(); } },
              { text: 'Wrong topic', onPress: () => { dismissArticle(article.id, 'not_relevant'); router.back(); } },
              { text: 'Duplicate', onPress: () => { dismissArticle(article.id, 'duplicate'); router.back(); } },
              { text: 'Cancel', style: 'cancel' },
            ]);
          }
          logEvent('dismiss_menu_open', { article_id: article.id });
        }}>
          <Ionicons name="flag-outline" size={20} color={colors.rubric} />
        </Pressable>
        <Pressable onPress={() => {
          logEvent('reader_open_source', { article_id: article.id, url: article.source_url });
          Linking.openURL(article.source_url);
        }}>
          <Ionicons name="open-outline" size={20} color={colors.textMuted} />
        </Pressable>
      </View>

      {/* Dismiss menu (web) */}
      {showDismissMenu && (
        <View style={styles.dismissOverlay}>
          <View style={styles.dismissMenu}>
            <Text style={styles.dismissMenuTitle}>Dismiss article</Text>
            {([
              ['Not useful', 'low_quality'],
              ['Wrong topic', 'not_relevant'],
              ['Duplicate', 'duplicate'],
            ] as const).map(([label, reason]) => (
              <Pressable
                key={reason}
                style={styles.dismissMenuItem}
                onPress={() => {
                  dismissArticle(article.id, reason);
                  setShowDismissMenu(false);
                  router.back();
                }}
              >
                <Text style={styles.dismissMenuItemText}>{label}</Text>
              </Pressable>
            ))}
            <Pressable
              style={[styles.dismissMenuItem, { borderTopWidth: 1, borderTopColor: colors.rule }]}
              onPress={() => setShowDismissMenu(false)}
            >
              <Text style={[styles.dismissMenuItemText, { color: colors.textMuted }]}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      )}

      {/* Sticky floating depth indicator */}
      <FloatingDepthIndicator
        currentZone={currentZone}
        conceptCount={getConceptsForArticleWithState(article.id).length}
        sectionCount={article.sections.filter(isSectionValid).length}
      />

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
        testID="reader-content"
      >
        {/* ═══════════ HEADER ZONE ═══════════ */}
        <View onLayout={onZoneLayout('summary')}>
          <Text style={styles.articleTitle}>{getDisplayTitle(article)}</Text>
          <View style={styles.metaRow}>
            {article.author ? <Text style={styles.metaText}>{article.author}</Text> : null}
            <Text style={styles.metaText}>{article.hostname}</Text>
            {article.date ? <Text style={styles.metaText}>{article.date}</Text> : null}
            <Text style={styles.metaText}>{article.estimated_read_minutes} min · {article.word_count} words</Text>
          </View>

          {/* Time guidance */}
          <View style={styles.timeGuideRow}>
            <View style={styles.timeGuideItem}>
              <Text style={styles.timeGuideText}>30s summary</Text>
            </View>
            <Text style={styles.timeGuideSep}>·</Text>
            <View style={styles.timeGuideItem}>
              <Text style={styles.timeGuideText}>1m concepts</Text>
            </View>
            {article.sections.length > 1 && (
              <>
                <Text style={styles.timeGuideSep}>·</Text>
                <View style={styles.timeGuideItem}>
                  <Text style={styles.timeGuideText}>{Math.ceil(article.estimated_read_minutes / 2)}m sections</Text>
                </View>
              </>
            )}
            <Text style={styles.timeGuideSep}>·</Text>
            <View style={styles.timeGuideItem}>
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
          <MarkdownText content={stripLeadingTitle(article.full_summary, article.title)} />

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
                <Ionicons name="copy-outline" size={14} color={colors.warning} />
                <Text style={styles.dedupBannerText}>
                  Similar to: {readSimilar[0].title}
                </Text>
              </Pressable>
            );
          })()}
        </View>

        {/* ═══════════ CONCEPTS ZONE ═══════════ */}
        <View onLayout={onZoneLayout('concepts')}>
          {(() => {
            const articleConcepts = getConceptsForArticleWithState(article.id);
            if (articleConcepts.length === 0) return null;
            return (
              <>
                <View style={styles.divider}>
                  <View style={styles.dividerLine} />
                  <Text style={styles.dividerText}>✦ CONCEPTS</Text>
                  <View style={styles.dividerLine} />
                </View>

                <View style={styles.conceptChipsContainer}>
                  {articleConcepts.map(({ concept, state }) => (
                    <Pressable
                      key={concept.id}
                      style={[
                        styles.conceptChip,
                        state === 'unknown' && styles.conceptChipUnknown,
                        state === 'encountered' && styles.conceptChipLearning,
                        state === 'known' && styles.conceptChipKnown,
                      ]}
                      onPress={() => {
                        logEvent('concept_chip_tap', { article_id: article.id, concept_id: concept.id, concept_name: concept.name || concept.text });
                        setSelectedConcept({ concept, state });
                      }}
                    >
                      <View style={[
                        styles.conceptChipDot,
                        state === 'unknown' && { backgroundColor: colors.textMuted },
                        state === 'encountered' && { backgroundColor: colors.claimNew },
                        state === 'known' && { backgroundColor: colors.textMuted },
                      ]} />
                      <Text style={[
                        styles.conceptChipText,
                        state === 'encountered' && { color: colors.claimNew },
                        state === 'known' && { color: colors.textMuted, opacity: 0.7 },
                      ]}>
                        {concept.name || concept.text}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </>
            );
          })()}
        </View>

        {/* ═══════════ SECTIONS ZONE ═══════════ */}
        {article.sections.length > 1 && (
          <View onLayout={onZoneLayout('sections')}>
            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>✦ SECTIONS</Text>
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
            <Text style={styles.dividerText}>✦ FULL ARTICLE</Text>
            <View style={styles.dividerLine} />
          </View>

          {/* Use clean LLM-generated sections when available, fall back to raw markdown */}
          {article.sections.filter(isSectionValid).length > 1 ? (
            article.sections.filter(isSectionValid).map((section, i) => (
              <View key={i} style={{ marginBottom: spacing.lg }}>
                <Text style={styles.fullSectionHeading}>{section.heading}</Text>
                <MarkdownText
                  content={section.content}
                  claimHighlights={article.key_claims}
                  claimSignals={claimSignals}
                  onClaimTap={handleInlineClaimTap}
                  highlightedBlocks={highlightedBlocks}
                  onBlockLongPress={handleBlockLongPress}
                />
              </View>
            ))
          ) : (
            <MarkdownText
              content={article.content_markdown}
              claimHighlights={article.key_claims}
              claimSignals={claimSignals}
              onClaimTap={handleInlineClaimTap}
              highlightedBlocks={highlightedBlocks}
              onBlockLongPress={handleBlockLongPress}
            />
          )}

          {article.source_url && (
            <Pressable
              style={styles.viewOriginalLink}
              onPress={() => {
                logEvent('view_original_source', { article_id: article.id, url: article.source_url });
                Linking.openURL(article.source_url);
              }}
            >
              <Text style={styles.viewOriginalText}>View original source →</Text>
            </Pressable>
          )}
        </View>

        {/* Related articles (connection prompting) */}
        {(() => {
          const related = getRelatedArticles(article.id);
          if (related.length === 0) return null;
          return (
            <View style={styles.relatedSection}>
              <View style={styles.divider}>
                <View style={styles.dividerLine} />
                <Text style={styles.dividerText}>✦ RELATED READING</Text>
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
            <Text style={styles.sourceText} numberOfLines={Platform.OS === 'web' ? undefined : 3}>
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

      {/* Concept detail sheet */}
      {selectedConcept && article && (
        <ConceptSheet
          concept={selectedConcept.concept}
          currentState={selectedConcept.state}
          currentArticleId={article.id}
          onClose={() => setSelectedConcept(null)}
          onStateChange={(level) => {
            updateConceptState(selectedConcept.concept.id, level);
            setSelectedConcept({ ...selectedConcept, state: level });
          }}
          onConceptTap={(concept, state) => {
            setSelectedConcept({ concept, state });
          }}
        />
      )}

      {/* Highlight action bar */}
      {highlightAction && (
        <View style={styles.highlightActionBar}>
          {highlightNoteMode ? (
            <View style={{ flex: 1 }}>
              <TextInput
                style={styles.highlightNoteInput}
                placeholder="Your note on this passage..."
                placeholderTextColor={colors.textMuted}
                value={highlightNoteText}
                onChangeText={setHighlightNoteText}
                autoFocus
                multiline
              />
              <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 6 }}>
                <Pressable onPress={() => { setHighlightNoteMode(false); setHighlightNoteText(''); }}>
                  <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>Cancel</Text>
                </Pressable>
                <Pressable
                  style={[styles.highlightNoteSaveBtn, !highlightNoteText.trim() && { opacity: 0.4 }]}
                  onPress={() => {
                    if (highlightNoteText.trim() && article) {
                      updateHighlightNote(article.id, highlightAction.blockIndex, highlightNoteText.trim());
                      logEvent('highlight_note_saved', { article_id: article.id, block_index: highlightAction.blockIndex });
                    }
                    setHighlightNoteMode(false);
                    setHighlightNoteText('');
                    setHighlightAction(null);
                  }}
                  disabled={!highlightNoteText.trim()}
                >
                  <Text style={{ color: colors.parchment, fontFamily: fonts.body, fontSize: 13, fontWeight: '600' }}>Save</Text>
                </Pressable>
              </View>
            </View>
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={16} color={colors.warning} />
              <Text style={styles.highlightActionText}>Highlighted</Text>
              <Pressable
                style={styles.highlightNoteBtn}
                onPress={() => setHighlightNoteMode(true)}
              >
                <Ionicons name="create-outline" size={14} color={colors.rubric} />
                <Text style={styles.highlightNoteLabel}>Note</Text>
              </Pressable>
              <Pressable style={styles.highlightResearchBtn} onPress={handleResearchHighlight}>
                <Ionicons name="search" size={14} color={colors.rubric} />
                <Text style={styles.highlightResearchText}>Research</Text>
              </Pressable>
              <Pressable onPress={() => setHighlightAction(null)}>
                <Ionicons name="close" size={16} color={colors.textMuted} />
              </Pressable>
            </>
          )}
        </View>
      )}
    </View>
  );
}

// ============================================================
// Styles
// ============================================================

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  desktopContainer: { maxWidth: layout.readingMeasure, alignSelf: 'center' as const, width: '100%' as any },
  topBar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: layout.screenPadding, paddingTop: Platform.OS === 'web' ? 12 : 56, paddingBottom: spacing.sm, gap: 12,
  },
  backButton: { padding: 4 },
  backLinkText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? {} : {}),
  },
  scroll: { flex: 1, paddingHorizontal: Platform.OS === 'web' ? 40 : 20 },
  errorText: { color: colors.rubric, fontFamily: fonts.reading, fontSize: 16, textAlign: 'center', marginTop: 100 },
  backLink: { color: colors.rubric, fontFamily: fonts.body, fontSize: 14, textAlign: 'center', marginTop: 12 },

  // Floating depth indicator
  depthIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: layout.screenPadding,
    backgroundColor: colors.parchment,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    gap: spacing.xl,
  },
  depthIndicatorItem: { alignItems: 'center' },
  depthLabel: {
    fontFamily: fonts.body,
    color: colors.textFaint,
    fontSize: 11.5,
  },
  depthLabelActive: { color: colors.rubric },
  depthUnderline: {
    height: layout.depthUnderlineHeight,
    backgroundColor: colors.rubric,
    width: '100%',
    marginTop: 4,
    borderRadius: 1,
  },
  depthCount: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, fontWeight: '400' as const },

  // Article header
  articleTitle: {
    ...type.readerTitle,
    color: colors.ink,
    marginBottom: 10,
  },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: 10 },
  metaText: { ...type.metadata, color: colors.textMuted },
  topicsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: spacing.xl },
  topicPill: { paddingHorizontal: 0, paddingVertical: 2 },
  topicText: { ...type.topicTag, color: colors.rubric },

  // Summary
  fullSummary: {
    ...type.readerBody,
    color: colors.textBody,
    marginBottom: spacing.xxl,
  },

  // Dividers between zones — rubric star markers
  divider: {
    flexDirection: 'row', alignItems: 'center',
    marginTop: 28, marginBottom: spacing.xl, gap: 12,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: colors.rule },
  dividerText: {
    ...type.sectionHead,
    color: colors.rubric,
  },

  // Claims progress
  claimsProgress: {
    fontFamily: fonts.ui,
    fontSize: 10,
    textTransform: 'uppercase' as const,
    letterSpacing: 1,
    color: colors.textMuted,
    marginBottom: 12,
    textAlign: 'center',
  },

  // Claims list — left border, no background
  claimCard: {
    backgroundColor: 'transparent',
    borderRadius: 0,
    padding: spacing.lg,
    marginBottom: 10,
    borderLeftWidth: layout.claimBorderWidth,
    borderLeftColor: colors.claimDefault,
  },
  claimCardKnew: { borderLeftColor: colors.claimKnown, opacity: colors.claimKnownOpacity },
  claimCardNew: { borderLeftColor: colors.claimNew },
  claimCardSave: { borderLeftColor: colors.rubric },
  claimCardText: { ...type.claimText, color: colors.textBody, marginBottom: 10 },
  claimActions: { flexDirection: 'row', gap: spacing.sm },
  claimBtn: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 4, backgroundColor: 'transparent',
    borderWidth: 1, borderColor: colors.rule,
  },
  claimBtnNewBorder: { borderColor: colors.claimNew, backgroundColor: 'transparent' },
  claimBtnActiveKnew: { backgroundColor: colors.rule },
  claimBtnActiveNew: { backgroundColor: colors.claimNew, borderColor: colors.claimNew },
  claimBtnText: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 11, fontWeight: '500' as const },

  // Section cards
  sectionCard: { backgroundColor: 'transparent', borderRadius: 0, marginBottom: 10, borderBottomWidth: 1, borderBottomColor: colors.rule },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.lg, gap: spacing.sm },
  sectionHeading: { fontFamily: fonts.bodyMedium, color: colors.ink, fontSize: 15, ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}) },
  sectionSummary: { fontFamily: fonts.reading, color: colors.textSecondary, fontSize: 13, lineHeight: 18, marginTop: 4 },
  sectionContent: { paddingBottom: spacing.lg },
  sectionClaims: { marginBottom: 12, paddingLeft: 4 },
  claimRow: { flexDirection: 'row', marginBottom: 6 },
  claimArrow: { color: colors.rubric, marginRight: 8, fontFamily: fonts.body, fontSize: 13 },
  claimRowText: { fontFamily: fonts.reading, color: colors.textSecondary, fontSize: 13, lineHeight: 19, flex: 1 },

  // Markdown rendering
  markdownHeading: {
    fontFamily: fonts.bodyMedium,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
    marginTop: 20, marginBottom: 10, lineHeight: 28,
  },
  markdownText: {
    ...type.readerBody,
    color: colors.textBody,
    marginBottom: 14,
  },
  markdownList: { marginBottom: 14 },
  markdownListItem: { flexDirection: 'row', marginBottom: 6, paddingRight: 8 },
  markdownBullet: { color: colors.rubric, marginRight: 10, fontSize: 16 },
  markdownOrderedBullet: { color: colors.rubric, marginRight: 10, fontSize: 14, minWidth: 20, fontFamily: fonts.body },
  codeBlock: { backgroundColor: colors.parchmentDark, borderRadius: 4, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.rule },
  codeText: { color: colors.textSecondary, fontSize: 13, fontFamily: 'monospace' },
  markdownLink: { color: colors.info, textDecorationLine: 'underline' as const },
  markdownBold: { color: colors.ink, fontWeight: '700' as const },
  markdownItalic: { color: colors.textBody, fontStyle: 'italic' as const },
  markdownInlineCode: { color: colors.textSecondary, fontFamily: 'monospace', backgroundColor: colors.parchmentDark, paddingHorizontal: 4 },
  markdownBlockquote: {
    borderLeftWidth: 3, borderLeftColor: colors.rubric,
    paddingLeft: 14, marginBottom: 14, marginLeft: 4,
  },
  markdownBlockquoteText: {
    fontFamily: fonts.readingItalic,
    color: colors.textSecondary, fontSize: 15, lineHeight: 24,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  markdownHr: { height: 1, backgroundColor: colors.rule, marginVertical: 20 },
  tableContainer: {
    marginBottom: 14,
    borderRadius: 4,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.rule,
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  tableRowAlt: { backgroundColor: colors.parchmentDark },
  tableCell: {
    flex: 1,
    paddingVertical: 8,
    paddingHorizontal: 10,
  },
  tableHeaderCell: {
    backgroundColor: colors.parchmentDark,
  },
  tableHeaderText: {
    fontFamily: fonts.bodyMedium,
    color: colors.ink,
    fontSize: 13,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  tableCellText: {
    fontFamily: fonts.reading,
    color: colors.textBody,
    fontSize: 13,
    lineHeight: 18,
  },

  // Dedup banner
  dedupBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'transparent',
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
    padding: 12,
    borderRadius: 0,
    marginTop: 12,
  },
  dedupBannerText: {
    fontFamily: fonts.reading,
    color: colors.warning,
    fontSize: 13,
    flex: 1,
  },

  // Paragraph highlighting (long-press) — amber left border
  paragraphHighlight: {
    backgroundColor: 'transparent',
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
    paddingLeft: 8,
    borderRadius: 0,
    marginLeft: -8,
  },

  // Inline claim highlights in full text
  claimHighlightUnsignaled: {
    backgroundColor: 'transparent', borderRadius: 0,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: colors.claimDefault,
  },
  claimHighlightKnew: {
    backgroundColor: 'transparent', borderRadius: 0,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: colors.claimKnown, opacity: colors.claimKnownOpacity,
  },
  claimHighlightNew: {
    backgroundColor: 'transparent', borderRadius: 0,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: colors.claimNew,
  },
  claimHighlightSave: {
    backgroundColor: 'transparent', borderRadius: 0,
    paddingHorizontal: 4, paddingVertical: 2,
    borderLeftWidth: 3, borderLeftColor: colors.rubric,
  },

  // Floating signal pill
  pillBackdrop: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'center', alignItems: 'center',
  },
  pillContainer: {
    flexDirection: 'row', backgroundColor: colors.parchment,
    borderRadius: 8, padding: 6, gap: 4,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15, shadowRadius: 12, elevation: 8,
    borderWidth: 1, borderColor: colors.rule,
  },
  pillBtn: {
    paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: 4, backgroundColor: colors.parchmentDark,
  },
  pillBtnNew: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.claimNew },
  pillBtnSave: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.rubric },
  pillBtnText: { fontFamily: fonts.body, color: colors.ink, fontSize: 13 },

  // Source attribution
  sourceBox: {
    backgroundColor: 'transparent', borderRadius: 0, padding: 16,
    marginTop: 24, borderLeftWidth: 3, borderLeftColor: colors.rule,
  },
  sourceLabel: { fontFamily: fonts.body, color: colors.rubric, fontSize: 12, marginBottom: 6 },
  sourceText: { fontFamily: fonts.reading, color: colors.textMuted, fontSize: 13, lineHeight: 19 },

  // Time guidance
  timeGuideRow: {
    flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: 12,
    paddingVertical: spacing.sm, paddingHorizontal: 0,
    alignItems: 'center',
  },
  timeGuideItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  timeGuideText: { fontFamily: fonts.ui, color: colors.textMuted, fontSize: 11 },
  timeGuideSep: { color: colors.textMuted, fontSize: 11 },

  // Related articles
  relatedSection: { marginTop: 16 },
  relatedCard: {
    backgroundColor: 'transparent', borderRadius: 0, padding: 14,
    marginBottom: 8, borderLeftWidth: 3, borderLeftColor: colors.rubric,
  },
  relatedTitle: { fontFamily: fonts.bodyMedium, color: colors.ink, fontSize: 14, ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}), marginBottom: 4 },
  relatedConnection: { fontFamily: fonts.reading, color: colors.rubric, fontSize: 12, lineHeight: 16 },

  // Connection callout card — rubric left border
  connectionCard: {
    marginTop: -2,
    marginBottom: 12,
    padding: 12,
    backgroundColor: 'transparent',
    borderRadius: 0,
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
  },
  connectionHeader: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    marginBottom: 8,
  },
  connectionLabel: {
    fontFamily: fonts.body,
    color: colors.rubric,
    fontSize: 12,
  },
  connectionArticleRow: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    paddingVertical: 6,
    paddingHorizontal: 4,
  },
  connectionArticleTitle: {
    fontFamily: fonts.body,
    color: colors.ink,
    fontSize: 13,
    flex: 1,
    marginRight: 8,
  },
  connectionMore: {
    fontFamily: fonts.ui,
    color: colors.textMuted,
    fontSize: 11,
    marginTop: 4,
    paddingHorizontal: 4,
  },

  // Voice recording
  voiceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 4, backgroundColor: colors.parchmentDark, marginRight: 10,
    borderWidth: 1, borderColor: colors.rule,
  },
  voiceBtnRecording: { backgroundColor: '#fce4e4', borderColor: colors.rubric },
  voiceTimer: { fontFamily: fonts.ui, color: colors.rubric, fontSize: 12, fontWeight: '700' as const },
  voiceCount: { fontFamily: fonts.ui, color: colors.textMuted, fontSize: 11 },

  // Restored position indicator
  restoredIndicator: {
    alignItems: 'center',
    paddingVertical: 6,
    backgroundColor: colors.parchmentDark,
  },
  restoredText: {
    fontFamily: fonts.ui,
    color: colors.textMuted,
    fontSize: 12,
  },

  // Research banner — rubric left border
  researchBanner: {
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    marginHorizontal: layout.screenPadding,
    marginVertical: spacing.sm,
    padding: 12,
    borderRadius: 0,
  },
  researchTranscript: {
    fontFamily: fonts.readingItalic,
    color: colors.textBody,
    fontSize: 13,
    lineHeight: 19,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  researchBtn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    backgroundColor: colors.rubric,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 4,
  },
  researchBtnText: {
    fontFamily: fonts.body,
    color: colors.parchment,
    fontSize: 13,
  },
  researchDismissBtn: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 4,
    backgroundColor: colors.parchmentDark,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  researchBannerText: {
    fontFamily: fonts.body,
    color: colors.success,
    fontSize: 13,
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
    backgroundColor: colors.parchment,
    borderRadius: 4,
    padding: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  highlightActionText: {
    fontFamily: fonts.body,
    color: colors.warning,
    fontSize: 13,
    flex: 1,
  },
  highlightNoteBtn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    backgroundColor: 'transparent',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  highlightNoteLabel: {
    fontFamily: fonts.body,
    color: colors.rubric,
    fontSize: 12,
  },
  highlightNoteInput: {
    fontFamily: fonts.reading,
    color: colors.ink,
    fontSize: 14,
    lineHeight: 20,
    minHeight: 36,
  },
  highlightNoteSaveBtn: {
    backgroundColor: colors.rubric,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 4,
  },
  highlightResearchBtn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    backgroundColor: 'transparent',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  highlightResearchText: {
    fontFamily: fonts.body,
    color: colors.rubric,
    fontSize: 12,
  },

  // Text note input (web)
  textNoteBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 4, backgroundColor: colors.parchmentDark, marginRight: 10,
    borderWidth: 1, borderColor: colors.rule,
  },
  textNoteBtnText: { fontFamily: fonts.body, color: colors.rubric, fontSize: 12 },
  textNoteContainer: {
    position: 'absolute' as const, top: '100%' as any, right: 0,
    width: 300, backgroundColor: colors.parchment, borderRadius: 4, padding: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15, shadowRadius: 12, elevation: 8,
    borderWidth: 1, borderColor: colors.rule, zIndex: 100,
  },
  textNoteInput: {
    fontFamily: fonts.reading, color: colors.ink, fontSize: 14, lineHeight: 20,
    minHeight: 60, textAlignVertical: 'top' as const,
    marginBottom: 8,
  },
  textNoteActions: {
    flexDirection: 'row' as const, justifyContent: 'flex-end' as const, gap: 8,
  },
  textNoteCancelBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4 },
  textNoteCancelText: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 13 },
  textNoteSubmitBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
    backgroundColor: colors.rubric, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4,
  },
  textNoteSubmitText: { fontFamily: fonts.body, color: colors.parchment, fontSize: 13 },

  // Claim research button
  claimResearchBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 4, backgroundColor: 'transparent',
    borderWidth: 1, borderColor: colors.rule,
    marginLeft: 'auto' as any,
  },
  claimResearchText: { fontFamily: fonts.body, color: colors.rubric, fontSize: 11 },

  // Research results badge in top bar
  researchBadge: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    marginRight: 4,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  researchBadgeText: {
    fontFamily: fonts.body,
    color: colors.rubric,
    fontSize: 11,
  },

  // Dismiss menu (web)
  dismissOverlay: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.3)',
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    zIndex: 100,
  },
  dismissMenu: {
    backgroundColor: colors.parchment,
    borderRadius: 4,
    width: 260,
    overflow: 'hidden' as const,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  dismissMenuTitle: {
    fontFamily: fonts.bodyMedium,
    color: colors.ink,
    fontSize: 15,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
    padding: 16,
    textAlign: 'center' as const,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  dismissMenuItem: {
    padding: 14,
  },
  dismissMenuItemText: {
    fontFamily: fonts.body,
    color: colors.ink,
    fontSize: 14,
    textAlign: 'center' as const,
  },

  // Concept chips
  conceptChipsContainer: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: 8,
    paddingVertical: spacing.sm,
  },
  conceptChip: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 4,
    backgroundColor: colors.parchmentDark,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  conceptChipUnknown: {},
  conceptChipLearning: {
    borderColor: colors.claimNew,
    backgroundColor: 'transparent',
  },
  conceptChipKnown: {
    borderColor: colors.rule,
    borderStyle: 'dashed' as const,
    opacity: 0.6,
  },
  conceptChipDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.textMuted,
  },
  conceptChipText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.ink,
  },

  // Full article section headings
  fullSectionHeading: {
    fontFamily: fonts.bodyMedium,
    color: colors.ink,
    fontSize: 17,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } : {}),
    marginBottom: spacing.sm,
    lineHeight: 24,
  },

  // View original source link
  viewOriginalLink: {
    paddingVertical: spacing.lg,
    alignItems: 'center' as const,
    marginTop: spacing.md,
  },
  viewOriginalText: {
    fontFamily: fonts.body,
    color: colors.rubric,
    fontSize: 13,
  },

  // Concept sheet (bottom sheet overlay)
  conceptSheetBackdrop: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'flex-end' as const,
    zIndex: 200,
  },
  conceptSheetContainer: {
    backgroundColor: colors.parchment,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 24,
    paddingBottom: 40,
    maxHeight: '70%' as any,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
  },
  conceptSheetHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rule,
    alignSelf: 'center' as const,
    marginBottom: 20,
  },
  conceptSheetName: {
    fontFamily: fonts.bodyMedium,
    color: colors.ink,
    fontSize: 20,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } : {}),
    marginBottom: 8,
  },
  conceptSheetDesc: {
    fontFamily: fonts.reading,
    color: colors.textSecondary,
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 20,
  },
  conceptSheetStateRow: {
    flexDirection: 'row' as const,
    gap: 8,
    marginBottom: 24,
  },
  conceptSheetStateBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.rule,
    alignItems: 'center' as const,
    backgroundColor: 'transparent',
  },
  conceptSheetStateBtnActive: {
    backgroundColor: colors.rubric,
    borderColor: colors.rubric,
  },
  conceptSheetStateBtnText: {
    fontFamily: fonts.body,
    color: colors.textSecondary,
    fontSize: 13,
  },
  conceptSheetStateBtnTextActive: {
    color: colors.parchment,
  },
  conceptSheetSection: {
    marginBottom: 20,
  },
  conceptSheetSectionTitle: {
    fontFamily: fonts.ui,
    color: colors.textMuted,
    fontSize: 11,
    textTransform: 'uppercase' as const,
    letterSpacing: 1,
    marginBottom: 8,
  },
  conceptSheetArticleRow: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  conceptSheetArticleTitle: {
    fontFamily: fonts.body,
    color: colors.ink,
    fontSize: 14,
    flex: 1,
    marginRight: 8,
  },
  conceptSheetRelatedChips: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: 6,
  },
  conceptSheetRelatedChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  conceptSheetExploreBtn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: 8,
    backgroundColor: colors.rubric,
    paddingVertical: 12,
    borderRadius: 4,
    marginTop: 4,
  },
  conceptSheetExploreBtnText: {
    fontFamily: fonts.body,
    color: colors.parchment,
    fontSize: 14,
    fontWeight: '500' as const,
  },
});
