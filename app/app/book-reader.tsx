import { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking, TextInput,
  NativeSyntheticEvent, NativeScrollEvent, LayoutChangeEvent,
  Platform, Animated,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import {
  getBookById, getBookChapterSections, getSectionReadingState,
  updateSectionReadingState, recordBookClaimSignal, addBookTimeSpent,
  addPersonalThreadEntry, getBookProgress, getCachedBookSections,
  processClaimSignalForConcepts, addVoiceNote, getVoiceNotes,
  addHighlight, removeHighlight, getHighlightBlockIndices, updateHighlightNote,
  getBookReadingState, getPersonalThread, getBooks, getBooksByTopic, getByTopic,
  getConcepts, getConceptState,
} from '../data/store';
import {
  BookSection, BookClaim, KeyTerm, CrossBookConnection,
  BookReadingDepth, ClaimSignalType, VoiceNote, Book,
} from '../data/types';
import * as Haptics from 'expo-haptics';
import { logEvent } from '../data/logger';
import { isSectionValid, parseInlineMarkdown, splitMarkdownBlocks, parseMarkdownBlock } from '../lib/markdown-utils';
import { transcribeVoiceNote } from '../data/transcription';
import { colors, fonts, type as typeStyles, spacing, layout } from '../design/tokens';

// --- Depth zone definitions ---

const DEPTH_ZONES = ['briefing', 'claims', 'terms', 'full'] as const;
type DepthZone = typeof DEPTH_ZONES[number];

const DEPTH_LABELS: Record<DepthZone, string> = {
  briefing: 'Briefing',
  claims: 'Claims',
  terms: 'Key Terms',
  full: 'Full Text',
};

// --- Constants ---

const SCROLL_POSITION_SAVE_INTERVAL_MS = 2000;

// --- Inline markdown rendering ---

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
        return <Text key={`bold-${i}`} style={styles.markdownBold}>{seg.text}</Text>;
      case 'italic':
        return <Text key={`italic-${i}`} style={styles.markdownItalic}>{seg.text}</Text>;
      case 'code':
        return <Text key={`code-${i}`} style={styles.markdownInlineCode}>{seg.text}</Text>;
      default:
        return seg.text;
    }
  });
}

// --- MarkdownText component ---

function MarkdownText({ content, highlightedBlocks, onBlockLongPress }: {
  content: string;
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
                    <Text style={styles.markdownText}>{renderInlineMarkdown(item)}</Text>
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
                    <Text style={styles.markdownText}>{renderInlineMarkdown(item)}</Text>
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

          default:
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
      })}
    </View>
  );
}

// --- Floating Depth Indicator ---

function FloatingDepthIndicator({ currentZone, claimCount, termCount, claimsReviewed }: {
  currentZone: DepthZone;
  claimCount: number;
  termCount: number;
  claimsReviewed?: number;
}) {
  const zoneCounts: Partial<Record<DepthZone, number>> = {};
  if (claimCount > 0) zoneCounts.claims = claimCount;
  if (termCount > 0) zoneCounts.terms = termCount;

  return (
    <View style={styles.depthIndicator}>
      {DEPTH_ZONES.map((zone, i) => {
        const active = zone === currentZone;
        const idx = DEPTH_ZONES.indexOf(zone);
        const currentIdx = DEPTH_ZONES.indexOf(currentZone);
        const reached = idx <= currentIdx;
        const count = zoneCounts[zone];
        return (
          <View key={zone} style={styles.depthIndicatorItem}>
            {i > 0 && (
              <View style={[styles.depthConnector, reached && styles.depthConnectorReached]} />
            )}
            <Text style={[
              styles.depthLabel,
              active && styles.depthLabelActive,
              reached && !active && styles.depthLabelReached,
            ]}>
              {DEPTH_LABELS[zone]}
              {zone === 'claims' && claimsReviewed != null && claimCount > 0 ? (
                <Text style={styles.depthCount}> ({claimsReviewed}/{claimCount})</Text>
              ) : count != null ? (
                <Text style={styles.depthCount}> ({count})</Text>
              ) : null}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

// --- Claim Signal Pill ---

function ClaimSignalPill({ currentSignal, onSignal, onDismiss }: {
  currentSignal?: ClaimSignalType;
  onSignal: (s: ClaimSignalType) => void;
  onDismiss: () => void;
}) {
  return (
    <Pressable style={styles.pillBackdrop} onPress={onDismiss}>
      <View style={styles.pillContainer}>
        {currentSignal && (
          <Text style={{ color: colors.textMuted, fontSize: 11, marginBottom: 4 }}>
            Already marked - tap to change
          </Text>
        )}
        <View style={{ flexDirection: 'row', gap: 4 }}>
          <Pressable style={[styles.pillBtn, currentSignal === 'knew_it' && { backgroundColor: colors.rule }]} onPress={() => onSignal('knew_it')}>
            <Text style={styles.pillBtnText}>{currentSignal === 'knew_it' ? 'v ' : ''}Knew this</Text>
          </Pressable>
          <Pressable style={[styles.pillBtn, styles.pillBtnNew, currentSignal === 'interesting' && { backgroundColor: 'rgba(42,122,74,0.15)' }]} onPress={() => onSignal('interesting')}>
            <Text style={[styles.pillBtnText, { color: colors.success }]}>{currentSignal === 'interesting' ? 'v ' : ''}New to me</Text>
          </Pressable>
          <Pressable style={[styles.pillBtn, styles.pillBtnSave, currentSignal === 'save' && { backgroundColor: 'rgba(42,74,106,0.15)' }]} onPress={() => onSignal('save')}>
            <Text style={[styles.pillBtnText, { color: colors.info }]}>{currentSignal === 'save' ? 'v ' : ''}Save</Text>
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

// --- Text Note Input ---

function TextNoteInput({ sectionId, bookId, onNoteSubmitted }: {
  sectionId: string;
  bookId: string;
  onNoteSubmitted?: (text: string, noteId: string) => void;
}) {
  const [text, setText] = useState('');
  const [expanded, setExpanded] = useState(false);

  const handleSubmit = useCallback(() => {
    if (!text.trim()) return;
    const noteId = `tn_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const note: VoiceNote = {
      id: noteId,
      article_id: sectionId,
      depth: 'full',
      recorded_at: Date.now(),
      duration_ms: 0,
      file_uri: '',
      transcription_status: 'completed',
      transcript: text.trim(),
    };
    addVoiceNote(note);
    logEvent('book_text_note_added', { book_id: bookId, section_id: sectionId, length: text.length });
    const submitted = text.trim();
    setText('');
    setExpanded(false);
    if (onNoteSubmitted) onNoteSubmitted(submitted, noteId);
  }, [text, sectionId, bookId, onNoteSubmitted]);

  if (!expanded) {
    return (
      <Pressable style={styles.textNoteBtn} onPress={() => setExpanded(true)}>
        <Ionicons name="create-outline" size={16} color={colors.info} />
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
          <Ionicons name="send" size={14} color={colors.ink} />
          <Text style={styles.textNoteSubmitText}>Save</Text>
        </Pressable>
      </View>
    </View>
  );
}

// --- Voice Record Button ---

function VoiceRecordButton({ sectionId, bookId, onTranscribed }: {
  sectionId: string;
  bookId: string;
  onTranscribed?: (transcript: string, noteId: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [noteCount, setNoteCount] = useState(() => getVoiceNotes(sectionId).length);

  const startRecording = useCallback(async () => {
    try {
      if (Platform.OS === 'web') return;
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        logEvent('voice_note_permission_denied', { book_id: bookId, section_id: sectionId });
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recordingRef.current = recording;
      setIsRecording(true);
      setRecordingDuration(0);
      timerRef.current = setInterval(() => setRecordingDuration(d => d + 1), 1000);
      logEvent('book_voice_note_start', { book_id: bookId, section_id: sectionId });
    } catch (e) {
      console.warn('[voice] failed to start recording:', e);
    }
  }, [bookId, sectionId]);

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
          article_id: sectionId,
          depth: 'full',
          recorded_at: Date.now(),
          duration_ms: status.durationMillis || recordingDuration * 1000,
          file_uri: uri,
          transcription_status: 'pending',
        };
        addVoiceNote(note);
        setNoteCount(n => n + 1);

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
  }, [sectionId, recordingDuration, onTranscribed]);

  if (Platform.OS === 'web') return null;

  return (
    <Pressable
      style={[styles.voiceBtn, isRecording && styles.voiceBtnRecording]}
      onPress={isRecording ? stopRecording : startRecording}
    >
      <Ionicons
        name={isRecording ? 'stop' : transcribing ? 'hourglass-outline' : 'mic-outline'}
        size={18}
        color={isRecording ? colors.danger : transcribing ? colors.warning : colors.info}
      />
      {isRecording ? (
        <Text style={styles.voiceTimer}>{recordingDuration}s</Text>
      ) : noteCount > 0 ? (
        <Text style={styles.voiceCount}>{noteCount}</Text>
      ) : null}
    </Pressable>
  );
}

// --- Cross-book connection card ---

const CONNECTION_STYLES: Record<string, { color: string; icon: string; label: string; bg: string }> = {
  agrees: { color: colors.success, icon: 'checkmark-circle-outline', label: 'Supports:', bg: 'rgba(42,122,74,0.08)' },
  disagrees: { color: colors.warning, icon: 'flash-outline', label: 'Tension:', bg: 'rgba(146,96,14,0.08)' },
  extends: { color: colors.info, icon: 'arrow-forward-circle-outline', label: 'Extends:', bg: 'rgba(42,74,106,0.08)' },
  provides_evidence: { color: '#7a5195', icon: 'document-text-outline', label: 'Evidence:', bg: 'rgba(122,81,149,0.08)' },
  same_topic: { color: colors.textMuted, icon: 'link-outline', label: 'Also discusses:', bg: 'rgba(176,168,152,0.06)' },
};

function CrossBookConnectionCard({ connection }: { connection: CrossBookConnection }) {
  const router = useRouter();
  const style = CONNECTION_STYLES[connection.relationship] || CONNECTION_STYLES.same_topic;

  return (
    <Pressable
      style={[styles.connectionCard, { backgroundColor: style.bg, borderLeftColor: style.color }]}
      onPress={() => {
        logEvent('book_cross_connection_tap', {
          target_section: connection.target_section_id,
          relationship: connection.relationship,
        });
        const parts = connection.target_section_id.split(':');
        if (parts.length >= 3) {
          router.push({
            pathname: '/book-reader',
            params: { bookId: parts[0], sectionId: connection.target_section_id },
          });
        }
      }}
    >
      <View style={styles.connectionHeader}>
        <Ionicons name={style.icon as any} size={14} color={style.color} />
        <Text style={[styles.connectionLabel, { color: style.color }]}>
          {style.label}
        </Text>
      </View>
      <Text style={styles.connectionQuote} numberOfLines={3}>
        "{connection.target_claim_text}"
      </Text>
      <View style={styles.connectionSource}>
        <Ionicons name="arrow-forward" size={12} color={colors.textMuted} />
        <Text style={styles.connectionSourceText} numberOfLines={1}>
          {connection.target_book_title}
        </Text>
      </View>
    </Pressable>
  );
}

// --- Parse section ID ---

function parseSectionId(sectionId: string): { bookId: string; chapterNum: number; sectionNum: number } | null {
  const match = sectionId.match(/^(.+):ch(\d+):s(\d+)$/);
  if (!match) return null;
  return { bookId: match[1], chapterNum: parseInt(match[2], 10), sectionNum: parseInt(match[3], 10) };
}

// ============================================================
// Book Landing Page — shown when no sectionId is provided
// ============================================================

function BookLandingPage({ book }: { book: Book }) {
  const router = useRouter();
  const progress = getBookProgress(book.id);
  const bookState = getBookReadingState(book.id);
  const personalThread = getPersonalThread(book.id);
  const timeMin = Math.round(bookState.total_time_spent_ms / 60000);

  // Find the next unread section
  let nextUnreadSection: string | null = null;
  for (const ch of book.chapters) {
    if (ch.processing_status !== 'completed') continue;
    for (let s = 1; s <= ch.section_count; s++) {
      const sid = `${book.id}:ch${ch.chapter_number}:s${s}`;
      const state = bookState.section_states[sid];
      if (!state || state.depth === 'unread') {
        nextUnreadSection = sid;
        break;
      }
    }
    if (nextUnreadSection) break;
  }

  // Find last read section (for continue reading)
  let lastReadSection = '';
  let lastReadTime = 0;
  for (const [sid, ss] of Object.entries(bookState.section_states)) {
    if (ss.last_read_at > lastReadTime) {
      lastReadTime = ss.last_read_at;
      lastReadSection = sid;
    }
  }

  // Find related books and articles on same topics
  const booksByTopic = getBooksByTopic();
  const articlesByTopic = getByTopic();
  const relatedBooks = new Set<string>();
  const relatedArticleCount: Record<string, number> = {};
  for (const topic of book.topics) {
    const topicBooks = booksByTopic.get(topic) || [];
    for (const b of topicBooks) {
      if (b.id !== book.id) relatedBooks.add(b.title);
    }
    const topicArticles = articlesByTopic.get(topic) || [];
    if (topicArticles.length > 0) {
      relatedArticleCount[topic] = topicArticles.length;
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color={colors.ink} />
        </Pressable>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <Text style={styles.topBarTitle} numberOfLines={1}>{book.title}</Text>
          <Text style={styles.topBarSubtitle}>{book.author}</Text>
        </View>
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Book header */}
        <Text style={[styles.sectionTitle, { fontSize: 22, marginBottom: 4 }]}>{book.title}</Text>
        <Text style={[styles.metaText, { fontSize: 15, marginBottom: 12 }]}>{book.author} · {book.language}</Text>

        {/* Progress overview */}
        <View style={landingStyles.progressCard}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
            <Text style={landingStyles.progressLabel}>{progress.pct}% read</Text>
            <Text style={landingStyles.progressDetail}>{progress.read}/{progress.total} sections · {timeMin} min</Text>
          </View>
          <View style={landingStyles.progressBar}>
            <View style={[landingStyles.progressFill, { width: `${progress.pct}%` }]} />
          </View>
        </View>

        {/* What You Bring — cross-book connections */}
        {(relatedBooks.size > 0 || Object.keys(relatedArticleCount).length > 0 || personalThread.length > 0) && (
          <View style={landingStyles.whatYouBringCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name="compass" size={16} color={colors.info} />
              <Text style={landingStyles.whatYouBringTitle}>What You Bring</Text>
            </View>
            {relatedBooks.size > 0 && (
              <Text style={landingStyles.whatYouBringText}>
                Also reading: {[...relatedBooks].join(', ')}
              </Text>
            )}
            {Object.keys(relatedArticleCount).length > 0 && (
              <Text style={landingStyles.whatYouBringText}>
                Your articles on related topics: {Object.entries(relatedArticleCount).map(([t, n]) => `${t} (${n})`).join(', ')}
              </Text>
            )}
            {personalThread.length > 0 && (
              <View style={{ marginTop: 8 }}>
                <Text style={[landingStyles.whatYouBringText, { color: '#7a5195', fontWeight: '600', marginBottom: 4 }]}>
                  Your notes ({personalThread.length}):
                </Text>
                {personalThread.slice(-3).map(entry => (
                  <Text key={entry.id} style={landingStyles.threadEntry} numberOfLines={2}>
                    "{entry.text}"
                  </Text>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Engagement stats */}
        {progress.read > 0 && (
          <View style={landingStyles.engagementCard}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-around' }}>
              <View style={{ alignItems: 'center' }}>
                <Text style={landingStyles.engagementNumber}>
                  {Object.values(bookState.section_states).reduce((sum, ss) => sum + Object.keys(ss.claim_signals).length, 0)}
                </Text>
                <Text style={landingStyles.engagementLabel}>Claims reviewed</Text>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Text style={landingStyles.engagementNumber}>
                  {personalThread.filter(e => e.type === 'reflection').length}
                </Text>
                <Text style={landingStyles.engagementLabel}>Reflections</Text>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Text style={landingStyles.engagementNumber}>
                  {timeMin > 0 ? Math.round(timeMin / progress.read) : 0}
                </Text>
                <Text style={landingStyles.engagementLabel}>Min/section</Text>
              </View>
            </View>
          </View>
        )}

        {/* Thesis statement */}
        {book.thesis_statement && (
          <View style={landingStyles.thesisCard}>
            <Text style={landingStyles.thesisLabel}>Thesis</Text>
            <Text style={landingStyles.thesisText}>{book.thesis_statement}</Text>
          </View>
        )}

        {/* Running argument */}
        {book.running_argument.length > 0 && (
          <View style={{ marginTop: 12, marginBottom: 12 }}>
            <Text style={landingStyles.sectionLabel}>The Argument So Far</Text>
            {book.running_argument.map((arg, i) => (
              <View key={i} style={landingStyles.argumentItem}>
                <Text style={landingStyles.argumentChapter}>Ch {i + 1}</Text>
                <Text style={landingStyles.argumentText}>{arg}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Reading timeline — compact visualization of reading sessions */}
        {personalThread.length > 0 && (
          <View style={{ marginBottom: 16 }}>
            <Text style={landingStyles.sectionLabel}>Your Reading Journey</Text>
            <View style={landingStyles.timelineContainer}>
              {personalThread.slice(-8).map((entry, i) => {
                const sectionParsed = parseSectionId(entry.section_id);
                const dayLabel = new Date(entry.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                const icon = entry.type === 'reflection' ? 'sparkles-outline' as const
                  : entry.type === 'voice_note' ? 'mic-outline' as const
                  : entry.type === 'connection' ? 'link-outline' as const
                  : 'chatbubble-outline' as const;
                return (
                  <View key={entry.id} style={landingStyles.timelineItem}>
                    <View style={landingStyles.timelineDot}>
                      <Ionicons name={icon} size={10} color={'#7a5195'} />
                    </View>
                    {i < personalThread.slice(-8).length - 1 && (
                      <View style={landingStyles.timelineLine} />
                    )}
                    <View style={landingStyles.timelineContent}>
                      <Text style={landingStyles.timelineMeta}>
                        {dayLabel} · Ch {sectionParsed?.chapterNum || '?'}, §{sectionParsed?.sectionNum || '?'}
                      </Text>
                      <Text style={landingStyles.timelineText} numberOfLines={2}>{entry.text}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          </View>
        )}

        {/* Chapter map */}
        <Text style={landingStyles.sectionLabel}>Chapters</Text>
        {book.chapters.map(ch => {
          const sectionIds = Array.from({ length: ch.section_count }, (_, i) =>
            `${book.id}:ch${ch.chapter_number}:s${i + 1}`
          );
          const readCount = sectionIds.filter(sid => {
            const s = bookState.section_states[sid];
            return s && s.depth !== 'unread';
          }).length;

          return (
            <Pressable
              key={ch.chapter_number}
              style={landingStyles.chapterItem}
              onPress={() => {
                const firstUnread = sectionIds.find(sid => {
                  const s = bookState.section_states[sid];
                  return !s || s.depth === 'unread';
                });
                const target = firstUnread || sectionIds[0];
                logEvent('book_landing_chapter_tap', { book_id: book.id, chapter: ch.chapter_number });
                router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: target } });
              }}
            >
              <View style={{ flex: 1 }}>
                <Text style={landingStyles.chapterTitle}>
                  Ch {ch.chapter_number}: {ch.title}
                </Text>
                <View style={{ flexDirection: 'row', gap: 4, marginTop: 4 }}>
                  {sectionIds.map(sid => {
                    const s = bookState.section_states[sid];
                    const depth = s?.depth || 'unread';
                    const color = depth === 'unread' ? colors.rule
                      : depth === 'reflected' ? colors.success
                      : colors.info;
                    return <View key={sid} style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: color }} />;
                  })}
                </View>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={landingStyles.chapterProgress}>{readCount}/{ch.section_count}</Text>
                {ch.processing_status === 'pending' && (
                  <Text style={{ color: colors.warning, fontSize: 11 }}>Processing...</Text>
                )}
              </View>
            </Pressable>
          );
        })}

        {/* Action buttons */}
        <View style={{ marginTop: 20, gap: 10, marginBottom: 40 }}>
          {lastReadSection && (
            <Pressable
              style={landingStyles.actionBtn}
              onPress={() => {
                logEvent('book_landing_continue', { book_id: book.id, section_id: lastReadSection });
                router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: lastReadSection } });
              }}
            >
              <Ionicons name="play" size={18} color={colors.ink} />
              <Text style={landingStyles.actionBtnText}>Continue where you left off</Text>
            </Pressable>
          )}
          {nextUnreadSection && nextUnreadSection !== lastReadSection && (
            <Pressable
              style={[landingStyles.actionBtn, { backgroundColor: colors.parchmentDark }]}
              onPress={() => {
                logEvent('book_landing_next_unread', { book_id: book.id, section_id: nextUnreadSection });
                router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: nextUnreadSection! } });
              }}
            >
              <Ionicons name="arrow-forward" size={18} color={colors.info} />
              <Text style={[landingStyles.actionBtnText, { color: colors.info }]}>Next unread section</Text>
            </Pressable>
          )}
          {!lastReadSection && nextUnreadSection && (
            <Pressable
              style={landingStyles.actionBtn}
              onPress={() => {
                logEvent('book_landing_start', { book_id: book.id });
                router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: nextUnreadSection! } });
              }}
            >
              <Ionicons name="play" size={18} color={colors.ink} />
              <Text style={landingStyles.actionBtnText}>Start reading</Text>
            </Pressable>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const landingStyles = StyleSheet.create({
  progressCard: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
  },
  progressLabel: { color: colors.ink, fontSize: 16, fontWeight: '700' },
  progressDetail: { color: colors.textMuted, fontSize: 13 },
  progressBar: {
    height: 4,
    backgroundColor: colors.rule,
    borderRadius: 2,
  },
  progressFill: {
    height: 4,
    backgroundColor: colors.info,
    borderRadius: 2,
  },
  whatYouBringCard: {
    backgroundColor: 'rgba(42,74,106,0.08)',
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
    borderLeftWidth: 3,
    borderLeftColor: colors.info,
  },
  whatYouBringTitle: { color: colors.info, fontSize: 15, fontWeight: '700' },
  whatYouBringText: { color: colors.textMuted, fontSize: 14, lineHeight: 20, marginTop: 4 },
  threadEntry: { color: colors.textSecondary, fontSize: 13, fontStyle: 'italic', marginLeft: 8, marginBottom: 4 },
  thesisCard: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
    borderLeftWidth: 3,
    borderLeftColor: '#7a5195',
  },
  thesisLabel: { color: '#7a5195', fontSize: 12, fontWeight: '700', textTransform: 'uppercase', marginBottom: 6 },
  thesisText: { color: colors.textBody, fontSize: 15, lineHeight: 22, fontStyle: 'italic' },
  sectionLabel: { color: colors.textMuted, fontSize: 13, fontWeight: '700', textTransform: 'uppercase', marginBottom: 10, letterSpacing: 1 },
  argumentItem: { flexDirection: 'row', gap: 10, marginBottom: 8 },
  argumentChapter: { color: colors.textMuted, fontSize: 12, fontWeight: '700', width: 36 },
  argumentText: { color: colors.textSecondary, fontSize: 13, lineHeight: 18, flex: 1 },
  timelineContainer: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 10,
    padding: 12,
  },
  timelineItem: {
    flexDirection: 'row',
    minHeight: 36,
  },
  timelineDot: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(122,81,149,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  timelineLine: {
    position: 'absolute',
    left: 9,
    top: 22,
    bottom: 0,
    width: 2,
    backgroundColor: colors.rule,
  },
  timelineContent: {
    flex: 1,
    marginLeft: 10,
    paddingBottom: 10,
  },
  timelineMeta: { color: colors.textMuted, fontSize: 11, marginBottom: 2 },
  timelineText: { color: colors.textSecondary, fontSize: 13, lineHeight: 18 },
  chapterItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.parchmentDark,
    borderRadius: 8,
    padding: 12,
    marginBottom: 6,
  },
  chapterTitle: { color: colors.ink, fontSize: 14, fontWeight: '500' },
  chapterProgress: { color: colors.textMuted, fontSize: 12 },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: colors.info,
    borderRadius: 10,
    paddingVertical: 14,
    paddingHorizontal: 20,
  },
  actionBtnText: { color: colors.ink, fontSize: 15, fontWeight: '600' },
  engagementCard: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 10,
    padding: 16,
    marginBottom: 12,
  },
  engagementNumber: { color: colors.ink, fontSize: 20, fontWeight: '700' },
  engagementLabel: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
});

// ============================================================
// Main Book Reader Screen
// ============================================================

export default function BookReaderScreen() {
  const { bookId, sectionId } = useLocalSearchParams<{ bookId: string; sectionId: string }>();
  const router = useRouter();

  const parsed = parseSectionId(sectionId || '');
  const book = getBookById(bookId || '');

  // If no sectionId (or invalid), show the book landing page
  if (book && (!sectionId || !parsed)) {
    return <BookLandingPage book={book} />;
  }

  // --- State ---
  const [section, setSection] = useState<BookSection | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentZone, setCurrentZone] = useState<DepthZone>('briefing');
  const [claimSignals, setClaimSignals] = useState<Record<string, ClaimSignalType>>({});
  const [activeClaimPill, setActiveClaimPill] = useState<string | null>(null);
  const [highlightedBlocks, setHighlightedBlocks] = useState<Set<number>>(new Set());
  const [highlightAction, setHighlightAction] = useState<{ blockIndex: number; text: string } | null>(null);
  const [highlightNoteMode, setHighlightNoteMode] = useState(false);
  const [highlightNoteText, setHighlightNoteText] = useState('');
  const [reflectionText, setReflectionText] = useState('');
  const [reflectionSubmitted, setReflectionSubmitted] = useState(false);
  const [allChapterSections, setAllChapterSections] = useState<BookSection[]>([]);
  const [showSkeletonView, setShowSkeletonView] = useState(false);
  const [adaptiveDepthSuggestion, setAdaptiveDepthSuggestion] = useState<{ zone: DepthZone; reason: string } | null>(null);
  const [socraticQuestion, setSocraticQuestion] = useState<string | null>(null);

  // --- Refs ---
  const scrollRef = useRef<ScrollView>(null);
  const enterTime = useRef(Date.now());
  const lastScrollY = useRef(0);
  const lastPositionSaveTime = useRef(0);
  const currentZoneRef = useRef<DepthZone>('briefing');

  const zonePositions = useRef<Record<DepthZone, number>>({
    briefing: 0,
    claims: 0,
    terms: 0,
    full: 0,
  });

  // --- Load section data ---
  useEffect(() => {
    if (!bookId || !parsed) return;

    let cancelled = false;
    setLoading(true);

    (async () => {
      const sections = await getBookChapterSections(bookId, parsed.chapterNum);
      if (cancelled) return;

      setAllChapterSections(sections);
      const found = sections.find(s => s.id === sectionId);
      setSection(found || null);
      setLoading(false);

      if (found) {
        const sState = getSectionReadingState(bookId, found.id);
        setClaimSignals(sState.claim_signals || {});
        setHighlightedBlocks(getHighlightBlockIndices(found.id));

        if (sState.depth === 'unread') {
          updateSectionReadingState(bookId, found.id, { depth: 'briefing', last_read_at: Date.now() });
        }

        logEvent('book_reader_open', {
          book_id: bookId,
          section_id: found.id,
          chapter: parsed.chapterNum,
          section: parsed.sectionNum,
          previous_depth: sState.depth,
        });

        // Adaptive depth: analyze concept familiarity for this section
        if (sState.depth === 'unread') {
          const allConcepts = getConcepts();
          const sectionTerms = found.key_terms.map(t => t.term.toLowerCase());
          const sectionClaimWords = found.claims.map(c => c.text.toLowerCase());
          let knownCount = 0;
          let totalMatched = 0;
          for (const concept of allConcepts) {
            const conceptText = concept.text.toLowerCase();
            const matches = sectionTerms.some(t => conceptText.includes(t) || t.includes(conceptText))
              || sectionClaimWords.some(c => c.includes(conceptText));
            if (matches) {
              totalMatched++;
              const state = getConceptState(concept.id);
              if (state.state === 'known' || state.state === 'encountered') knownCount++;
            }
          }
          const familiarity = totalMatched > 0 ? knownCount / totalMatched : 0;
          if (familiarity >= 0.7 && totalMatched >= 3) {
            setAdaptiveDepthSuggestion({ zone: 'claims', reason: `You know ${knownCount} of ${totalMatched} concepts here` });
            logEvent('adaptive_depth_suggestion', { section_id: found.id, familiarity, known: knownCount, total: totalMatched, suggested: 'claims' });
          } else if (familiarity >= 0.4 && totalMatched >= 3) {
            setAdaptiveDepthSuggestion({ zone: 'briefing', reason: `${totalMatched - knownCount} new concepts to explore` });
          }
        }

        // Socratic question: generate contextual reflection prompt
        if (found.claims.length > 0) {
          const mainClaims = found.claims.filter(c => c.is_main);
          const target = mainClaims.length > 0 ? mainClaims[0] : found.claims[0];
          const questions = [
            `What evidence would change your mind about: "${target.text.slice(0, 80)}..."?`,
            `How does this section's argument connect to what you already know about ${found.key_terms[0]?.term || 'this topic'}?`,
            `If you were explaining this section to someone, what would be the one key insight?`,
            `What's missing from this argument? What hasn't the author addressed?`,
          ];
          const idx = Math.abs(found.id.split('').reduce((a, c) => a + c.charCodeAt(0), 0)) % questions.length;
          setSocraticQuestion(questions[idx]);
        }

        // Restore scroll position
        if (sState.scroll_position_y > 0) {
          setTimeout(() => {
            scrollRef.current?.scrollTo({ y: sState.scroll_position_y, animated: false });
          }, 300);
        }
      }
    })();

    return () => { cancelled = true; };
  }, [bookId, sectionId]);

  // --- Cleanup: save time and scroll on unmount ---
  useEffect(() => {
    return () => {
      if (!bookId || !sectionId) return;
      const elapsed = Date.now() - enterTime.current;
      addBookTimeSpent(bookId, elapsed);

      const currentState = getSectionReadingState(bookId, sectionId);
      updateSectionReadingState(bookId, sectionId, {
        time_spent_ms: (currentState.time_spent_ms || 0) + elapsed,
        last_read_at: Date.now(),
        scroll_position_y: lastScrollY.current,
      });

      logEvent('book_reader_close', {
        book_id: bookId,
        section_id: sectionId,
        time_spent_ms: elapsed,
        final_zone: currentZoneRef.current,
      });
    };
  }, [bookId, sectionId]);

  // --- Zone tracking via scroll ---
  const updateDepthZone = useCallback((scrollY: number) => {
    if (!section || !bookId) return;
    const positions = zonePositions.current;
    let zone: DepthZone = 'briefing';
    for (const z of DEPTH_ZONES) {
      if (positions[z] > 0 && scrollY >= positions[z] - 80) {
        zone = z;
      }
    }
    if (zone !== currentZoneRef.current) {
      const prevZone = currentZoneRef.current;
      logEvent('book_reader_zone_change', {
        book_id: bookId,
        section_id: section.id,
        from: prevZone,
        to: zone,
      });
      currentZoneRef.current = zone;
      setCurrentZone(zone);

      // Advance depth (never go backwards)
      const depthMap: Record<DepthZone, BookReadingDepth> = {
        briefing: 'briefing',
        claims: 'claims',
        terms: 'claims',
        full: 'reading',
      };
      const currentDepthIdx = DEPTH_ZONES.indexOf(zone);
      const savedState = getSectionReadingState(bookId, section.id);
      const savedDepthIdx = DEPTH_ZONES.indexOf(
        savedState.depth === 'reading' ? 'full' :
        savedState.depth === 'reflected' ? 'full' :
        savedState.depth === 'unread' ? 'briefing' :
        savedState.depth as DepthZone
      );
      if (currentDepthIdx > savedDepthIdx || savedState.depth === 'unread') {
        updateSectionReadingState(bookId, section.id, {
          depth: depthMap[zone],
          last_read_at: Date.now(),
        });
      }
    }
  }, [section, bookId]);

  // --- Scroll handler ---
  const handleScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const scrollY = event.nativeEvent.contentOffset.y;
    const now = Date.now();

    updateDepthZone(scrollY);

    // Throttled scroll position save
    if (now - lastPositionSaveTime.current >= SCROLL_POSITION_SAVE_INTERVAL_MS) {
      lastPositionSaveTime.current = now;
      if (bookId && sectionId) {
        updateSectionReadingState(bookId, sectionId, { scroll_position_y: Math.round(scrollY) });
      }
    }

    lastScrollY.current = scrollY;
  }, [bookId, sectionId, updateDepthZone]);

  // --- Zone layout tracking ---
  const onZoneLayout = useCallback((zone: DepthZone) => (event: LayoutChangeEvent) => {
    zonePositions.current[zone] = event.nativeEvent.layout.y;
  }, []);

  // --- Claim signal handler ---
  const handleClaimSignal = useCallback((claimId: string, signal: ClaimSignalType, claimText: string) => {
    if (!bookId || !sectionId) return;
    setClaimSignals(prev => ({ ...prev, [claimId]: signal }));
    recordBookClaimSignal(bookId, sectionId, claimId, signal);
    processClaimSignalForConcepts(bookId, claimText, signal);
    logEvent('book_claim_signal', {
      book_id: bookId,
      section_id: sectionId,
      claim_id: claimId,
      signal,
    });
  }, [bookId, sectionId]);

  // --- Highlight handler ---
  const handleBlockLongPress = useCallback((blockIndex: number, text: string) => {
    if (!sectionId) return;
    const indices = getHighlightBlockIndices(sectionId);
    if (indices.has(blockIndex)) {
      removeHighlight(sectionId, blockIndex);
      setHighlightedBlocks(prev => {
        const next = new Set(prev);
        next.delete(blockIndex);
        return next;
      });
    } else {
      addHighlight({
        id: `hl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        article_id: sectionId,
        block_index: blockIndex,
        text: text.slice(0, 500),
        highlighted_at: Date.now(),
        zone: 'full',
      });
      setHighlightedBlocks(prev => new Set(prev).add(blockIndex));
      setHighlightAction({ blockIndex, text: text.slice(0, 500) });
      setTimeout(() => setHighlightAction(null), 4000);
    }
  }, [sectionId]);

  // --- Navigation helpers ---
  const getAdjacentSection = useCallback((direction: 'prev' | 'next'): { bookId: string; sectionId: string } | null => {
    if (!book || !parsed) return null;

    let targetChapter = parsed.chapterNum;
    let targetSection = parsed.sectionNum + (direction === 'next' ? 1 : -1);

    const currentChapterMeta = book.chapters.find(ch => ch.chapter_number === targetChapter);
    if (!currentChapterMeta) return null;

    // Check if section exists in current chapter
    if (targetSection >= 1 && targetSection <= currentChapterMeta.section_count) {
      return {
        bookId: book.id,
        sectionId: `${book.id}:ch${targetChapter}:s${targetSection}`,
      };
    }

    // Move to adjacent chapter
    if (direction === 'next') {
      const nextChapter = book.chapters.find(ch => ch.chapter_number === targetChapter + 1);
      if (nextChapter) {
        return {
          bookId: book.id,
          sectionId: `${book.id}:ch${nextChapter.chapter_number}:s1`,
        };
      }
    } else {
      const prevChapter = book.chapters.find(ch => ch.chapter_number === targetChapter - 1);
      if (prevChapter) {
        return {
          bookId: book.id,
          sectionId: `${book.id}:ch${prevChapter.chapter_number}:s${prevChapter.section_count}`,
        };
      }
    }

    return null;
  }, [book, parsed]);

  const navigateToSection = useCallback((target: { bookId: string; sectionId: string }) => {
    logEvent('book_reader_navigate', {
      book_id: target.bookId,
      target_section: target.sectionId,
      from_section: sectionId,
    });
    router.replace({
      pathname: '/book-reader',
      params: { bookId: target.bookId, sectionId: target.sectionId },
    });
  }, [router, sectionId]);

  // --- Reflection submit ---
  const handleReflectionSubmit = useCallback(() => {
    if (!bookId || !sectionId || !reflectionText.trim()) return;
    addPersonalThreadEntry(bookId, {
      book_id: bookId,
      section_id: sectionId,
      type: 'reflection',
      text: reflectionText.trim(),
    });
    updateSectionReadingState(bookId, sectionId, { depth: 'reflected' });
    setReflectionSubmitted(true);
    logEvent('book_reflection_submitted', {
      book_id: bookId,
      section_id: sectionId,
      text_length: reflectionText.trim().length,
    });
  }, [bookId, sectionId, reflectionText]);

  const handleNextSection = useCallback(() => {
    if (!bookId || !sectionId) return;
    updateSectionReadingState(bookId, sectionId, { depth: 'reflected' });
    const next = getAdjacentSection('next');
    if (next) {
      navigateToSection(next);
    } else {
      router.back();
    }
  }, [bookId, sectionId, getAdjacentSection, navigateToSection, router]);

  // --- Compute navigation info ---
  const prevSection = getAdjacentSection('prev');
  const nextSection = getAdjacentSection('next');
  const progress = book ? getBookProgress(book.id) : null;

  // Total sections across book up to current
  let currentSectionGlobal = 0;
  let totalSections = 0;
  if (book && parsed) {
    for (const ch of book.chapters) {
      totalSections += ch.section_count;
      if (ch.chapter_number < parsed.chapterNum) {
        currentSectionGlobal += ch.section_count;
      } else if (ch.chapter_number === parsed.chapterNum) {
        currentSectionGlobal += parsed.sectionNum;
      }
    }
  }

  // Current chapter section count
  const currentChapterMeta = book?.chapters.find(ch => ch.chapter_number === parsed?.chapterNum);
  const chapterSectionCount = currentChapterMeta?.section_count || 0;

  // Chapter transition detection: is this the first section of a new chapter (not ch1)?
  const isChapterStart = parsed && parsed.sectionNum === 1 && parsed.chapterNum > 1;
  const previousChapterArg = isChapterStart && book
    ? book.running_argument[parsed.chapterNum - 2] // -2 because 0-indexed and we want the PREVIOUS chapter
    : null;
  const previousChapterMeta = isChapterStart && book
    ? book.chapters.find(ch => ch.chapter_number === parsed.chapterNum - 1)
    : null;

  // Personal thread from earlier sections (for briefing enrichment)
  const earlierThreadNotes = (() => {
    if (!bookId || !sectionId) return [];
    const thread = getPersonalThread(bookId);
    return thread
      .filter(e => e.section_id !== sectionId && e.text.length > 0)
      .slice(-3);
  })();

  // Concept familiarity analysis for "What you bring"
  const familiarityAnalysis = (() => {
    if (!section) return { familiar: [] as { text: string; topic: string }[], novel: 0, total: 0 };
    const allConcepts = getConcepts();
    const sectionTerms = [
      ...section.key_terms.map(t => t.term.toLowerCase()),
      ...section.claims.map(c => c.text.toLowerCase().split(' ').filter(w => w.length > 5)),
    ].flat();
    const matched: { text: string; topic: string; known: boolean }[] = [];
    const seen = new Set<string>();
    for (const concept of allConcepts) {
      const ct = concept.text.toLowerCase();
      if (seen.has(ct)) continue;
      const relevant = sectionTerms.some(t => ct.includes(t) || t.includes(ct));
      if (relevant) {
        seen.add(ct);
        const cs = getConceptState(concept.id);
        matched.push({ text: concept.text, topic: concept.topic, known: cs.state !== 'unknown' });
      }
    }
    return {
      familiar: matched.filter(m => m.known).slice(0, 4),
      novel: matched.filter(m => !m.known).length,
      total: matched.length,
    };
  })();

  // Session stats for reflection card
  const sessionClaimCount = Object.keys(claimSignals).length;

  // Is this the last section in the entire book?
  const isLastSection = (() => {
    if (!book || !parsed) return false;
    const lastChapter = book.chapters[book.chapters.length - 1];
    return parsed.chapterNum === lastChapter.chapter_number &&
      parsed.sectionNum === lastChapter.section_count;
  })();

  // Book completion stats (computed only for last section)
  const bookCompletionStats = isLastSection && bookId ? (() => {
    const bookState = getBookReadingState(bookId);
    const thread = getPersonalThread(bookId);
    const totalSignals = Object.values(bookState.section_states)
      .reduce((sum, ss) => sum + Object.keys(ss.claim_signals).length, 0);
    const totalTime = Math.round(bookState.total_time_spent_ms / 60000);
    const totalSections = Object.values(bookState.section_states).filter(s => s.depth !== 'unread').length;
    const reflections = thread.filter(e => e.type === 'reflection').length;
    const voiceNotes = thread.filter(e => e.type === 'voice_note').length;
    return { totalSignals, totalTime, totalSections, reflections, voiceNotes, thread };
  })() : null;

  // All chapter section states for mini-map
  const chapterSectionStates = (() => {
    if (!book || !parsed || !bookId) return [];
    return Array.from({ length: chapterSectionCount }, (_, i) => {
      const sid = `${book.id}:ch${parsed.chapterNum}:s${i + 1}`;
      const state = getSectionReadingState(bookId, sid);
      return { sectionNum: i + 1, depth: state.depth, isCurrent: i + 1 === parsed.sectionNum };
    });
  })();

  // --- Context restoration check ---
  const [welcomeBackDismissed, setWelcomeBackDismissed] = useState(false);
  const showWelcomeBack = (() => {
    if (welcomeBackDismissed || !book || !bookId) return false;
    const bookState = getBookReadingState(bookId);
    if (bookState.last_read_at === 0) return false;
    const daysSince = (Date.now() - bookState.last_read_at) / (24 * 60 * 60 * 1000);
    return daysSince >= 3;
  })();

  // --- Loading state ---
  if (loading) {
    return (
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Pressable onPress={() => router.back()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={22} color={colors.ink} />
          </Pressable>
          <Text style={styles.loadingText}>Loading section...</Text>
        </View>
      </View>
    );
  }

  // --- Error state ---
  if (!section || !book || !parsed) {
    return (
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Pressable onPress={() => router.back()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={22} color={colors.ink} />
          </Pressable>
        </View>
        <Text style={styles.errorText}>Section not found</Text>
        <Pressable onPress={() => router.back()}>
          <Text style={styles.backLink}>Back to library</Text>
        </Pressable>
      </View>
    );
  }

  // Gather context restoration data
  const welcomeBackData = (() => {
    if (!showWelcomeBack || !bookId) return null;
    const bookState = getBookReadingState(bookId);
    const daysSince = Math.floor((Date.now() - bookState.last_read_at) / (24 * 60 * 60 * 1000));
    const thread = getPersonalThread(bookId);
    const recentNotes = thread.slice(-3);
    const signalCount = Object.values(bookState.section_states)
      .reduce((sum, ss) => sum + Object.keys(ss.claim_signals).length, 0);
    const readSections = Object.values(bookState.section_states).filter(ss => ss.depth !== 'unread').length;

    // Running argument for chapters read so far
    const chaptersRead = new Set<number>();
    for (const [sid] of Object.entries(bookState.section_states)) {
      const p = parseSectionId(sid);
      if (p) chaptersRead.add(p.chapterNum);
    }
    const relevantArguments = book!.running_argument
      .slice(0, Math.max(...chaptersRead, 0))
      .slice(-2);

    return { daysSince, recentNotes, signalCount, readSections, relevantArguments };
  })();

  return (
    <View style={styles.container}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color={colors.ink} />
        </Pressable>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <Text style={styles.topBarTitle} numberOfLines={1}>{book.title}</Text>
          <Text style={styles.topBarSubtitle}>
            Ch {parsed.chapterNum}{currentChapterMeta ? `: ${currentChapterMeta.title}` : ''}
          </Text>
        </View>
        {Platform.OS === 'web' ? (
          <TextNoteInput
            sectionId={section.id}
            bookId={bookId}
            onNoteSubmitted={(text, noteId) => {
              addPersonalThreadEntry(bookId, {
                book_id: bookId,
                section_id: section.id,
                type: 'voice_note',
                text,
                voice_note_id: noteId,
              });
            }}
          />
        ) : (
          <VoiceRecordButton
            sectionId={section.id}
            bookId={bookId}
            onTranscribed={(transcript, noteId) => {
              addPersonalThreadEntry(bookId, {
                book_id: bookId,
                section_id: section.id,
                type: 'voice_note',
                text: transcript,
                voice_note_id: noteId,
              });
            }}
          />
        )}
        {progress && (
          <View style={styles.progressBadge}>
            <Text style={styles.progressBadgeText}>
              {'\u00A7'}{currentSectionGlobal} of {totalSections}
            </Text>
          </View>
        )}
      </View>

      {/* Floating depth indicator */}
      <FloatingDepthIndicator
        currentZone={currentZone}
        claimCount={section.claims.length}
        termCount={section.key_terms.length}
        claimsReviewed={Object.keys(claimSignals).length}
      />

      {/* Main scrollable content */}
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        scrollEventThrottle={16}
        onScroll={handleScroll}
      >
        {/* Welcome Back card — context restoration */}
        {showWelcomeBack && welcomeBackData && (
          <View style={welcomeStyles.card}>
            <View style={welcomeStyles.header}>
              <Ionicons name="time-outline" size={16} color={colors.warning} />
              <Text style={welcomeStyles.title}>Welcome back — {welcomeBackData.daysSince} days since last visit</Text>
            </View>

            <Text style={welcomeStyles.subtitle}>
              {welcomeBackData.readSections} sections read · {welcomeBackData.signalCount} claims signaled
            </Text>

            {welcomeBackData.relevantArguments.length > 0 && (
              <View style={welcomeStyles.argumentBox}>
                <Text style={welcomeStyles.argumentLabel}>The argument so far:</Text>
                {welcomeBackData.relevantArguments.map((arg, i) => (
                  <Text key={i} style={welcomeStyles.argumentText}>{arg}</Text>
                ))}
              </View>
            )}

            {welcomeBackData.recentNotes.length > 0 && (
              <View style={{ marginTop: 8 }}>
                <Text style={welcomeStyles.notesLabel}>Your recent notes:</Text>
                {welcomeBackData.recentNotes.map(note => (
                  <Text key={note.id} style={welcomeStyles.noteText} numberOfLines={2}>
                    "{note.text}"
                  </Text>
                ))}
              </View>
            )}

            <Pressable
              style={welcomeStyles.dismissBtn}
              onPress={() => {
                logEvent('welcome_back_dismissed', { book_id: bookId, days_since: welcomeBackData.daysSince });
                setWelcomeBackDismissed(true);
              }}
            >
              <Text style={welcomeStyles.dismissText}>Resume reading</Text>
              <Ionicons name="arrow-forward" size={14} color={colors.warning} />
            </Pressable>
          </View>
        )}

        {/* Chapter transition card — shown at start of new chapter */}
        {isChapterStart && previousChapterMeta && (
          <View style={chapterTransitionStyles.card}>
            <View style={chapterTransitionStyles.header}>
              <Ionicons name="flag-outline" size={16} color={colors.success} />
              <Text style={chapterTransitionStyles.headerText}>
                Chapter {previousChapterMeta.chapter_number} Complete
              </Text>
            </View>
            <Text style={chapterTransitionStyles.chapterTitle}>
              {previousChapterMeta.title}
            </Text>
            {previousChapterArg && (
              <View style={chapterTransitionStyles.argumentBox}>
                <Text style={chapterTransitionStyles.argumentLabel}>The argument:</Text>
                <Text style={chapterTransitionStyles.argumentText}>{previousChapterArg}</Text>
              </View>
            )}
            <View style={chapterTransitionStyles.newChapterBadge}>
              <Text style={chapterTransitionStyles.newChapterText}>
                Now entering: Ch {parsed!.chapterNum}{currentChapterMeta ? ` — ${currentChapterMeta.title}` : ''}
              </Text>
            </View>
          </View>
        )}

        {/* Section title */}
        <Text style={styles.sectionTitle}>{section.title}</Text>
        <View style={styles.sectionMeta}>
          <Text style={styles.metaText}>
            {section.estimated_read_minutes} min read
          </Text>
          <Text style={styles.metaText}>
            {section.word_count} words
          </Text>
        </View>

        {/* Adaptive depth suggestion */}
        {adaptiveDepthSuggestion && adaptiveDepthSuggestion.zone !== 'briefing' && (
          <Pressable
            style={styles.adaptiveDepthBanner}
            onPress={() => {
              const targetY = zonePositions.current[adaptiveDepthSuggestion.zone];
              if (targetY > 0) {
                scrollRef.current?.scrollTo({ y: targetY - 60, animated: true });
              }
              setAdaptiveDepthSuggestion(null);
              logEvent('adaptive_depth_accepted', { zone: adaptiveDepthSuggestion.zone });
            }}
          >
            <Ionicons name="flash-outline" size={16} color={'#7a5195'} />
            <View style={{ flex: 1 }}>
              <Text style={styles.adaptiveDepthText}>
                Skip to {DEPTH_LABELS[adaptiveDepthSuggestion.zone]}
              </Text>
              <Text style={styles.adaptiveDepthReason}>{adaptiveDepthSuggestion.reason}</Text>
            </View>
            <Pressable
              onPress={(e) => {
                e.stopPropagation();
                setAdaptiveDepthSuggestion(null);
                logEvent('adaptive_depth_dismissed', {});
              }}
              hitSlop={8}
            >
              <Ionicons name="close" size={16} color={colors.textMuted} />
            </Pressable>
          </Pressable>
        )}

        {/* ====== ZONE 1: BRIEFING ====== */}
        <View onLayout={onZoneLayout('briefing')}>
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <View style={styles.dividerLabelRow}>
              <Ionicons name="compass-outline" size={14} color={colors.info} />
              <Text style={styles.dividerText}>Briefing</Text>
            </View>
            <View style={styles.dividerLine} />
          </View>

          {/* Summary card */}
          <View style={styles.briefingCard}>
            <Text style={styles.briefingText}>{section.summary}</Text>
          </View>

          {/* Briefing / argument context */}
          {section.briefing ? (
            <View style={styles.argumentCard}>
              <Text style={styles.argumentLabel}>Where this fits</Text>
              <Text style={styles.argumentText}>{section.briefing}</Text>
            </View>
          ) : null}

          {/* What you bring — concept familiarity */}
          {familiarityAnalysis.familiar.length > 0 && (
            <View style={styles.familiarityCard}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Ionicons name="library-outline" size={14} color={colors.success} />
                <Text style={styles.familiarityTitle}>What you bring</Text>
              </View>
              <View style={styles.familiarityChips}>
                {familiarityAnalysis.familiar.map((c, i) => (
                  <View key={i} style={styles.familiarityChip}>
                    <Ionicons name="checkmark" size={10} color={colors.success} />
                    <Text style={styles.familiarityChipText}>{c.text}</Text>
                  </View>
                ))}
              </View>
              {familiarityAnalysis.novel > 0 && (
                <Text style={styles.familiarityNovel}>
                  + {familiarityAnalysis.novel} new concept{familiarityAnalysis.novel !== 1 ? 's' : ''} to discover
                </Text>
              )}
            </View>
          )}

          {/* Personal thread — notes from earlier sections */}
          {earlierThreadNotes.length > 0 && (
            <View style={styles.threadBriefingCard}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name="journal-outline" size={14} color={'#7a5195'} />
                <Text style={styles.threadBriefingTitle}>Your earlier thoughts</Text>
              </View>
              {earlierThreadNotes.map(note => (
                <Text key={note.id} style={styles.threadBriefingNote} numberOfLines={2}>
                  "{note.text}"
                </Text>
              ))}
            </View>
          )}

          {/* Cross-book connections */}
          {section.cross_book_connections.length > 0 && (
            <View style={{ marginTop: 12 }}>
              {section.cross_book_connections.map((conn, i) => (
                <CrossBookConnectionCard key={i} connection={conn} />
              ))}
            </View>
          )}
        </View>

        {/* ====== ZONE 2: CLAIMS ====== */}
        <View onLayout={onZoneLayout('claims')}>
          {section.claims.length > 0 && (
            <>
              <View style={styles.divider}>
                <View style={styles.dividerLine} />
                <View style={styles.dividerLabelRow}>
                  <Ionicons name="bulb-outline" size={14} color={'#7a5195'} />
                  <Text style={styles.dividerText}>Claims</Text>
                </View>
                <View style={styles.dividerLine} />
              </View>

              {/* Claims header with skeleton toggle */}
              <View style={styles.claimsHeaderRow}>
                <Text style={styles.claimsProgress}>
                  {Object.keys(claimSignals).length} of {section.claims.length} claims reviewed
                </Text>
                {section.claims.some(c => c.supports_claim) && (
                  <Pressable
                    style={[styles.skeletonToggle, showSkeletonView && styles.skeletonToggleActive]}
                    onPress={() => {
                      setShowSkeletonView(!showSkeletonView);
                      logEvent('skeleton_view_toggle', { enabled: !showSkeletonView, section_id: sectionId });
                    }}
                  >
                    <Ionicons name="git-branch-outline" size={14} color={showSkeletonView ? colors.ink : colors.textMuted} />
                    <Text style={[styles.skeletonToggleText, showSkeletonView && { color: colors.ink }]}>
                      Skeleton
                    </Text>
                  </Pressable>
                )}
              </View>

              {/* Skeleton view: tree structure grouping main + supporting claims */}
              {showSkeletonView ? (
                <View>
                  {section.claims.filter(c => c.is_main).map((mainClaim) => {
                    const signal = claimSignals[mainClaim.claim_id];
                    const supports = section.claims.filter(c => c.supports_claim === mainClaim.claim_id);
                    return (
                      <View key={mainClaim.claim_id} style={{ marginBottom: 16 }}>
                        {/* Main claim */}
                        <View style={[
                          styles.claimCard, styles.claimCardMain,
                          signal === 'knew_it' && styles.claimCardKnew,
                          signal === 'interesting' && styles.claimCardNew,
                          signal === 'save' && styles.claimCardSave,
                          { marginBottom: supports.length > 0 ? 0 : 10, borderBottomLeftRadius: supports.length > 0 ? 0 : 12, borderBottomRightRadius: supports.length > 0 ? 0 : 12 },
                        ]}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                            <Ionicons name="diamond-outline" size={12} color={'#7a5195'} />
                            <Text style={{ color: '#7a5195', fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>Main Claim</Text>
                          </View>
                          <Text style={styles.claimCardText}>{mainClaim.text}</Text>
                          <View style={styles.claimActions}>
                            <Pressable style={[styles.claimBtn, signal === 'knew_it' && styles.claimBtnActiveKnew]} onPress={() => handleClaimSignal(mainClaim.claim_id, 'knew_it', mainClaim.text)}>
                              <Text style={[styles.claimBtnText, signal === 'knew_it' && { color: colors.textMuted }]}>Knew this</Text>
                            </Pressable>
                            <Pressable style={[styles.claimBtn, styles.claimBtnNewBorder, signal === 'interesting' && styles.claimBtnActiveNew]} onPress={() => handleClaimSignal(mainClaim.claim_id, 'interesting', mainClaim.text)}>
                              <Text style={[styles.claimBtnText, { color: colors.success }, signal === 'interesting' && { color: colors.parchment }]}>New to me</Text>
                            </Pressable>
                          </View>
                        </View>
                        {/* Supporting claims */}
                        {supports.map((sub) => {
                          const subSignal = claimSignals[sub.claim_id];
                          return (
                            <View key={sub.claim_id} style={[
                              styles.claimCard,
                              { marginLeft: 20, borderTopLeftRadius: 0, borderTopRightRadius: 0, borderLeftColor: colors.rule, borderLeftWidth: 2, marginBottom: 0, marginTop: 0, paddingTop: 10, paddingBottom: 10 },
                              subSignal === 'knew_it' && { opacity: 0.6 },
                              subSignal === 'interesting' && { borderLeftColor: colors.success },
                            ]}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                                <Ionicons name="return-down-forward-outline" size={12} color={colors.textMuted} />
                                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>Evidence</Text>
                              </View>
                              <Text style={[styles.claimCardText, { fontSize: 14 }]}>{sub.text}</Text>
                              {sub.source_passage && (
                                <View style={styles.claimSourcePassage}>
                                  <Text style={styles.claimSourceText}>"{sub.source_passage}"</Text>
                                </View>
                              )}
                              <View style={styles.claimActions}>
                                <Pressable style={[styles.claimBtn, subSignal === 'knew_it' && styles.claimBtnActiveKnew]} onPress={() => handleClaimSignal(sub.claim_id, 'knew_it', sub.text)}>
                                  <Text style={[styles.claimBtnText, subSignal === 'knew_it' && { color: colors.textMuted }]}>Knew</Text>
                                </Pressable>
                                <Pressable style={[styles.claimBtn, styles.claimBtnNewBorder, subSignal === 'interesting' && styles.claimBtnActiveNew]} onPress={() => handleClaimSignal(sub.claim_id, 'interesting', sub.text)}>
                                  <Text style={[styles.claimBtnText, { color: colors.success }, subSignal === 'interesting' && { color: colors.parchment }]}>New</Text>
                                </Pressable>
                              </View>
                            </View>
                          );
                        })}
                      </View>
                    );
                  })}
                </View>
              ) : (
              <View>
              {/* Flat view: original claim cards */}
              {section.claims.map((claim) => {
                const signal = claimSignals[claim.claim_id];
                return (
                  <View key={claim.claim_id} style={[
                    styles.claimCard,
                    claim.is_main && styles.claimCardMain,
                    signal === 'knew_it' && styles.claimCardKnew,
                    signal === 'interesting' && styles.claimCardNew,
                    signal === 'save' && styles.claimCardSave,
                  ]}>
                    <Text style={styles.claimCardText}>{claim.text}</Text>

                    {claim.source_passage && (
                      <View style={styles.claimSourcePassage}>
                        <Text style={styles.claimSourceText}>"{claim.source_passage}"</Text>
                      </View>
                    )}

                    {claim.confidence >= 0.8 && (
                      <View style={styles.confidenceBadge}>
                        <Text style={styles.confidenceText}>High confidence</Text>
                      </View>
                    )}

                    <View style={styles.claimActions}>
                      <Pressable
                        style={[styles.claimBtn, signal === 'knew_it' && styles.claimBtnActiveKnew]}
                        onPress={() => handleClaimSignal(claim.claim_id, 'knew_it', claim.text)}
                      >
                        <Text style={[styles.claimBtnText, signal === 'knew_it' && { color: colors.textMuted }]}>Knew this</Text>
                      </Pressable>
                      <Pressable
                        style={[styles.claimBtn, styles.claimBtnNewBorder, signal === 'interesting' && styles.claimBtnActiveNew]}
                        onPress={() => handleClaimSignal(claim.claim_id, 'interesting', claim.text)}
                      >
                        <Text style={[styles.claimBtnText, { color: colors.success }, signal === 'interesting' && { color: colors.parchment }]}>New to me</Text>
                      </Pressable>
                      <Pressable
                        style={[styles.claimBtn, styles.claimBtnSaveBorder, signal === 'save' && styles.claimBtnActiveSave]}
                        onPress={() => handleClaimSignal(claim.claim_id, 'save', claim.text)}
                      >
                        <Text style={[styles.claimBtnText, { color: colors.info }, signal === 'save' && { color: colors.parchment }]}>Save</Text>
                      </Pressable>
                    </View>
                  </View>
                );
              })}
              </View>
              )}
            </>
          )}
        </View>

        {/* ====== ZONE 3: KEY TERMS ====== */}
        <View onLayout={onZoneLayout('terms')}>
          {section.key_terms.length > 0 && (
            <>
              <View style={styles.divider}>
                <View style={styles.dividerLine} />
                <View style={styles.dividerLabelRow}>
                  <Ionicons name="book-outline" size={14} color={colors.warning} />
                  <Text style={styles.dividerText}>Key Terms</Text>
                </View>
                <View style={styles.dividerLine} />
              </View>

              {section.key_terms.map((term, i) => {
                const matchingConcepts = getConcepts().filter(c =>
                  c.text.toLowerCase().includes(term.term.toLowerCase()) ||
                  term.term.toLowerCase().includes(c.text.toLowerCase())
                );
                const knownConcept = matchingConcepts.find(c => {
                  const cs = getConceptState(c.id);
                  return cs.state === 'known' || cs.state === 'encountered';
                });
                return (
                  <View key={i} style={[styles.termCard, knownConcept && styles.termCardFamiliar]}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={styles.termName}>{term.term}</Text>
                      {knownConcept && (
                        <View style={styles.termFamiliarBadge}>
                          <Ionicons name="checkmark-circle" size={12} color={colors.success} />
                          <Text style={styles.termFamiliarText}>Familiar</Text>
                        </View>
                      )}
                    </View>
                    <Text style={styles.termDefinition}>{term.definition}</Text>
                    {term.conflicts_with && (
                      <View style={styles.termConflict}>
                        <Ionicons name="warning-outline" size={14} color={colors.warning} />
                        <Text style={styles.termConflictText}>
                          Different usage in {term.conflicts_with}
                        </Text>
                      </View>
                    )}
                    {matchingConcepts.length > 0 && (
                      <Text style={styles.termConceptCount}>
                        Appears in {matchingConcepts[0].source_article_ids.length} article{matchingConcepts[0].source_article_ids.length !== 1 ? 's' : ''}
                      </Text>
                    )}
                  </View>
                );
              })}
            </>
          )}
        </View>

        {/* ====== ZONE 4: FULL TEXT ====== */}
        <View onLayout={onZoneLayout('full')}>
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <View style={styles.dividerLabelRow}>
              <Ionicons name="document-text-outline" size={14} color={colors.success} />
              <Text style={styles.dividerText}>Full Text</Text>
            </View>
            <View style={styles.dividerLine} />
          </View>

          <MarkdownText
            content={section.content_markdown}
            highlightedBlocks={highlightedBlocks}
            onBlockLongPress={handleBlockLongPress}
          />
        </View>

        {/* ====== REFLECTION CARD ====== */}
        <View style={styles.reflectionCard}>
          <View style={styles.reflectionHeader}>
            <Ionicons name="sparkles-outline" size={18} color={'#7a5195'} />
            <Text style={styles.reflectionTitle}>Section Complete</Text>
          </View>

          {/* Session stats */}
          <View style={styles.sessionStatsRow}>
            {sessionClaimCount > 0 && (
              <View style={styles.sessionStat}>
                <Ionicons name="bulb-outline" size={14} color={'#7a5195'} />
                <Text style={styles.sessionStatText}>{sessionClaimCount} claims reviewed</Text>
              </View>
            )}
            {highlightedBlocks.size > 0 && (
              <View style={styles.sessionStat}>
                <Ionicons name="brush-outline" size={14} color={colors.warning} />
                <Text style={styles.sessionStatText}>{highlightedBlocks.size} highlighted</Text>
              </View>
            )}
          </View>

          <Text style={styles.reflectionTakeaway}>
            {section.summary.split('.')[0]}.
          </Text>

          {/* Socratic prompt */}
          {socraticQuestion && !reflectionSubmitted && (
            <View style={styles.socraticCard}>
              <Ionicons name="help-circle-outline" size={16} color={colors.warning} />
              <Text style={styles.socraticText}>{socraticQuestion}</Text>
            </View>
          )}

          {!reflectionSubmitted ? (
            <View style={styles.reflectionInputArea}>
              <TextInput
                style={styles.reflectionInput}
                placeholder="Your reflection on this section..."
                placeholderTextColor={colors.textMuted}
                multiline
                value={reflectionText}
                onChangeText={setReflectionText}
              />
              <View style={styles.reflectionActions}>
                <Pressable
                  style={[styles.reflectionSubmitBtn, !reflectionText.trim() && { opacity: 0.4 }]}
                  onPress={handleReflectionSubmit}
                  disabled={!reflectionText.trim()}
                >
                  <Ionicons name="send" size={14} color={colors.ink} />
                  <Text style={styles.reflectionSubmitText}>Save reflection</Text>
                </Pressable>
              </View>
            </View>
          ) : (
            <View style={styles.reflectionDone}>
              <Ionicons name="checkmark-circle" size={16} color={colors.success} />
              <Text style={styles.reflectionDoneText}>Reflection saved</Text>
            </View>
          )}

          {!isLastSection && (
            <Pressable style={styles.nextSectionBtn} onPress={handleNextSection}>
              <Text style={styles.nextSectionText}>Next section</Text>
              <Ionicons name="arrow-forward" size={16} color={colors.ink} />
            </Pressable>
          )}
        </View>

        {/* ====== BOOK COMPLETION CARD (last section only) ====== */}
        {isLastSection && bookCompletionStats && book && (
          <View style={completionStyles.card}>
            <View style={completionStyles.header}>
              <Ionicons name="trophy-outline" size={24} color={colors.warning} />
              <Text style={completionStyles.title}>Book Complete</Text>
            </View>
            <Text style={completionStyles.bookTitle}>{book.title}</Text>
            <Text style={completionStyles.bookAuthor}>by {book.author}</Text>

            {/* Stats grid */}
            <View style={completionStyles.statsGrid}>
              <View style={completionStyles.statBox}>
                <Text style={completionStyles.statNumber}>{bookCompletionStats.totalSections}</Text>
                <Text style={completionStyles.statLabel}>sections</Text>
              </View>
              <View style={completionStyles.statBox}>
                <Text style={completionStyles.statNumber}>{bookCompletionStats.totalTime}</Text>
                <Text style={completionStyles.statLabel}>minutes</Text>
              </View>
              <View style={completionStyles.statBox}>
                <Text style={completionStyles.statNumber}>{bookCompletionStats.totalSignals}</Text>
                <Text style={completionStyles.statLabel}>claims</Text>
              </View>
              <View style={completionStyles.statBox}>
                <Text style={completionStyles.statNumber}>{bookCompletionStats.reflections + bookCompletionStats.voiceNotes}</Text>
                <Text style={completionStyles.statLabel}>notes</Text>
              </View>
            </View>

            {/* Running argument summary */}
            {book.running_argument.length > 0 && (
              <View style={completionStyles.argumentSection}>
                <Text style={completionStyles.argumentTitle}>The Full Argument</Text>
                {book.running_argument.map((arg, i) => (
                  <View key={i} style={completionStyles.argumentRow}>
                    <Text style={completionStyles.argumentChNum}>Ch {i + 1}</Text>
                    <Text style={completionStyles.argumentText}>{arg}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* Personal thread highlights */}
            {bookCompletionStats.thread.length > 0 && (
              <View style={completionStyles.threadSection}>
                <Text style={completionStyles.threadTitle}>Your Journey</Text>
                {bookCompletionStats.thread.slice(-5).map(entry => (
                  <View key={entry.id} style={completionStyles.threadItem}>
                    <Ionicons
                      name={entry.type === 'reflection' ? 'sparkles-outline' :
                            entry.type === 'voice_note' ? 'mic-outline' :
                            entry.type === 'connection' ? 'link-outline' : 'chatbubble-outline'}
                      size={12}
                      color={'#7a5195'}
                    />
                    <Text style={completionStyles.threadText} numberOfLines={2}>{entry.text}</Text>
                  </View>
                ))}
              </View>
            )}

            <Pressable
              style={completionStyles.doneBtn}
              onPress={() => {
                logEvent('book_completed', {
                  book_id: bookId,
                  total_sections: bookCompletionStats.totalSections,
                  total_time_min: bookCompletionStats.totalTime,
                  total_signals: bookCompletionStats.totalSignals,
                  total_notes: bookCompletionStats.reflections + bookCompletionStats.voiceNotes,
                });
                router.back();
              }}
            >
              <Ionicons name="library" size={18} color={colors.ink} />
              <Text style={completionStyles.doneBtnText}>Back to Library</Text>
            </Pressable>
          </View>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Floating claim signal pill */}
      {activeClaimPill !== null && (
        <ClaimSignalPill
          currentSignal={claimSignals[activeClaimPill]}
          onSignal={(signal) => {
            const claim = section.claims.find(c => c.claim_id === activeClaimPill);
            if (claim) handleClaimSignal(activeClaimPill, signal, claim.text);
            setActiveClaimPill(null);
          }}
          onDismiss={() => setActiveClaimPill(null)}
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
                  <Text style={{ color: colors.textMuted, fontSize: 13 }}>Cancel</Text>
                </Pressable>
                <Pressable
                  style={[styles.highlightNoteSaveBtn, !highlightNoteText.trim() && { opacity: 0.4 }]}
                  onPress={() => {
                    if (highlightNoteText.trim() && sectionId) {
                      updateHighlightNote(sectionId, highlightAction.blockIndex, highlightNoteText.trim());
                      logEvent('book_highlight_note_saved', {
                        book_id: bookId,
                        section_id: sectionId,
                        block_index: highlightAction.blockIndex,
                      });
                    }
                    setHighlightNoteMode(false);
                    setHighlightNoteText('');
                    setHighlightAction(null);
                  }}
                  disabled={!highlightNoteText.trim()}
                >
                  <Text style={{ color: colors.ink, fontSize: 13, fontWeight: '600' }}>Save</Text>
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
                <Ionicons name="create-outline" size={14} color={colors.info} />
                <Text style={styles.highlightNoteLabel}>Note</Text>
              </Pressable>
              <Pressable
                style={styles.highlightNoteBtn}
                onPress={() => {
                  const matchText = highlightAction.text.toLowerCase();
                  const concepts = getConcepts();
                  const matches = concepts.filter(c => {
                    const ct = c.text.toLowerCase();
                    return matchText.includes(ct) || ct.split(' ').some(w => w.length > 4 && matchText.includes(w));
                  }).slice(0, 3);
                  if (matches.length > 0) {
                    const info = matches.map(m => `${m.text} (${m.source_article_ids.length} articles)`).join(', ');
                    // Show as a temporary personal thread entry
                    if (bookId && sectionId) {
                      addPersonalThreadEntry(bookId, {
                        book_id: bookId,
                        section_id: sectionId,
                        type: 'connection',
                        text: `Found connections: ${info}`,
                      });
                    }
                  }
                  logEvent('highlight_find_connections', {
                    book_id: bookId,
                    section_id: sectionId,
                    matches: matches.length,
                    text_preview: highlightAction.text.slice(0, 60),
                  });
                  setHighlightAction(null);
                }}
              >
                <Ionicons name="link-outline" size={14} color={'#7a5195'} />
                <Text style={[styles.highlightNoteLabel, { color: '#7a5195' }]}>Connect</Text>
              </Pressable>
              <Pressable onPress={() => setHighlightAction(null)}>
                <Ionicons name="close" size={16} color={colors.textMuted} />
              </Pressable>
            </>
          )}
        </View>
      )}

      {/* Navigation footer with section mini-map */}
      <View style={styles.navFooter}>
        <Pressable
          style={[styles.navBtn, !prevSection && styles.navBtnDisabled]}
          onPress={() => prevSection && navigateToSection(prevSection)}
          disabled={!prevSection}
        >
          <Ionicons name="chevron-back" size={20} color={prevSection ? colors.ink : colors.rule} />
        </Pressable>
        <View style={styles.navCenter}>
          <Text style={styles.navChapterLabel}>Ch {parsed.chapterNum}</Text>
          <View style={styles.sectionMiniMap}>
            {chapterSectionStates.map((ss) => (
              <Pressable
                key={ss.sectionNum}
                style={[
                  styles.miniMapDot,
                  ss.isCurrent && styles.miniMapDotCurrent,
                  ss.depth === 'reflected' && styles.miniMapDotReflected,
                  ss.depth !== 'unread' && ss.depth !== 'reflected' && styles.miniMapDotRead,
                ]}
                onPress={() => {
                  if (!ss.isCurrent && book) {
                    const targetSid = `${book.id}:ch${parsed.chapterNum}:s${ss.sectionNum}`;
                    navigateToSection({ bookId: book.id, sectionId: targetSid });
                  }
                }}
              />
            ))}
          </View>
        </View>
        <Pressable
          style={[styles.navBtn, !nextSection && styles.navBtnDisabled]}
          onPress={() => nextSection && navigateToSection(nextSection)}
          disabled={!nextSection}
        >
          <Ionicons name="chevron-forward" size={20} color={nextSection ? colors.ink : colors.rule} />
        </Pressable>
      </View>
    </View>
  );
}

// ============================================================
// Welcome Back styles
// ============================================================

const welcomeStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  title: { color: colors.warning, fontSize: 14, fontWeight: '700' },
  subtitle: { color: colors.textMuted, fontSize: 13, marginBottom: 8 },
  argumentBox: {
    backgroundColor: colors.parchment,
    borderRadius: 8,
    padding: 10,
    marginTop: 4,
  },
  argumentLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '600', marginBottom: 4 },
  argumentText: { color: colors.textSecondary, fontSize: 13, lineHeight: 18, marginBottom: 4 },
  notesLabel: { color: '#7a5195', fontSize: 12, fontWeight: '600', marginBottom: 4 },
  noteText: { color: colors.textMuted, fontSize: 13, fontStyle: 'italic', marginBottom: 4 },
  dismissBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: 'rgba(146,96,14,0.08)',
  },
  dismissText: { color: colors.warning, fontSize: 14, fontWeight: '600' },
});

// ============================================================
// Book Completion styles
// ============================================================

const completionStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 16,
    padding: 24,
    marginTop: 24,
    borderWidth: 1,
    borderColor: 'rgba(146,96,14,0.15)',
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  title: { color: colors.warning, fontSize: 22, fontWeight: '700' },
  bookTitle: { color: colors.ink, fontSize: 18, fontWeight: '600', marginBottom: 2 },
  bookAuthor: { color: colors.textMuted, fontSize: 14, marginBottom: 16 },
  statsGrid: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 20,
  },
  statBox: {
    flex: 1,
    backgroundColor: colors.parchment,
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
  },
  statNumber: { color: colors.ink, fontSize: 20, fontWeight: '700' },
  statLabel: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  argumentSection: {
    backgroundColor: colors.parchment,
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
  },
  argumentTitle: { color: colors.info, fontSize: 14, fontWeight: '700', marginBottom: 10 },
  argumentRow: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  argumentChNum: { color: colors.textMuted, fontSize: 12, fontWeight: '700', width: 36 },
  argumentText: { color: colors.textSecondary, fontSize: 13, lineHeight: 18, flex: 1 },
  threadSection: {
    marginBottom: 16,
  },
  threadTitle: { color: '#7a5195', fontSize: 14, fontWeight: '700', marginBottom: 8 },
  threadItem: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginBottom: 6 },
  threadText: { color: colors.textMuted, fontSize: 13, lineHeight: 18, flex: 1, fontStyle: 'italic' },
  doneBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: colors.info,
    borderRadius: 12,
    paddingVertical: 14,
  },
  doneBtnText: { color: colors.ink, fontSize: 16, fontWeight: '600' },
});

// ============================================================
// Chapter Transition styles
// ============================================================

const chapterTransitionStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.parchmentDark,
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: 'rgba(42,122,74,0.15)',
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  headerText: { color: colors.success, fontSize: 13, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  chapterTitle: { color: colors.ink, fontSize: 16, fontWeight: '600', marginBottom: 8 },
  argumentBox: {
    backgroundColor: colors.parchment,
    borderRadius: 8,
    padding: 10,
    marginBottom: 10,
  },
  argumentLabel: { color: colors.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', marginBottom: 4 },
  argumentText: { color: colors.textSecondary, fontSize: 14, lineHeight: 20 },
  newChapterBadge: {
    backgroundColor: 'rgba(42,74,106,0.08)',
    borderRadius: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  newChapterText: { color: colors.info, fontSize: 13, fontWeight: '600' },
});

// ============================================================
// Styles
// ============================================================

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  topBar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'web' ? 12 : 56, paddingBottom: 8, gap: 8,
  },
  backButton: { padding: 4 },
  topBarTitle: { color: colors.ink, fontSize: 14, fontWeight: '600' },
  topBarSubtitle: { color: colors.textMuted, fontSize: 12 },
  scroll: { flex: 1, paddingHorizontal: Platform.OS === 'web' ? 40 : 20 },
  loadingText: { color: colors.textMuted, fontSize: 14, marginLeft: 12 },
  errorText: { color: colors.danger, fontSize: 16, textAlign: 'center', marginTop: 100 },
  backLink: { color: colors.info, fontSize: 14, textAlign: 'center', marginTop: 12 },

  // Section title
  sectionTitle: {
    color: colors.ink,
    fontSize: Platform.OS === 'web' ? 28 : 24,
    fontWeight: '700',
    lineHeight: Platform.OS === 'web' ? 38 : 32,
    marginBottom: 8,
    letterSpacing: -0.3,
    ...(Platform.OS === 'web' ? { fontFamily: fonts.reading } : {}),
  },
  sectionMeta: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  metaText: { color: colors.textMuted, fontSize: 13 },

  // Progress badge
  progressBadge: {
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: 10,
  },
  progressBadgeText: { color: colors.textMuted, fontSize: 11, fontWeight: '600' },

  // Floating depth indicator
  depthIndicator: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 8, paddingHorizontal: 16,
    backgroundColor: 'rgba(247,244,236,0.93)',
    ...(Platform.OS === 'web' ? { borderBottomWidth: 1, borderBottomColor: colors.parchmentDark } : {}),
  },
  depthIndicatorItem: { flexDirection: 'row', alignItems: 'center' },
  depthConnector: { width: 16, height: 2, backgroundColor: colors.rule, marginHorizontal: 6, borderRadius: 1 },
  depthConnectorReached: { backgroundColor: colors.rule },
  depthLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '500' },
  depthLabelActive: { color: colors.ink, fontWeight: '700' },
  depthLabelReached: { color: colors.textMuted },
  depthCount: { color: colors.textMuted, fontSize: 11, fontWeight: '400' as const },

  // Dividers
  divider: {
    flexDirection: 'row', alignItems: 'center',
    marginTop: 28, marginBottom: 20, gap: 12,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: colors.parchmentDark },
  dividerLabelRow: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 },
  dividerText: { color: colors.textMuted, fontSize: 13, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1 },

  // Briefing zone
  briefingCard: {
    backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 16,
    borderLeftWidth: 4, borderLeftColor: colors.info, marginBottom: 12,
  },
  briefingText: {
    color: colors.textBody,
    fontSize: Platform.OS === 'web' ? 17 : 16,
    lineHeight: Platform.OS === 'web' ? 28 : 26,
    ...(Platform.OS === 'web' ? { fontFamily: fonts.reading } : {}),
  },
  argumentCard: {
    backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 16, marginBottom: 12,
  },
  argumentLabel: {
    color: colors.textMuted, fontSize: 12, fontWeight: '600',
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8,
  },
  argumentText: {
    color: colors.textSecondary, fontSize: 15, lineHeight: 24,
  },

  // Cross-book connections
  connectionCard: {
    borderRadius: 10, padding: 12, marginBottom: 10,
    borderLeftWidth: 3,
  },
  connectionHeader: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6, marginBottom: 6,
  },
  connectionLabel: { color: '#7a5195', fontSize: 12, fontWeight: '600' as const },
  connectionQuote: {
    color: '#9a7bc0', fontSize: 14, lineHeight: 21,
    fontStyle: 'italic' as const, marginBottom: 8,
  },
  connectionSource: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6,
  },
  connectionSourceText: { color: colors.textMuted, fontSize: 12 },

  // Claims
  claimsProgress: {
    color: colors.textMuted, fontSize: 12, marginBottom: 12, textAlign: 'center',
  },
  claimCard: {
    backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 16,
    marginBottom: 10, borderLeftWidth: 3, borderLeftColor: colors.rule,
  },
  claimCardMain: { borderLeftWidth: 5 },
  claimCardKnew: { borderLeftColor: colors.textMuted, opacity: 0.7 },
  claimCardNew: { borderLeftColor: colors.success },
  claimCardSave: { borderLeftColor: colors.info },
  claimCardText: { color: colors.textBody, fontSize: 15, lineHeight: 23, marginBottom: 8 },
  claimSourcePassage: {
    borderLeftWidth: 2, borderLeftColor: colors.rule,
    paddingLeft: 12, marginBottom: 10, marginLeft: 4,
  },
  claimSourceText: {
    color: colors.textMuted, fontSize: 13, lineHeight: 20, fontStyle: 'italic' as const,
  },
  confidenceBadge: {
    alignSelf: 'flex-start' as const,
    backgroundColor: 'rgba(42,122,74,0.15)', paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: 6, marginBottom: 10,
  },
  confidenceText: { color: colors.success, fontSize: 11, fontWeight: '600' },
  claimActions: { flexDirection: 'row', gap: 8 },
  claimBtn: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 8, backgroundColor: colors.rule,
  },
  claimBtnNewBorder: { borderColor: colors.success, borderWidth: 1, backgroundColor: 'transparent' },
  claimBtnSaveBorder: { borderColor: colors.info, borderWidth: 1, backgroundColor: 'transparent' },
  claimBtnActiveKnew: { backgroundColor: colors.rule },
  claimBtnActiveNew: { backgroundColor: 'rgba(42,122,74,0.12)', borderColor: colors.success },
  claimBtnActiveSave: { backgroundColor: 'rgba(42,74,106,0.15)', borderColor: colors.info },
  claimBtnText: { color: colors.textMuted, fontSize: 12, fontWeight: '500' },

  // Key Terms
  termCard: {
    backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 16, marginBottom: 10,
  },
  termName: { color: colors.ink, fontSize: 16, fontWeight: '700', marginBottom: 6 },
  termDefinition: { color: colors.textSecondary, fontSize: 15, lineHeight: 23 },
  termConflict: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6,
    marginTop: 10, backgroundColor: 'rgba(146,96,14,0.08)', padding: 8, borderRadius: 6,
  },
  termConflictText: { color: colors.warning, fontSize: 12, flex: 1 },
  familiarityCard: {
    backgroundColor: 'rgba(42,122,74,0.06)',
    borderRadius: 12,
    padding: 14,
    marginHorizontal: 16,
    marginTop: 10,
    borderWidth: 1,
    borderColor: 'rgba(42,122,74,0.15)',
  },
  familiarityTitle: { color: colors.success, fontSize: 13, fontWeight: '700' as const },
  familiarityChips: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: 6,
  },
  familiarityChip: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    backgroundColor: 'rgba(42,122,74,0.08)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(42,122,74,0.12)',
  },
  familiarityChipText: { color: colors.success, fontSize: 12 },
  familiarityNovel: { color: colors.success, fontSize: 12, marginTop: 8, fontStyle: 'italic' as const },
  termCardFamiliar: { borderLeftColor: colors.success, borderLeftWidth: 3 },
  termFamiliarBadge: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 3,
    backgroundColor: 'rgba(42,122,74,0.08)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
  },
  termFamiliarText: { color: colors.success, fontSize: 10, fontWeight: '600' as const },
  termConceptCount: { color: colors.textMuted, fontSize: 11, marginTop: 6 },

  // Markdown rendering
  markdownHeading: {
    color: colors.ink, fontWeight: '700',
    marginTop: 20, marginBottom: 10, lineHeight: 28,
  },
  markdownText: {
    color: colors.textSecondary,
    fontSize: Platform.OS === 'web' ? 18 : 16,
    lineHeight: Platform.OS === 'web' ? 30 : 26,
    marginBottom: 14, letterSpacing: 0.15,
    ...(Platform.OS === 'web' ? { fontFamily: fonts.reading } : {}),
  },
  markdownList: { marginBottom: 14 },
  markdownListItem: { flexDirection: 'row', marginBottom: 6, paddingRight: 8 },
  markdownBullet: { color: colors.info, marginRight: 10, fontSize: 16 },
  markdownOrderedBullet: { color: colors.info, marginRight: 10, fontSize: 14, minWidth: 20 },
  codeBlock: { backgroundColor: colors.parchmentDark, borderRadius: 8, padding: 14, marginBottom: 14 },
  codeText: { color: colors.textMuted, fontSize: 13, fontFamily: 'monospace' },
  markdownLink: { color: colors.info, textDecorationLine: 'underline' as const },
  markdownBold: { color: colors.ink, fontWeight: '700' as const },
  markdownItalic: { color: colors.textSecondary, fontStyle: 'italic' as const },
  markdownInlineCode: { color: colors.textMuted, fontFamily: 'monospace', backgroundColor: colors.parchmentDark, paddingHorizontal: 4 },
  markdownBlockquote: {
    borderLeftWidth: 3, borderLeftColor: colors.rule,
    paddingLeft: 14, marginBottom: 14, marginLeft: 4,
  },
  markdownBlockquoteText: {
    color: colors.textMuted, fontSize: 15, lineHeight: 24, fontStyle: 'italic' as const,
  },
  markdownHr: { height: 1, backgroundColor: colors.rule, marginVertical: 20 },
  tableContainer: {
    marginBottom: 14, borderRadius: 8, overflow: 'hidden',
    borderWidth: 1, borderColor: colors.rule,
  },
  tableRow: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.parchmentDark },
  tableRowAlt: { backgroundColor: colors.parchment },
  tableCell: { flex: 1, paddingVertical: 8, paddingHorizontal: 10 },
  tableHeaderCell: { backgroundColor: colors.parchmentDark },
  tableHeaderText: { color: colors.ink, fontSize: 13, fontWeight: '600' },
  tableCellText: { color: colors.textSecondary, fontSize: 13, lineHeight: 18 },

  // Paragraph highlighting
  paragraphHighlight: {
    backgroundColor: 'rgba(146,96,14,0.08)',
    borderLeftWidth: 3, borderLeftColor: colors.warning,
    paddingLeft: 8, borderRadius: 4, marginLeft: -8,
  },

  // Reflection card
  reflectionCard: {
    backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 20,
    marginTop: 28, borderWidth: 1, borderColor: colors.rule,
  },
  reflectionHeader: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8, marginBottom: 12,
  },
  reflectionTitle: { color: colors.ink, fontSize: 18, fontWeight: '700' },
  reflectionTakeaway: {
    color: '#7a5195', fontSize: 15, lineHeight: 22,
    fontStyle: 'italic' as const, marginBottom: 16,
  },
  reflectionInputArea: { marginBottom: 16 },
  reflectionInput: {
    color: colors.ink, fontSize: 15, lineHeight: 22,
    minHeight: 60, textAlignVertical: 'top' as const,
    backgroundColor: colors.parchment, borderRadius: 8, padding: 12,
    borderWidth: 1, borderColor: colors.rule,
  },
  reflectionActions: {
    flexDirection: 'row' as const, justifyContent: 'flex-end' as const, marginTop: 8,
  },
  reflectionSubmitBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6,
    backgroundColor: colors.rubric, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
  },
  reflectionSubmitText: { color: colors.ink, fontSize: 13, fontWeight: '600' },
  reflectionDone: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6, marginBottom: 16,
  },
  reflectionDoneText: { color: colors.success, fontSize: 14, fontWeight: '500' },
  nextSectionBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const,
    gap: 8, backgroundColor: colors.info, paddingVertical: 12, borderRadius: 10,
  },
  nextSectionText: { color: colors.ink, fontSize: 15, fontWeight: '600' },

  // Floating signal pill
  pillBackdrop: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(42,36,32,0.35)', justifyContent: 'center', alignItems: 'center',
  },
  pillContainer: {
    flexDirection: 'row', backgroundColor: colors.parchmentDark,
    borderRadius: 16, padding: 6, gap: 4,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 12, elevation: 8,
  },
  pillBtn: {
    paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: 12, backgroundColor: colors.rule,
  },
  pillBtnNew: { backgroundColor: 'rgba(42,122,74,0.12)' },
  pillBtnSave: { backgroundColor: 'rgba(42,74,106,0.15)' },
  pillBtnText: { color: colors.textBody, fontSize: 13, fontWeight: '600' },

  // Highlight action bar
  highlightActionBar: {
    position: 'absolute', bottom: 72, left: 16, right: 16,
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 12, elevation: 8,
    borderWidth: 1, borderColor: colors.rule,
  },
  highlightActionText: { color: colors.warning, fontSize: 13, fontWeight: '600' as const, flex: 1 },
  highlightNoteBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
    backgroundColor: colors.parchmentDark, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
  },
  highlightNoteLabel: { color: colors.info, fontSize: 12, fontWeight: '500' as const },
  highlightNoteInput: { color: colors.ink, fontSize: 14, lineHeight: 20, minHeight: 36 },
  highlightNoteSaveBtn: {
    backgroundColor: colors.info, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8,
  },

  // Voice recording
  voiceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 16, backgroundColor: colors.parchmentDark,
  },
  voiceBtnRecording: { backgroundColor: 'rgba(139,37,0,0.15)' },
  voiceTimer: { color: colors.danger, fontSize: 12, fontWeight: '700' },
  voiceCount: { color: colors.textMuted, fontSize: 11 },

  // Text note input
  textNoteBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 16, backgroundColor: colors.parchmentDark,
  },
  textNoteBtnText: { color: colors.info, fontSize: 12, fontWeight: '500' as const },
  textNoteContainer: {
    position: 'absolute' as const, top: '100%' as any, right: 0,
    width: 300, backgroundColor: colors.parchmentDark, borderRadius: 12, padding: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 12, elevation: 8,
    borderWidth: 1, borderColor: colors.rule, zIndex: 100,
  },
  textNoteInput: {
    color: colors.ink, fontSize: 14, lineHeight: 20,
    minHeight: 60, textAlignVertical: 'top' as const, marginBottom: 8,
  },
  textNoteActions: {
    flexDirection: 'row' as const, justifyContent: 'flex-end' as const, gap: 8,
  },
  textNoteCancelBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  textNoteCancelText: { color: colors.textMuted, fontSize: 13 },
  textNoteSubmitBtn: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
    backgroundColor: colors.info, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
  },
  textNoteSubmitText: { color: colors.ink, fontSize: 13, fontWeight: '600' as const },

  // Navigation footer
  navFooter: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 12,
    backgroundColor: colors.parchment, borderTopWidth: 1, borderTopColor: colors.parchmentDark,
    paddingBottom: Platform.OS === 'web' ? 12 : 28,
  },
  navBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.parchmentDark, alignItems: 'center', justifyContent: 'center',
  },
  navBtnDisabled: { opacity: 0.3 },
  navLabel: { color: colors.textMuted, fontSize: 13, fontWeight: '500' },
  navCenter: { flex: 1, alignItems: 'center' as const },
  navChapterLabel: { color: colors.textMuted, fontSize: 11, fontWeight: '600', marginBottom: 4 },
  sectionMiniMap: { flexDirection: 'row' as const, gap: 6, alignItems: 'center' as const },
  miniMapDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: colors.rule,
  },
  miniMapDotCurrent: {
    width: 12, height: 12, borderRadius: 6,
    backgroundColor: colors.info,
    borderWidth: 2, borderColor: colors.info,
  },
  miniMapDotRead: { backgroundColor: colors.rule },
  miniMapDotReflected: { backgroundColor: colors.success },

  // Personal thread in briefing
  threadBriefingCard: {
    backgroundColor: 'rgba(122,81,149,0.08)',
    borderRadius: 10,
    padding: 12,
    marginTop: 8,
    borderLeftWidth: 3,
    borderLeftColor: '#7a5195',
  },
  threadBriefingTitle: { color: '#7a5195', fontSize: 13, fontWeight: '600' },
  threadBriefingNote: { color: colors.textMuted, fontSize: 13, fontStyle: 'italic' as const, marginTop: 4 },

  // Session stats in reflection
  sessionStatsRow: {
    flexDirection: 'row' as const, gap: 16, marginBottom: 12,
  },
  sessionStat: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4,
  },
  sessionStatText: { color: colors.textMuted, fontSize: 12 },
  claimsHeaderRow: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    marginBottom: 8,
  },
  skeletonToggle: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: colors.parchmentDark,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  skeletonToggleActive: {
    backgroundColor: 'rgba(122,81,149,0.15)',
    borderColor: '#7a5195',
  },
  skeletonToggleText: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '600' as const,
  },
  adaptiveDepthBanner: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 10,
    backgroundColor: 'rgba(122,81,149,0.08)',
    borderRadius: 12,
    padding: 12,
    marginHorizontal: 16,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: 'rgba(122,81,149,0.15)',
  },
  adaptiveDepthText: {
    color: '#9a7bc0',
    fontSize: 14,
    fontWeight: '600' as const,
  },
  adaptiveDepthReason: {
    color: '#7a5195',
    fontSize: 12,
    marginTop: 2,
  },
  socraticCard: {
    flexDirection: 'row' as const,
    alignItems: 'flex-start' as const,
    gap: 8,
    backgroundColor: 'rgba(146,96,14,0.06)',
    borderRadius: 10,
    padding: 12,
    marginBottom: 14,
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
  },
  socraticText: {
    color: colors.warning,
    fontSize: 14,
    lineHeight: 20,
    flex: 1,
    fontStyle: 'italic' as const,
  },
});
