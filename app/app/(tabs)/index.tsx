import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Animated, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, View,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { colors, fonts, layout } from '../../design/tokens';
import { EntitySpan, ResurfacingItem, ReviewStreamResponse } from '../../data/types';
import {
  fetchReviewStream, recordReviewResult, recordEntityTap,
  triggerMicrolearning, dismissMicrolearning,
  triggerFollowUp, suspendReviewItem, createFactualQuiz, suspendFact,
  flagMicrolearningInaccurate,
  gradeStructuralCard,
} from '../../lib/book-api';
import { logEvent } from '../../data/logger';
import { safeDate } from '../../lib/display-utils';
import { setFeedbackContext } from '../../lib/feedback-context';
import EntitySheet from '../../components/EntitySheet';
import AncientMap from '../../components/AncientMap';
import { detectDates } from '../../components/KnowledgeExplorer';
import AspectCard from '../../components/AspectCard';
import type { AspectCardData } from '../../components/AspectCard';
import SequenceCard from '../../components/SequenceCard';
import type { SequenceCardData } from '../../components/SequenceCard';
import SynchronicCard from '../../components/SynchronicCard';
import type { SynchronicCardData } from '../../components/SynchronicCard';
import CastCard from '../../components/CastCard';
import type { CastCardData } from '../../components/CastCard';
import CausalChainCard from '../../components/CausalChainCard';
import type { CausalChainCardData } from '../../components/CausalChainCard';

// ── Annotated Text (tappable entity spans) ──────────────────────────

function AnnotatedText({
  text,
  spans,
  style,
  onEntityTap,
  onDateTap,
}: {
  text: string;
  spans?: EntitySpan[];
  style: any;
  onEntityTap: (entityId: string) => void;
  onDateTap?: (year: number) => void;
}) {
  // Build a unified list of tappable ranges: entity spans + detected dates
  type TapSpan = { start: number; end: number; type: 'entity'; entityId: string }
                | { start: number; end: number; type: 'date'; year: number };
  const allSpans: TapSpan[] = [];

  if (spans) {
    for (const sp of spans) {
      allSpans.push({ start: sp.start, end: sp.end, type: 'entity', entityId: sp.entity_id });
    }
  }
  if (onDateTap) {
    for (const dt of detectDates(text)) {
      // Skip if overlapping with an entity span
      const overlaps = allSpans.some(s => dt.start < s.end && dt.end > s.start);
      if (!overlaps) {
        allSpans.push({ start: dt.start, end: dt.end, type: 'date', year: dt.year });
      }
    }
  }

  if (allSpans.length === 0) {
    return <Text style={style}>{text}</Text>;
  }

  // Sort by position
  allSpans.sort((a, b) => a.start - b.start);

  const parts: React.ReactNode[] = [];
  let cursor = 0;

  for (const span of allSpans) {
    if (span.start > cursor) {
      parts.push(<Text key={`t-${cursor}`}>{text.slice(cursor, span.start)}</Text>);
    }
    if (span.type === 'entity') {
      parts.push(
        <Text key={`e-${span.start}`} style={entityStyle.tappable}
          onPress={() => onEntityTap(span.entityId)}>
          {text.slice(span.start, span.end)}
        </Text>
      );
    } else {
      parts.push(
        <Text key={`d-${span.start}`} style={entityStyle.dateTappable}
          onPress={() => onDateTap!(span.year)}>
          {text.slice(span.start, span.end)}
        </Text>
      );
    }
    cursor = span.end;
  }
  if (cursor < text.length) {
    parts.push(<Text key={`t-${cursor}`}>{text.slice(cursor)}</Text>);
  }

  return <Text style={style}>{parts}</Text>;
}

const entityStyle = StyleSheet.create({
  tappable: {
    textDecorationLine: 'underline',
    textDecorationStyle: 'dotted',
    textDecorationColor: colors.textMuted,
  },
  dateTappable: {
    textDecorationLine: 'underline',
    textDecorationStyle: 'dotted',
    textDecorationColor: colors.rubric,
    color: colors.rubric,
  },
});

// ── Research Input ──────────────────────────────────────────────────

function FollowUpLinks({
  queries,
  triggeredFromServer,
  itemId,
  nodeTitle,
  nodeDescription,
  onResearch,
}: {
  queries: string[];
  triggeredFromServer?: string[];
  itemId?: string;
  nodeTitle?: string;
  nodeDescription?: string;
  onResearch: (q: string) => void;
}) {
  const [tapped, setTapped] = useState<Set<string>>(
    new Set(triggeredFromServer || []),
  );
  if (!queries || queries.length === 0) return null;

  const handleTap = (q: string) => {
    if (tapped.has(q)) return;
    setTapped(prev => new Set(prev).add(q));
    onResearch(q);
    if (itemId) {
      triggerFollowUp(itemId, q).catch(e =>
        console.warn('[follow-up] trigger record failed:', e));
    }
  };

  return (
    <>
      <Text style={cs.followUpLabel}>{'\uD83D\uDD0D'} Go deeper</Text>
      {queries.map((q, i) => {
        const isTriggered = tapped.has(q);
        return (
          <Pressable
            key={`${i}-${q.slice(0, 20)}`}
            style={[cs.followUpBtn, isTriggered && cs.followUpBtnTapped]}
            onPress={() => handleTap(q)}
            disabled={isTriggered}
          >
            <Text style={[cs.followUpText, isTriggered && cs.followUpTextTapped]}>
              {isTriggered ? `\u2726 Queued: ${q}` : q}
            </Text>
          </Pressable>
        );
      })}
    </>
  );
}

function QuizSuggestions({
  suggestions,
  itemId,
}: {
  suggestions: Array<{ question: string; answer: string; fact_id?: string; type?: string }>;
  itemId: string;
}) {
  const [created, setCreated] = useState<Set<string>>(new Set());

  if (!suggestions || suggestions.length === 0) return null;

  const handleCreate = (s: { question: string; answer: string; fact_id?: string }) => {
    if (created.has(s.question)) return;
    setCreated(prev => new Set(prev).add(s.question));
    logEvent('factual_quiz_created', { item_id: itemId, question: s.question });
    createFactualQuiz(itemId, s.question, s.answer, s.fact_id).catch(e =>
      console.warn('[quiz-suggestion] create failed:', e));
  };

  return (
    <View style={{ marginTop: 10 }}>
      <Text style={cs.followUpLabel}>Quick quiz</Text>
      {suggestions.map((s, i) => {
        const done = created.has(s.question);
        return (
          <Pressable
            key={i}
            style={[cs.quizSugBtn, done && cs.quizSugDone]}
            onPress={() => handleCreate(s)}
            disabled={done}
          >
            <Text style={[cs.quizSugText, done && { color: colors.textMuted }]}>
              {done ? '\u2713 ' : '+ '}
              {s.question}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function ResearchInput({ onSubmit }: { onSubmit: (query: string) => void }) {
  const [text, setText] = useState('');
  const [sent, setSent] = useState(false);

  const handleSubmit = () => {
    const q = text.trim();
    if (!q) return;
    logEvent('review_custom_query', { query: q });
    onSubmit(q);
    setSent(true);
    setText('');
  };

  if (sent) {
    return (
      <View style={ri.container}>
        <Text style={ri.sentText}>{'\uD83D\uDD0D'} Researching...</Text>
      </View>
    );
  }

  return (
    <View style={ri.container}>
      <TextInput
        style={ri.input}
        placeholder="Ask your own question..."
        placeholderTextColor={colors.textMuted}
        value={text}
        onChangeText={setText}
        onSubmitEditing={handleSubmit}
        returnKeyType="send"
      />
      {text.trim().length > 0 && (
        <Pressable style={ri.sendBtn} onPress={handleSubmit}>
          <Text style={ri.sendText}>{'\uD83D\uDD0D'}</Text>
        </Pressable>
      )}
    </View>
  );
}

const ri = StyleSheet.create({
  container: { marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 8 },
  input: {
    flex: 1, fontFamily: fonts.reading, fontSize: 14, color: colors.textBody,
    borderWidth: 1, borderColor: colors.rule, borderRadius: 4,
    paddingHorizontal: 12, paddingVertical: 8,
    ...(Platform.OS === 'web' ? { outlineStyle: 'none' as any } : {}),
  },
  sendBtn: { padding: 8 },
  sendText: { fontSize: 18 },
  sentText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
});

// ── Card Provenance Helpers ────────────────────────────────────────

function getOriginBadge(item: ResurfacingItem): { label: string; icon: string } | null {
  const p = item.provenance;
  if (!p) return null;
  const origin = p.origin;
  if (origin === 'book_chapter') {
    const src = (p.sources || []).find(s => s.book_id);
    const ch = src?.chapter_number ? `ch.${src.chapter_number}` : '';
    return { label: ch || 'Book', icon: '\uD83D\uDCD6' };
  }
  if (origin === 'book_whole') return { label: 'Whole book', icon: '\uD83D\uDCD6' };
  if (origin === 'gap_fill') return { label: 'Gap fill', icon: '\uD83D\uDD17' };
  if (origin === 'voice_wondering') return { label: 'Voice', icon: '\uD83C\uDF99' };
  if (origin === 'follow_up') return { label: 'Follow-up', icon: '\uD83D\uDD0D' };
  if (origin === 'entity_research') return { label: 'Entity', icon: '\uD83D\uDC64' };
  if (origin === 'entity_capture') {
    // Distinguish Wikidata-anchored captures with a "linked" marker.
    // Unresolved captures keep a plain speech-bubble icon.
    if (p.wikidata_qid) return { label: 'Captured', icon: '\uD83D\uDD37' };  // 🔷 blue diamond — linked
    return { label: 'Captured', icon: '\uD83D\uDCAC' };  // 💬 speech balloon
  }
  if (origin === 'user_request') return { label: 'Requested', icon: '\u2726' };
  return null;
}

function formatTimeAgo(ms: number | undefined): string {
  if (!ms) return 'Never';
  const ago = Date.now() - ms;
  const days = Math.floor(ago / 86400000);
  if (days < 1) {
    const hours = Math.floor(ago / 3600000);
    return hours < 1 ? 'Just now' : `${hours}h ago`;
  }
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function AboutCardModal({ item, visible, onClose }: {
  item: ResurfacingItem;
  visible: boolean;
  onClose: () => void;
}) {
  const p = item.provenance;
  const origin = p?.origin || 'unknown';
  const shortId = (item.question_id || '').slice(-8);

  const originLabels: Record<string, string> = {
    book_chapter: 'Book chapter mapping',
    book_whole: 'Whole book mapping',
    gap_fill: 'Prerequisite gap fill (no book backing)',
    voice_wondering: 'Voice elicitation wondering',
    follow_up: 'Follow-up query research',
    entity_research: 'Entity deep-dive research',
    entity_capture: 'Voice capture (entity-keyed)',
    user_request: 'User-requested research',
    unknown: 'Unknown origin',
  };

  const scheduleLabels: Record<string, string> = {
    never_reviewed: 'Never reviewed before',
    overdue: `Overdue by ${p?.overdue_days || 0} days`,
    due_soon: 'Due within 24 hours',
    not_due: 'Not yet due (filler)',
  };

  // Build source lists: book chapters vs. voice captures live on the same
  // `sources` array but have distinct shapes (book_id vs. source='voice_capture').
  const bookSources = (p?.sources || []).filter(s => s.book_id);
  const voiceSources = (p?.sources || []).filter(s =>
    s.source === 'voice_capture' || s.source === 'voice_elicitation'
  );

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={ab.overlay} onPress={onClose}>
        <Pressable style={ab.sheet} onPress={e => e.stopPropagation()}>
          <View style={ab.headerRow}>
            <Text style={ab.title}>About this card</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Text style={ab.closeBtn}>{'\u2715'}</Text>
            </Pressable>
          </View>

          <ScrollView style={ab.scrollBody} showsVerticalScrollIndicator={false}>
            {/* Card ID */}
            <Text style={ab.idText}>ID: {item.question_id || '—'}</Text>

            {/* Origin */}
            <Text style={ab.sectionLabel}>ORIGIN</Text>
            <Text style={ab.value}>{originLabels[origin] || origin}</Text>

            {/* Book sources */}
            {bookSources.length > 0 && <>
              <Text style={ab.sectionLabel}>SOURCE BOOKS</Text>
              {bookSources.map((src: { book_id?: string; chapter_number?: number; chapter_title?: string; confidence?: number; added_at?: number | string | null }, i: number) => (
                <View key={i} style={ab.sourceRow}>
                  <Text style={ab.value}>
                    {src.chapter_title || `Chapter ${src.chapter_number}`}
                  </Text>
                  {src.confidence != null && (
                    <Text style={ab.detail}>Confidence: {(src.confidence * 100).toFixed(0)}%</Text>
                  )}
                  {src.added_at && (
                    <Text style={ab.detail}>Added: {safeDate(src.added_at)}</Text>
                  )}
                </View>
              ))}
            </>}

            {/* Voice captures — appears for entity_capture and related origins */}
            {voiceSources.length > 0 && <>
              <Text style={ab.sectionLabel}>VOICE CAPTURE</Text>
              {voiceSources.map((src, i: number) => (
                <View key={`v-${i}`} style={ab.sourceRow}>
                  {src.source_text ? (
                    <Text style={ab.value}>&ldquo;{src.source_text}&rdquo;</Text>
                  ) : null}
                  {src.capture_id && (
                    <Text style={ab.detail}>Capture: {src.capture_id}</Text>
                  )}
                  {src.added_at && (
                    <Text style={ab.detail}>Captured: {safeDate(src.added_at)}</Text>
                  )}
                </View>
              ))}
            </>}

            {/* Wikidata identity (entity_capture items) */}
            {p?.wikidata_qid && <>
              <Text style={ab.sectionLabel}>WIKIDATA</Text>
              <Text style={ab.value}>{p.wikidata_qid}</Text>
              {p?.entity_id && (
                <Text style={ab.detail}>Entity: {p.entity_id}</Text>
              )}
            </>}

            {/* ML provenance */}
            {p?.source_item_id ? <>
              <Text style={ab.sectionLabel}>TRIGGERED BY</Text>
              <Text style={ab.detail}>Item: {p.source_item_id}</Text>
              {p.generation_depth != null && p.generation_depth > 0 && (
                <Text style={ab.detail}>Depth: {p.generation_depth} (child card)</Text>
              )}
            </> : null}

            {/* Scheduling */}
            <Text style={ab.sectionLabel}>SCHEDULING</Text>
            <View style={ab.row}>
              <Text style={ab.label}>Status</Text>
              <Text style={ab.value}>
                {scheduleLabels[p?.schedule_reason || ''] || p?.schedule_reason || '—'}
              </Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Reviews</Text>
              <Text style={ab.value}>{item.review_count ?? 0} times</Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Last score</Text>
              <Text style={ab.value}>{item.last_score || 'Never graded'}</Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Last reviewed</Text>
              <Text style={ab.value}>{formatTimeAgo(p?.last_reviewed_at)}</Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Stability</Text>
              <Text style={ab.value}>{(item.stability_days ?? 0).toFixed(1)} days</Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Due</Text>
              <Text style={ab.value}>
                {p?.due_at ? (p.due_at <= Date.now() ? `Overdue (${formatTimeAgo(p.due_at)})` : safeDate(p.due_at)) : '—'}
              </Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Created</Text>
              <Text style={ab.value}>
                {safeDate(p?.created_at)}
              </Text>
            </View>

            {/* Knowledge state */}
            <Text style={ab.sectionLabel}>KNOWLEDGE STATE</Text>
            <View style={ab.row}>
              <Text style={ab.label}>Level</Text>
              <Text style={ab.value}>{item.node_knowledge || 'unknown'}</Text>
            </View>
            <View style={ab.row}>
              <Text style={ab.label}>Confidence</Text>
              <Text style={ab.value}>{((item.node_confidence ?? 0) * 100).toFixed(0)}%</Text>
            </View>

            {/* Stream ranking */}
            {p?.stream_score != null && <>
              <Text style={ab.sectionLabel}>STREAM RANKING</Text>
              <View style={ab.row}>
                <Text style={ab.label}>Score</Text>
                <Text style={ab.value}>{p.stream_score}</Text>
              </View>
              {p.knowledge_weight != null && (
                <View style={ab.row}>
                  <Text style={ab.label}>Knowledge weight</Text>
                  <Text style={ab.value}>{p.knowledge_weight}</Text>
                </View>
              )}
              {p.fact_type_adj != null && p.fact_type_adj !== 0 && (
                <View style={ab.row}>
                  <Text style={ab.label}>Fact type adj.</Text>
                  <Text style={ab.value}>{p.fact_type_adj > 0 ? '+' : ''}{p.fact_type_adj}</Text>
                </View>
              )}
              {p.is_gap_fill && (
                <View style={ab.row}>
                  <Text style={ab.label}>Gap fill penalty</Text>
                  <Text style={ab.value}>-5.0</Text>
                </View>
              )}
            </>}

            {/* Short ID for easy reporting */}
            <View style={ab.idRow}>
              <Text style={ab.idLabel}>Short ID: </Text>
              <Text style={ab.idCode}>{shortId}</Text>
            </View>
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// ── Review Card ─────────────────────────────────────────────────────

function ReviewCard({
  item,
  onResult,
  onSkip,
  onSuspend,
  onEntityTap,
  onDateTap,
  onResearch,
}: {
  item: ResurfacingItem;
  onResult: (result: string) => void;
  onSkip: () => void;
  onSuspend: () => void;
  onEntityTap: (entityId: string) => void;
  onDateTap: (year: number) => void;
  onResearch: (query: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const revealedAtRef = useRef(0);
  const originBadge = getOriginBadge(item);

  const handleReveal = () => {
    setRevealed(true);
    revealedAtRef.current = Date.now();
    logEvent('review_answer_revealed', {
      question_id: item.question_id,
      node_title: item.node_title,
      domain: item.domain,
    });
  };

  const answerType = item.answer_type || 'concept';
  const typeLabel = answerType === 'date' ? 'Date'
    : answerType === 'person' ? 'Person'
    : answerType === 'event' ? 'Event'
    : answerType === 'connection' ? 'Connection'
    : answerType === 'significance' ? 'Significance'
    : answerType === 'name' ? 'Identity'
    : answerType === 'sequence' ? 'Timeline'
    : 'Concept';

  // Domain label — short readable name
  const domainLabel = (item.domain || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .slice(0, 40);

  const gradingButtons = [
    { value: 'knew', label: 'Knew it', style: 'correct' as const },
    { value: 'partly', label: 'Partly', style: 'partial' as const },
    { value: 'missed', label: 'Missed', style: 'wrong' as const },
  ];

  const handleGrade = (result: string) => {
    onResult(result);
  };

  const shortAnswer = (item.answer || '').trim();
  const displayAnswer = item.rich_answer || item.answer || '';
  // Show short answer separately only if it's meaningfully different from rich_answer
  const showShortAnswer = shortAnswer && displayAnswer
    && shortAnswer !== displayAnswer
    && !displayAnswer.startsWith(shortAnswer);
  const anchors = item.anchors || [];

  return (
    <View style={cs.card}>
      {/* Header: type badge + origin + domain + menu */}
      <View style={cs.headerRow}>
        <View style={cs.typeBadge}>
          <Text style={cs.typeBadgeText}>{typeLabel}</Text>
        </View>
        {originBadge && (
          <Text style={cs.originBadge}>{originBadge.icon} {originBadge.label}</Text>
        )}
        <Text style={[cs.domainLabel, { flex: 1 }]} numberOfLines={1}>{domainLabel}</Text>
        <Pressable onPress={() => setShowMenu(v => !v)} hitSlop={8} style={cs.menuDotsBtn}>
          <Text style={cs.menuDots}>{showMenu ? '\u2715' : '\u22EF'}</Text>
        </Pressable>
      </View>
      {showMenu && (
        <View style={cs.menuDropdown}>
          <Pressable style={cs.menuDropdownItem} onPress={() => { setShowMenu(false); setShowAbout(true); }}>
            <Text style={cs.menuDropdownText}>About this card</Text>
          </Pressable>
          <Pressable style={cs.menuDropdownItem} onPress={() => {
            setShowMenu(false);
            logEvent('review_flag_bad_question', {
              question_id: item.question_id,
              question: item.question,
              node_title: item.node_title,
              domain: item.domain,
              answer_type: item.answer_type,
              origin: item.provenance?.origin,
            });
          }}>
            <Text style={[cs.menuDropdownText, { color: colors.rubric }]}>Bad question</Text>
          </Pressable>
          <Pressable style={cs.menuDropdownItem} onPress={() => { setShowMenu(false); onSuspend(); }}>
            <Text style={cs.menuDropdownText}>Suspend this topic</Text>
          </Pressable>
        </View>
      )}
      <AboutCardModal item={item} visible={showAbout} onClose={() => setShowAbout(false)} />

      {/* Node title (context) + timeline link */}
      {revealed && item.node_title ? (
        <View style={cs.nodeTitleRow}>
          <Text style={[cs.nodeTitle, { flex: 1, marginBottom: 0 }]}>{item.node_title}</Text>
          {onDateTap && (
            <Pressable onPress={() => {
              // Find a date in the card content to anchor the timeline
              const dates = detectDates(item.rich_answer || item.answer || item.node_title || '');
              onDateTap(dates.length > 0 ? dates[0].year : 0);
            }} hitSlop={8} style={cs.timelineLink}>
              <Text style={cs.timelineLinkText}>✦ Timeline</Text>
            </Pressable>
          )}
        </View>
      ) : null}

      {/* Question */}
      <Text style={cs.question}>{item.question}</Text>

      {/* Uncertainty indicator — learner's captured confidence (Session 90 P1.1) */}
      {item.confidence === 'uncertain' ? (
        <Text style={cs.epistemicHedge}>{'\u223C'} you captured this with a hedge</Text>
      ) : item.confidence === 'wrong' ? (
        <Text style={cs.epistemicWrong}>{'\u26A0'} captured as a confident guess</Text>
      ) : null}

      {/* Reveal / Answer */}
      {!revealed ? (
        <View style={cs.actionRow}>
          <Pressable style={cs.revealButton} onPress={handleReveal}>
            <Text style={cs.revealText}>Show answer</Text>
          </Pressable>
          <Pressable style={cs.skipButton} onPress={onSkip}>
            <Text style={cs.skipText}>Skip {'\u2192'}</Text>
          </Pressable>
        </View>
      ) : (
        <View>
          {/* Correction block — verifiable contradiction (Session 90 P1.2) */}
          {item.correction && item.correction.user_said && item.correction.actually ? (
            <View style={cs.correctionBox}>
              <Text style={cs.correctionLabel}>You said</Text>
              <Text style={cs.correctionUserSaid}>{item.correction.user_said}</Text>
              <Text style={cs.correctionLabel}>Actually</Text>
              <Text style={cs.correctionActually}>{item.correction.actually}</Text>
              {item.correction.why_confused ? (
                <Text style={cs.correctionWhy}>{item.correction.why_confused}</Text>
              ) : null}
            </View>
          ) : null}

          {/* Short answer (succinct) + quick "Knew it" */}
          {showShortAnswer ? (
            <View style={cs.shortAnswerBox}>
              <Text style={cs.shortAnswerText}>{shortAnswer}</Text>
              <Pressable style={cs.quickKnewButton} onPress={() => handleGrade('knew')}>
                <Text style={cs.quickKnewText}>Knew it {'\u2713'}</Text>
              </Pressable>
            </View>
          ) : null}

          {/* Rich answer */}
          <View style={cs.answerBox}>
            <AnnotatedText
              text={displayAnswer}
              spans={item.entity_spans?.rich_answer}
              style={cs.answerText}
              onEntityTap={onEntityTap}
              onDateTap={onDateTap}
            />
          </View>

          {/* Memory hook */}
          {item.memory_hook ? (
            <View style={cs.hookBox}>
              <Text style={cs.hookLabel}>{'\u2726'} Memory hook</Text>
              <AnnotatedText
                text={item.memory_hook}
                spans={item.entity_spans?.memory_hook}
                style={cs.hookText}
                onEntityTap={onEntityTap}
                onDateTap={onDateTap}
              />
            </View>
          ) : null}

          {/* Temporal anchors */}
          {anchors.length > 0 ? (
            <View style={cs.anchorBox}>
              {anchors.map((a, i) => (
                <Text key={i} style={cs.anchorText}>{'\u2022'} {a}</Text>
              ))}
            </View>
          ) : null}

          {/* Curriculum context */}
          {item.curriculum_context ? (
            <Text style={cs.contextText}>{item.curriculum_context}</Text>
          ) : null}

          {/* Place entity map links */}
          {(() => {
            const allSpans = Object.values(item.entity_spans || {}).flat();
            const places = allSpans.filter(sp => sp.entity_type === 'place');
            const seen = new Set<string>();
            const unique = places.filter(sp => {
              if (seen.has(sp.entity_id)) return false;
              seen.add(sp.entity_id);
              return true;
            });
            if (unique.length === 0) return null;
            return (
              <View style={cs.mapLinkRow}>
                {unique.map(sp => (
                  <Pressable key={sp.entity_id} onPress={() => onEntityTap(sp.entity_id)}>
                    <Text style={cs.mapLinkText}>{'\uD83D\uDCCD'} {sp.name}</Text>
                  </Pressable>
                ))}
              </View>
            );
          })()}

          {/* Grading buttons */}
          <View style={cs.gradeRow}>
            {gradingButtons.map(btn => {
              const btnStyle = btn.style === 'correct' ? cs.gradeCorrect
                : btn.style === 'partial' ? cs.gradePartial
                : cs.gradeWrong;
              const txtStyle = btn.style === 'correct' ? cs.gradeCorrectText
                : btn.style === 'partial' ? cs.gradePartialText
                : cs.gradeWrongText;
              return (
                <Pressable
                  key={btn.value}
                  style={[cs.gradeButton, btnStyle]}
                  onPress={() => handleGrade(btn.value)}
                >
                  <Text style={txtStyle}>{btn.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {/* Follow-up research queries + custom input */}
          <View style={cs.followUpSection}>
            <FollowUpLinks
              queries={item.follow_up_queries || []}
              triggeredFromServer={item.triggered_follow_ups}
              itemId={item.question_id}
              nodeTitle={item.node_title}
              nodeDescription={item.node_description}
              onResearch={onResearch}
            />

            {/* Factual quiz suggestions — one-tap to create quiz from key_facts */}
            {item.question_id && (item as any).quiz_suggestions?.length > 0 && (
              <QuizSuggestions
                suggestions={(item as any).quiz_suggestions}
                itemId={item.question_id}
              />
            )}

            {/* Related facts from the same topic — informational checklist */}
            {(item as any).related_facts?.length > 0 && (
              <View style={{ marginTop: 10 }}>
                <Text style={cs.followUpLabel}>Same topic</Text>
                {(item as any).related_facts.map((f: { question: string; type: string; status: string; score?: string }, i: number) => {
                  const isTested = f.status === 'tested';
                  return (
                    <View key={i} style={[cs.relatedFactBtn, isTested && cs.relatedFactTested]}>
                      <Text style={[cs.relatedFactType, isTested && { color: colors.textMuted }]}>
                        {isTested ? (f.score === 'knew' ? '\u2713' : '\u25CB') : '\u25CB'}
                      </Text>
                      <Text style={[cs.relatedFactText, isTested && { color: colors.textMuted, opacity: 0.7 }]}>
                        {f.question}
                      </Text>
                    </View>
                  );
                })}
              </View>
            )}

            {/* Existing quizzes for this node */}
            {(item as any).existing_quizzes?.length > 0 && (
              <View style={{ marginTop: 10 }}>
                <Text style={cs.followUpLabel}>Quizzes for this topic</Text>
                {(item as any).existing_quizzes.map((q: { id: string; question: string; fact_id: string; status: string; last_score: string | null; review_count: number }, i: number) => {
                  const dismissed = q.status === 'dismissed';
                  const score = q.last_score;
                  const icon = dismissed ? '\u2015' : score === 'knew' ? '\u2713' : score === 'partly' ? '\u25CB' : score === 'missed' ? '\u2717' : '\u2022';
                  const muted = dismissed || score === 'knew';
                  return (
                    <View key={q.id} style={[cs.relatedFactBtn, muted && cs.relatedFactTested]}>
                      <Text style={[cs.relatedFactType, muted && { color: colors.textMuted }]}>
                        {icon}
                      </Text>
                      <Text style={[cs.relatedFactText, muted && { color: colors.textMuted, opacity: 0.7 }]} numberOfLines={2}>
                        {q.question}
                      </Text>
                    </View>
                  );
                })}
              </View>
            )}

            <ResearchInput onSubmit={onResearch} />
          </View>
        </View>
      )}
    </View>
  );
}

// ── Microlearning Card (first encounter: content + all quizzes) ─────

function MicrolearningCard({
  item,
  onComplete,
  onDismissCard,
  onDismissQuiz,
  onFlagInaccurate,
  onResult,
  onResearch,
  onEntityTap,
  onDateTap,
}: {
  item: ResurfacingItem;
  onComplete: () => void;
  onDismissCard: () => void;
  onDismissQuiz: (quizId: string) => void;
  onFlagInaccurate?: (cardId: string) => void;
  onResult: (quizId: string, result: string) => void;
  onResearch: (query: string) => void;
  onEntityTap: (entityId: string) => void;
  onDateTap: (year: number) => void;
}) {
  const quizzes = item.quizzes || (item.question ? [{ id: item.question_id || '', question: item.question, answer: item.answer || '' }] : []);
  const [revealedQuizzes, setRevealedQuizzes] = useState<Set<string>>(new Set());
  const [gradedQuizzes, setGradedQuizzes] = useState<Set<string>>(new Set());
  const [dismissedQuizzes, setDismissedQuizzes] = useState<Set<string>>(new Set());
  const [showAbout, setShowAbout] = useState(false);
  const originBadge = getOriginBadge(item);

  const handleReveal = (quizId: string) => {
    setRevealedQuizzes(prev => new Set(prev).add(quizId));
  };
  const handleGrade = (quizId: string, result: string) => {
    setGradedQuizzes(prev => new Set(prev).add(quizId));
    onResult(quizId, result);
  };
  const handleDismissQuiz = (quizId: string) => {
    setDismissedQuizzes(prev => new Set(prev).add(quizId));
    onDismissQuiz(quizId);
  };

  const gradeButtons = [
    { value: 'knew', label: 'Got it', style: 'correct' as const },
    { value: 'partly', label: 'Partly', style: 'partial' as const },
    { value: 'missed', label: 'Missed', style: 'wrong' as const },
  ];

  return (
    <View style={cs.card}>
      {/* Top actions */}
      <View style={ml.topRow}>
        <View style={ml.badge}>
          <Text style={ml.badgeText}>Research</Text>
        </View>
        {originBadge && (
          <Text style={cs.originBadge}>{originBadge.icon} {originBadge.label}</Text>
        )}
        <View style={{ flex: 1 }} />
        <View style={ml.topActions}>
          <Pressable style={ml.topActionBtn} onPress={() => setShowAbout(true)} hitSlop={8}>
            <Text style={ml.topActionText}>About</Text>
          </Pressable>
          <Pressable style={ml.topActionBtn} onPress={onComplete} hitSlop={8}>
            <Text style={ml.topActionText}>Skip</Text>
          </Pressable>
          <Pressable style={ml.topActionBtn} onPress={onDismissCard} hitSlop={8}>
            <Text style={ml.topActionText}>Suspend</Text>
          </Pressable>
          {onFlagInaccurate && item.question_id && (
            <Pressable style={ml.topActionBtn}
                       onPress={() => onFlagInaccurate(item.question_id!)}
                       hitSlop={8}>
              <Text style={[ml.topActionText, { color: colors.rubric }]}>Inaccurate</Text>
            </Pressable>
          )}
        </View>
      </View>
      <AboutCardModal item={item} visible={showAbout} onClose={() => setShowAbout(false)} />
      {item.title ? (
        <Text style={ml.cardTitle}>{item.title}</Text>
      ) : null}
      {(!item.title || item.title !== item.query) ? (
        <Text style={cs.domainLabel}>{item.query}</Text>
      ) : null}

      {/* Content — use sections if available, otherwise flat content */}
      {item.sections && item.sections.length > 0 ? (
        <View>
          {item.sections.map((sec, i) => (
            <View key={i} style={i > 0 ? ml.sectionBlock : undefined}>
              {sec.heading ? (
                <Text style={ml.sectionHeading}>{sec.heading}</Text>
              ) : null}
              <AnnotatedText
                text={sec.text}
                spans={item.entity_spans?.[`section_${i}`]}
                style={ml.content}
                onEntityTap={onEntityTap}
                onDateTap={onDateTap}
              />
            </View>
          ))}
        </View>
      ) : (
        <AnnotatedText
          text={item.content || ''}
          spans={item.entity_spans?.content}
          style={ml.content}
          onEntityTap={onEntityTap}
          onDateTap={onDateTap}
        />
      )}

      {/* All quizzes */}
      {quizzes.length > 0 && (
        <View style={ml.quizSection}>
          <Text style={ml.quizSectionLabel}>{quizzes.length} questions</Text>
          {quizzes.map(q => {
            if (dismissedQuizzes.has(q.id)) {
              return (
                <View key={q.id} style={ml.quizDismissed}>
                  <Text style={ml.quizDismissedText}>Dismissed</Text>
                </View>
              );
            }
            if (gradedQuizzes.has(q.id)) {
              return (
                <View key={q.id} style={ml.quizGraded}>
                  <Text style={cs.responded}>Recorded {'\u2713'}</Text>
                </View>
              );
            }
            const isRevealed = revealedQuizzes.has(q.id);
            return (
              <View key={q.id} style={ml.quizCard}>
                <Text style={ml.quizQuestion}>{q.question}</Text>
                {!isRevealed ? (
                  <View style={ml.quizActions}>
                    <Pressable style={cs.revealButton} onPress={() => handleReveal(q.id)}>
                      <Text style={cs.revealText}>Show answer</Text>
                    </Pressable>
                    <Pressable onPress={() => handleDismissQuiz(q.id)} hitSlop={8}>
                      <Text style={ml.dismissText}>Skip</Text>
                    </Pressable>
                  </View>
                ) : (
                  <View>
                    <View style={cs.answerBox}>
                      <Text style={cs.answerText}>{q.answer}</Text>
                    </View>
                    <View style={cs.gradeRow}>
                      {gradeButtons.map(btn => (
                        <Pressable
                          key={btn.value}
                          style={[cs.gradeButton, btn.style === 'correct' ? cs.gradeCorrect : btn.style === 'partial' ? cs.gradePartial : cs.gradeWrong]}
                          onPress={() => handleGrade(q.id, btn.value)}
                        >
                          <Text style={btn.style === 'correct' ? cs.gradeCorrectText : btn.style === 'partial' ? cs.gradePartialText : cs.gradeWrongText}>
                            {btn.label}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                )}
              </View>
            );
          })}
        </View>
      )}

      {/* Follow-ups */}
      <View style={cs.followUpSection}>
        <FollowUpLinks
              queries={item.follow_up_queries || []}
              triggeredFromServer={item.triggered_follow_ups}
              itemId={item.question_id}
              nodeTitle={item.node_title}
              nodeDescription={item.node_description}
              onResearch={onResearch}
            />
        <ResearchInput onSubmit={onResearch} />
      </View>

      {/* Bottom action */}
      <View style={ml.bottomActions}>
        <Pressable style={ml.completeBtn} onPress={onComplete}>
          <Text style={ml.completeBtnText}>Complete {'\u2192'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

// ── Microlearning Quiz (individual re-review) ──────────────────────

function MicrolearningQuizCard({
  item,
  onResult,
  onSkip,
  onSuspendFact,
  onFlagInaccurate,
  onResearch,
  onEntityTap,
  onDateTap,
}: {
  item: ResurfacingItem;
  onResult: (result: string, responseTimeMs?: number) => void;
  onSkip: () => void;
  onSuspendFact?: (factId: string) => void;
  onFlagInaccurate?: (cardId: string) => void;
  onResearch: (query: string) => void;
  onEntityTap: (entityId: string) => void;
  onDateTap: (year: number) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [graded, setGraded] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const displayTimeRef = useRef(Date.now());
  const [elapsedSec, setElapsedSec] = useState(0);

  // Subtle timer: update every second after 3s, stop on reveal
  useEffect(() => {
    if (revealed) return;
    const id = setInterval(() => {
      const sec = Math.floor((Date.now() - displayTimeRef.current) / 1000);
      if (sec >= 3) setElapsedSec(sec);
    }, 1000);
    return () => clearInterval(id);
  }, [revealed]);

  if (graded) {
    return (
      <View style={cs.card}>
        <Text style={cs.responded}>Recorded {'\u2713'}</Text>
      </View>
    );
  }

  const responseTimeMs = () => Date.now() - displayTimeRef.current;
  const originBadge = getOriginBadge(item);

  return (
    <View style={cs.card}>
      <View style={cs.headerRow}>
        <View style={ml.badge}>
          <Text style={ml.badgeText}>Review</Text>
        </View>
        {originBadge && (
          <Text style={cs.originBadge}>{originBadge.icon} {originBadge.label}</Text>
        )}
        {item.title ? (
          <Text style={[ml.quizCardTitle, { flex: 1 }]} numberOfLines={1}>{item.title}</Text>
        ) : (
          <Text style={[cs.domainLabel, { flex: 1 }]} numberOfLines={1}>{item.query}</Text>
        )}
        <Pressable onPress={() => setShowMenu(m => !m)} hitSlop={8} style={cs.menuDotsBtn}>
          <Text style={cs.menuDots}>{showMenu ? '\u2715' : '\u22EF'}</Text>
        </Pressable>
      </View>
      {showMenu && (
        <View style={cs.menuDropdown}>
          <Pressable style={cs.menuDropdownItem} onPress={() => { setShowMenu(false); setShowAbout(true); }}>
            <Text style={cs.menuDropdownText}>About this card</Text>
          </Pressable>
          {(item as any).fact_id && onSuspendFact && (
            <Pressable style={cs.menuDropdownItem} onPress={() => { setShowMenu(false); onSuspendFact((item as any).fact_id); }}>
              <Text style={cs.menuDropdownText}>Not interested in this fact</Text>
            </Pressable>
          )}
          {onFlagInaccurate && ((item as any).card_id || item.question_id) && (
            <Pressable style={cs.menuDropdownItem} onPress={() => {
              setShowMenu(false);
              onFlagInaccurate((item as any).card_id || item.question_id);
            }}>
              <Text style={[cs.menuDropdownText, { color: colors.rubric }]}>Inaccurate fact</Text>
            </Pressable>
          )}
        </View>
      )}
      <AboutCardModal item={item} visible={showAbout} onClose={() => setShowAbout(false)} />

      <View style={{ flexDirection: 'row', alignItems: 'flex-start' }}>
        <Text style={[cs.question, { flex: 1 }]}>{item.question}</Text>
        {elapsedSec >= 3 && !revealed && (
          <Text style={{ color: 'rgba(139,115,85,0.35)', fontSize: 12, fontVariant: ['tabular-nums'], marginLeft: 8, marginTop: 2 }}>
            {elapsedSec}s
          </Text>
        )}
      </View>

      {!revealed ? (
        <View style={cs.actionRow}>
          <Pressable style={cs.revealButton} onPress={() => setRevealed(true)}>
            <Text style={cs.revealText}>Show answer</Text>
          </Pressable>
          <Pressable style={cs.skipButton} onPress={onSkip}>
            <Text style={cs.skipText}>Skip {'\u2192'}</Text>
          </Pressable>
        </View>
      ) : (
        <View>
          <View style={cs.answerBox}>
            <Text style={cs.answerText}>{item.answer}</Text>
          </View>

          {/* Full content — use rich_answer as detail card if no ML content */}
          {(item.content || (item.rich_answer && item.rich_answer !== item.answer)) ? (
            <View style={ml.revealedContent}>
              <Text style={ml.revealedLabel}>{'\u2726'} Full context</Text>
              <AnnotatedText
                text={item.content || item.rich_answer || ''}
                spans={item.entity_spans?.content}
                style={ml.content}
                onEntityTap={onEntityTap}
                onDateTap={onDateTap}
              />
            </View>
          ) : null}

          <View style={cs.gradeRow}>
            {[
              { value: 'knew', label: 'Got it', style: 'correct' as const },
              { value: 'partly', label: 'Partly', style: 'partial' as const },
              { value: 'missed', label: 'Missed', style: 'wrong' as const },
            ].map(btn => (
              <Pressable
                key={btn.value}
                style={[cs.gradeButton, btn.style === 'correct' ? cs.gradeCorrect : btn.style === 'partial' ? cs.gradePartial : cs.gradeWrong]}
                onPress={() => { onResult(btn.value, responseTimeMs()); setGraded(true); }}
              >
                <Text style={btn.style === 'correct' ? cs.gradeCorrectText : btn.style === 'partial' ? cs.gradePartialText : cs.gradeWrongText}>
                  {btn.label}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={cs.followUpSection}>
            <FollowUpLinks
              queries={item.follow_up_queries || []}
              triggeredFromServer={item.triggered_follow_ups}
              itemId={item.question_id}
              nodeTitle={item.node_title}
              nodeDescription={item.node_description}
              onResearch={onResearch}
            />
            <ResearchInput onSubmit={onResearch} />
          </View>
        </View>
      )}
    </View>
  );
}

// ── Entity Intro Card ────────────────────────────────────────────────

const INTRO_TYPE_LABELS: Record<string, string> = {
  place: '\uD83D\uDCCD Place',
  person: '\uD83D\uDC64 Person',
  event: '\u26A1 Event',
  period: '\uD83D\uDD51 Period',
};

function EntityIntroCard({
  item,
  onContinue,
}: {
  item: ResurfacingItem;
  onContinue: () => void;
}) {
  const [continued, setContinued] = useState(false);

  const formatYear = (y: number | null | undefined) => {
    if (y == null) return '';
    return y < 0 ? `${Math.abs(y)} BC` : `${y} AD`;
  };

  const handleContinue = () => {
    setContinued(true);
    if (item.entity_id) {
      recordEntityTap(item.entity_id, 'encountered').catch(() => {});
      logEvent('entity_intro_seen', { entity_id: item.entity_id });
    }
    setTimeout(onContinue, 400);
  };

  if (continued) {
    return (
      <View style={cs.card}>
        <Text style={cs.responded}>Noted {'\u2713'}</Text>
      </View>
    );
  }

  const dateStr = item.date_start != null
    ? `${formatYear(item.date_start)}${item.date_end != null ? ` \u2013 ${formatYear(item.date_end)}` : ''}`
    : null;

  return (
    <View style={cs.card}>
      <View style={cs.headerRow}>
        {item.entity_type && (
          <View style={ic.introBadge}>
            <Text style={ic.introBadgeText}>
              {INTRO_TYPE_LABELS[item.entity_type] || item.entity_type}
            </Text>
          </View>
        )}
        <Text style={ic.introLabel}>Entity briefing</Text>
      </View>

      <Text style={ic.entityName}>{item.entity_name}</Text>
      {item.modern_name && item.modern_name !== item.entity_name ? (
        <Text style={ic.modernName}>Modern: {item.modern_name}</Text>
      ) : null}

      {item.entity_type === 'place' && item.latitude != null && item.longitude != null ? (
        <View style={ic.miniMapWrap}>
          <AncientMap
            entities={[{
              entity_id: item.entity_id || '',
              name: item.entity_name || '',
              entity_type: 'place',
              latitude: item.latitude,
              longitude: item.longitude,
              aliases: [],
              nexus_score: 0,
              curriculum_links: [],
            }]}
            center={[item.latitude, item.longitude]}
            zoom={7}
            tileLayer="clean"
            showControls={false}
            showTimeline={false}
            showFilters={false}
            showLegend={false}
            showEntitySheet={false}
            style={{ height: 140 }}
          />
        </View>
      ) : null}

      {item.description ? (
        <Text style={ic.description}>{item.description}</Text>
      ) : null}

      {dateStr ? (
        <Text style={ic.dateFact}>{'\u2022'} {dateStr}</Text>
      ) : null}

      <Pressable style={ic.continueBtn} onPress={handleContinue}>
        <Text style={ic.continueText}>Continue {'\u2192'}</Text>
      </Pressable>
    </View>
  );
}

// ── Main Screen ─────────────────────────────────────────────────────

export default function ReviewScreen() {
  const router = useRouter();
  const [items, setItems] = useState<ResurfacingItem[]>([]);
  const [streamMeta, setStreamMeta] = useState<Partial<ReviewStreamResponse>>({});
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [activeEntityId, setActiveEntityId] = useState<string | null>(null);
  const [flagTargetCardId, setFlagTargetCardId] = useState<string | null>(null);
  const [flagReason, setFlagReason] = useState('');
  const offsetRef = useRef(0);
  const fadeAnim = useRef(new Animated.Value(1)).current;
  const cardShownAtRef = useRef<number>(Date.now());
  const scrollRef = useRef<ScrollView>(null);
  const gradedIdsRef = useRef<Set<string>>(new Set());
  const lastLoadedRef = useRef<number>(0);

  const loadStream = useCallback(async (reset = true) => {
    if (reset) {
      setLoading(true);
      setError('');
      offsetRef.current = 0;
    } else {
      setLoadingMore(true);
    }
    try {
      const result = await fetchReviewStream({
        limit: 20,
        offset: offsetRef.current,
      });
      // Filter out items already graded in this session
      const graded = gradedIdsRef.current;
      const filtered = result.items.filter(
        (it: ResurfacingItem) => !it.question_id || !graded.has(it.question_id)
      );
      if (reset) {
        setItems(filtered);
        setCurrentIndex(0);
      } else {
        setItems(prev => [...prev, ...filtered]);
      }
      setStreamMeta(result);
      offsetRef.current += result.items.length;
      lastLoadedRef.current = Date.now();
      logEvent('review_stream_loaded', {
        item_count: filtered.length,
        total_candidates: result.total_candidates,
        due_count: result.due_count,
        offset: offsetRef.current,
      });
    } catch (e: any) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    setFeedbackContext({ screen: 'review' });
    // Don't reload if we were away less than 60s — just resume where we left off
    const elapsed = Date.now() - lastLoadedRef.current;
    if (lastLoadedRef.current === 0 || elapsed > 60_000) {
      loadStream(true);
    }
  }, []));

  // Auto-load more when nearing end of items
  const maybeLoadMore = useCallback(() => {
    if (currentIndex >= items.length - 3 && streamMeta.has_more && !loadingMore) {
      loadStream(false);
    }
  }, [currentIndex, items.length, streamMeta.has_more, loadingMore]);

  const animateTransition = useCallback((callback: () => void) => {
    Animated.timing(fadeAnim, {
      toValue: 0,
      duration: 150,
      useNativeDriver: true,
    }).start(() => {
      callback();
      scrollRef.current?.scrollTo({ y: 0, animated: false });
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 200,
        useNativeDriver: true,
      }).start();
    });
  }, [fadeAnim]);

  // Log when a new card is shown
  const logCardShown = useCallback((item: ResurfacingItem) => {
    cardShownAtRef.current = Date.now();
    logEvent('review_card_shown', {
      type: item.type,
      question_id: item.question_id,
      domain: item.domain,
      node_title: item.node_title,
      review_count: item.review_count,
      node_knowledge: item.node_knowledge,
      has_follow_ups: (item.follow_up_queries?.length ?? 0) > 0,
    });
  }, []);

  const timeOnCard = () => Math.round((Date.now() - cardShownAtRef.current) / 1000);

  const handleResult = async (item: ResurfacingItem, result: string, responseTimeMs?: number) => {
    const seconds = timeOnCard();
    if (item.question_id) {
      gradedIdsRef.current.add(item.question_id);
      recordReviewResult(item.question_id, result, responseTimeMs).catch(e =>
        console.warn('[review] score failed:', e));
      logEvent('review_result', {
        question_id: item.question_id,
        result,
        answer_type: item.answer_type,
        domain: item.domain,
        node_title: item.node_title,
        review_count: item.review_count,
        time_seconds: seconds,
        response_time_ms: responseTimeMs,
        card_type: item.type,
      });
    }
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleSkip = (item: ResurfacingItem) => {
    if (item.question_id) gradedIdsRef.current.add(item.question_id);
    logEvent('review_skip', {
      question_id: item.question_id,
      domain: item.domain,
      node_title: item.node_title,
      time_seconds: timeOnCard(),
      card_type: item.type,
    });
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleSuspend = (item: ResurfacingItem) => {
    if (item.question_id) {
      gradedIdsRef.current.add(item.question_id);
      suspendReviewItem(item.question_id).catch(e =>
        console.warn('[review] suspend failed:', e));
    }
    logEvent('review_suspend', {
      question_id: item.question_id,
      node_title: item.node_title,
      domain: item.domain,
    });
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleSuspendFact = (factId: string) => {
    logEvent('review_suspend_fact', { fact_id: factId });
    suspendFact(factId).catch(e =>
      console.warn('[review] suspend fact failed:', e));
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleDismissCard = (item: ResurfacingItem) => {
    if (item.question_id) {
      gradedIdsRef.current.add(item.question_id);
      dismissMicrolearning({ cardId: item.question_id }).catch(e =>
        console.warn('[review] dismiss failed:', e));
    }
    logEvent('review_dismiss_card', {
      question_id: item.question_id,
      query: item.query,
      time_seconds: timeOnCard(),
    });
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleDismissQuiz = (quizId: string) => {
    dismissMicrolearning({ quizId }).catch(e =>
      console.warn('[review] dismiss quiz failed:', e));
    logEvent('review_dismiss_quiz', { quiz_id: quizId });
  };

  const handleFlagInaccurate = (cardId: string) => {
    setFlagTargetCardId(cardId);
    setFlagReason('');
  };

  const confirmFlagInaccurate = () => {
    const cardId = flagTargetCardId;
    if (!cardId) return;
    const reason = flagReason.trim();
    gradedIdsRef.current.add(cardId);
    flagMicrolearningInaccurate(cardId, reason).catch(e =>
      console.warn('[review] flag inaccurate failed:', e));
    logEvent('review_flag_inaccurate', { card_id: cardId, reason });
    setFlagTargetCardId(null);
    setFlagReason('');
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleQuizResult = (quizId: string, result: string, responseTimeMs?: number) => {
    recordReviewResult(quizId, result, responseTimeMs).catch(e =>
      console.warn('[review] quiz score failed:', e));
    logEvent('review_quiz_result', {
      quiz_id: quizId,
      result,
      time_seconds: timeOnCard(),
      response_time_ms: responseTimeMs,
    });
  };

  const handleEntityIntroContinue = () => {
    const cur = items[currentIndex];
    if (cur?.entity_id) gradedIdsRef.current.add(cur.entity_id);
    logEvent('review_entity_intro_continue', {
      entity_id: cur?.entity_id,
      time_seconds: timeOnCard(),
    });
    animateTransition(() => {
      setCurrentIndex(i => i + 1);
      maybeLoadMore();
    });
  };

  const handleDateTap = useCallback((year: number) => {
    logEvent('review_date_tap', { year });
    router.push(`/timeline?year=${year}` as any);
  }, [router]);

  const handleExploreEntity = useCallback((entityId: string) => {
    logEvent('review_explore_entity', { entity_id: entityId });
    router.push(`/timeline?entity=${entityId}` as any);
  }, [router]);

  const handleResearch = (query: string, item?: ResurfacingItem) => {
    const sourceNodeId = item?.question_id?.split(':').pop();
    const sourceDomain = item?.domain_id || item?.domain;
    triggerMicrolearning({
      query,
      sourceItemId: item?.question_id,
      sourceNodeId,
      sourceDomain,
    }).then(resp => {
      logEvent('review_research_triggered', {
        query,
        card_id: resp.id,
        source_item: item?.question_id,
        source_domain: sourceDomain,
      });
    }).catch(e => {
      console.warn('[review] research trigger failed:', e);
    });
  };

  // Log each new card shown
  React.useEffect(() => {
    const item = items[currentIndex];
    if (item) logCardShown(item);
  }, [currentIndex, items.length]);

  const currentItem = items[currentIndex];
  const reviewedCount = currentIndex;
  const dueCount = streamMeta.due_count ?? 0;
  const totalCandidates = streamMeta.total_candidates ?? 0;
  const domainCount = Object.keys(streamMeta.domain_counts || {}).length;

  return (
    <View style={s.container}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView ref={scrollRef} contentContainerStyle={s.content}>
        {/* ── Compact status bar ── */}
        {!loading && items.length > 0 && (
          <View style={s.statusBar}>
            <Text style={s.statusText}>
              {dueCount > 0 ? `${dueCount} due` : 'All caught up'}
              {domainCount > 0 ? ` \u00B7 ${domainCount} domains` : ''}
            </Text>
            <Text style={s.statusCount}>{reviewedCount}/{items.length}</Text>
          </View>
        )}

        {/* ── Card stream ──────────────────────────────────────── */}
        {loading && (
          <View style={s.loadingContainer}>
            <ActivityIndicator size="small" color={colors.rubric} />
            <Text style={s.loadingText}>Loading review...</Text>
          </View>
        )}

        {error ? <Text style={s.errorText}>{error}</Text> : null}

        {!loading && items.length === 0 && (
          <View style={s.emptyState}>
            <Text style={s.emptyTitle}>{'\u2726'} All caught up</Text>
            <Text style={s.emptySubtitle}>
              No review items due. Keep reading to grow your knowledge pool.
            </Text>
          </View>
        )}

        {currentItem && (
          <Animated.View style={{ opacity: fadeAnim }}>
            {currentItem.type === 'aspect' ? (
              <AspectCard
                key={currentItem.card_id || `aspect-${currentIndex}`}
                card={currentItem as unknown as AspectCardData}
                onComplete={(results) => {
                  logEvent('aspect_card_complete', {
                    card_id: currentItem.card_id,
                    results: results.map(r => ({ id: r.position_id, score: r.score })),
                    knew: results.filter(r => r.score === 'knew').length,
                    total: results.length,
                  });
                  if (currentItem.card_id) {
                    gradeStructuralCard(
                      currentItem.card_id,
                      results.map(r => ({ position_id: r.position_id, score: r.score })),
                    ).catch(e => console.warn('[structural grade]', e));
                  }
                  animateTransition(() => {
                    setCurrentIndex(i => i + 1);
                    maybeLoadMore();
                  });
                }}
              />
            ) : currentItem.type === 'sequence' ? (
              <SequenceCard
                key={currentItem.card_id || `seq-${currentIndex}`}
                card={currentItem as unknown as SequenceCardData}
                onComplete={(results) => {
                  logEvent('sequence_card_complete', {
                    card_id: currentItem.card_id,
                    results: results.map(r => ({ id: r.position_id, score: r.score })),
                    knew: results.filter(r => r.score === 'knew').length,
                    total: results.length,
                  });
                  if (currentItem.card_id) {
                    gradeStructuralCard(
                      currentItem.card_id,
                      results.map(r => ({ position_id: r.position_id, score: r.score })),
                    ).catch(e => console.warn('[structural grade]', e));
                  }
                  animateTransition(() => {
                    setCurrentIndex(i => i + 1);
                    maybeLoadMore();
                  });
                }}
              />
            ) : currentItem.type === 'synchronic' ? (
              <SynchronicCard
                key={currentItem.card_id || `sync-${currentIndex}`}
                card={currentItem as unknown as SynchronicCardData}
                onComplete={(results) => {
                  logEvent('synchronic_card_complete', {
                    card_id: currentItem.card_id,
                    results: results.map(r => ({ id: r.position_id, score: r.score })),
                    knew: results.filter(r => r.score === 'knew').length,
                    total: results.length,
                  });
                  if (currentItem.card_id) {
                    gradeStructuralCard(
                      currentItem.card_id,
                      results.map(r => ({ position_id: r.position_id, score: r.score })),
                    ).catch(e => console.warn('[structural grade]', e));
                  }
                  animateTransition(() => {
                    setCurrentIndex(i => i + 1);
                    maybeLoadMore();
                  });
                }}
              />
            ) : currentItem.type === 'cast' ? (
              <CastCard
                key={currentItem.card_id || `cast-${currentIndex}`}
                card={currentItem as unknown as CastCardData}
                onComplete={(results) => {
                  logEvent('cast_card_complete', {
                    card_id: currentItem.card_id,
                    results: results.map(r => ({ id: r.position_id, score: r.score })),
                    knew: results.filter(r => r.score === 'knew').length,
                    total: results.length,
                  });
                  if (currentItem.card_id) {
                    gradeStructuralCard(
                      currentItem.card_id,
                      results.map(r => ({ position_id: r.position_id, score: r.score })),
                    ).catch(e => console.warn('[structural grade]', e));
                  }
                  animateTransition(() => {
                    setCurrentIndex(i => i + 1);
                    maybeLoadMore();
                  });
                }}
              />
            ) : currentItem.type === 'causal' ? (
              <CausalChainCard
                key={currentItem.card_id || `causal-${currentIndex}`}
                card={currentItem as unknown as CausalChainCardData}
                onComplete={(results) => {
                  logEvent('causal_card_complete', {
                    card_id: currentItem.card_id,
                    results: results.map(r => ({ id: r.position_id, score: r.score })),
                    knew: results.filter(r => r.score === 'knew').length,
                    total: results.length,
                  });
                  if (currentItem.card_id) {
                    gradeStructuralCard(
                      currentItem.card_id,
                      results.map(r => ({ position_id: r.position_id, score: r.score })),
                    ).catch(e => console.warn('[structural grade]', e));
                  }
                  animateTransition(() => {
                    setCurrentIndex(i => i + 1);
                    maybeLoadMore();
                  });
                }}
              />
            ) : currentItem.type === 'entity_intro' ? (
              <EntityIntroCard
                key={`intro-${currentItem.entity_id || currentIndex}`}
                item={currentItem}
                onContinue={handleEntityIntroContinue}
              />
            ) : currentItem.type === 'microlearning' ? (
              <MicrolearningCard
                key={currentItem.question_id || `ml-${currentIndex}`}
                item={currentItem}
                onResult={(quizId, result) => handleQuizResult(quizId, result)}
                onComplete={() => handleSkip(currentItem)}
                onDismissCard={() => handleDismissCard(currentItem)}
                onDismissQuiz={handleDismissQuiz}
                onFlagInaccurate={handleFlagInaccurate}
                onResearch={(q) => handleResearch(q, currentItem)}
                onEntityTap={setActiveEntityId}
                onDateTap={handleDateTap}
              />
            ) : currentItem.type === 'microlearning_quiz' ? (
              <MicrolearningQuizCard
                key={currentItem.question_id || `mlq-${currentIndex}`}
                item={currentItem}
                onResult={(result, rtMs) => handleResult(currentItem, result, rtMs)}
                onSkip={() => handleSkip(currentItem)}
                onSuspendFact={handleSuspendFact}
                onFlagInaccurate={handleFlagInaccurate}
                onResearch={(q) => handleResearch(q, currentItem)}
                onEntityTap={setActiveEntityId}
                onDateTap={handleDateTap}
              />
            ) : (
              <ReviewCard
                key={currentItem.question_id || `q-${currentIndex}`}
                item={currentItem}
                onResult={(result) => handleResult(currentItem, result)}
                onSkip={() => handleSkip(currentItem)}
                onSuspend={() => handleSuspend(currentItem)}
                onResearch={(q) => handleResearch(q, currentItem)}
                onEntityTap={setActiveEntityId}
                onDateTap={handleDateTap}
              />
            )}
          </Animated.View>
        )}

        {!loading && !currentItem && items.length > 0 && (
          <View style={s.emptyState}>
            <Text style={s.emptyTitle}>{'\u2726'} End of stream</Text>
            <Text style={s.emptySubtitle}>{reviewedCount} cards reviewed</Text>
            <Pressable style={s.newSessionBtn} onPress={() => {
              gradedIdsRef.current.clear();
              loadStream(true);
            }}>
              <Text style={s.newSessionText}>Refresh</Text>
            </Pressable>
          </View>
        )}

        {loadingMore && (
          <View style={s.loadingMoreRow}>
            <ActivityIndicator size="small" color={colors.textMuted} />
          </View>
        )}
      </ScrollView>
      </KeyboardAvoidingView>

      {/* Floating mic button */}
      <Pressable
        style={s.fab}
        onPress={() => {
          logEvent('review_fab_voice_tap');
          router.push('/voice-capture' as any);
        }}
        hitSlop={8}
      >
        <Text style={s.fabIcon}>{'\uD83C\uDF99'}</Text>
      </Pressable>

      <EntitySheet entityId={activeEntityId} onClose={() => setActiveEntityId(null)}
        onExploreEntity={handleExploreEntity} />

      <Modal
        visible={flagTargetCardId !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setFlagTargetCardId(null)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={fim.backdrop}
        >
          <Pressable style={fim.backdropTouch} onPress={() => setFlagTargetCardId(null)} />
          <View style={fim.sheet}>
            <Text style={fim.title}>Flag as inaccurate</Text>
            <Text style={fim.subtitle}>
              What's wrong? (optional — helps the pipeline learn)
            </Text>
            <TextInput
              value={flagReason}
              onChangeText={setFlagReason}
              placeholder="e.g. date is off by 2 years"
              placeholderTextColor="rgba(139,115,85,0.5)"
              style={fim.input}
              multiline
              maxLength={300}
              autoFocus
            />
            <View style={fim.actions}>
              <Pressable style={fim.btnCancel} onPress={() => setFlagTargetCardId(null)}>
                <Text style={fim.btnCancelText}>Cancel</Text>
              </Pressable>
              <Pressable style={fim.btnFlag} onPress={confirmFlagInaccurate}>
                <Text style={fim.btnFlagText}>Flag</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────

const cs = StyleSheet.create({
  card: {
    marginHorizontal: layout.screenPadding, marginBottom: 20, paddingVertical: 16,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  typeBadge: { backgroundColor: colors.ink, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  typeBadgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  domainLabel: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, flex: 1 },
  relatedFactBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, paddingHorizontal: 10, marginBottom: 4, backgroundColor: 'rgba(42,122,74,0.04)', borderRadius: 4, borderLeftWidth: 2, borderLeftColor: colors.claimNew },
  relatedFactTested: { backgroundColor: 'transparent', borderLeftColor: colors.rule },
  relatedFactType: { fontFamily: fonts.uiMedium, fontSize: 9, color: colors.claimNew, textTransform: 'uppercase', letterSpacing: 0.3, minWidth: 40, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  relatedFactText: { fontFamily: fonts.reading, fontSize: 13, color: colors.textBody, flex: 1 },
  originBadge: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted, letterSpacing: 0.3 },
  menuDotsBtn: { minWidth: 36, minHeight: 36, alignItems: 'center', justifyContent: 'center' },
  menuDots: { fontFamily: fonts.ui, fontSize: 18, color: colors.textMuted },
  menuDropdown: { backgroundColor: colors.parchmentDark, borderWidth: 1, borderColor: colors.rule, borderRadius: 6, paddingVertical: 4, marginBottom: 12, ...(Platform.OS === 'web' ? { boxShadow: '0 2px 8px rgba(0,0,0,0.06)' } as any : { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 6, elevation: 2 }) },
  menuDropdownItem: { paddingVertical: 10, paddingHorizontal: 14 },
  menuDropdownText: { fontFamily: fonts.ui, fontSize: 13, color: colors.textSecondary },
  nodeTitle: { fontFamily: fonts.bodyItalic, fontSize: 12, color: colors.textSecondary, marginBottom: 8, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  nodeTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  timelineLink: { paddingVertical: 2, paddingHorizontal: 6 },
  timelineLinkText: { fontFamily: fonts.ui, fontSize: 10, color: colors.rubric },
  question: { fontFamily: fonts.reading, fontSize: 18, lineHeight: 26, color: colors.ink, marginBottom: 16 },
  actionRow: { flexDirection: 'row', gap: 10 },
  revealButton: { flex: 1, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4, paddingVertical: 12, alignItems: 'center' },
  revealText: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric },
  skipButton: { paddingHorizontal: 16, paddingVertical: 12, borderRadius: 4, alignItems: 'center', justifyContent: 'center' },
  skipText: { fontFamily: fonts.ui, fontSize: 13, color: colors.textMuted },
  shortAnswerBox: { marginBottom: 12, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  shortAnswerText: { fontFamily: fonts.displaySemiBold, fontSize: 16, lineHeight: 22, color: colors.ink, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  quickKnewButton: { alignSelf: 'flex-end', marginTop: 8, paddingVertical: 6, paddingHorizontal: 14, borderRadius: 4, borderWidth: 1, borderColor: colors.claimNew, backgroundColor: 'rgba(42,122,74,0.05)' },
  quickKnewText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  answerBox: { borderLeftWidth: 3, borderLeftColor: colors.claimNew, paddingLeft: 14, marginBottom: 14 },
  answerText: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.textBody },
  hookBox: { backgroundColor: 'rgba(139,37,0,0.04)', borderLeftWidth: 2, borderLeftColor: colors.rubric, paddingLeft: 12, paddingVertical: 8, marginBottom: 12, borderRadius: 2 },
  hookLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.rubric, letterSpacing: 0.3, marginBottom: 4, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  hookText: { fontFamily: fonts.readingItalic, fontSize: 14, lineHeight: 20, color: colors.textBody, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  // Session 90 P1.1: small indicators near the question when the learner's capture was hedged
  epistemicHedge: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted, marginTop: -10, marginBottom: 14 },
  epistemicWrong: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric, marginTop: -10, marginBottom: 14 },
  // Session 90 P1.2: prominent correction block when the short answer contradicts ground truth
  correctionBox: {
    borderWidth: 1, borderColor: colors.rubric,
    backgroundColor: 'rgba(139,37,0,0.04)',
    borderRadius: 4, padding: 12, marginBottom: 14,
  },
  correctionLabel: {
    fontFamily: fonts.uiMedium, fontSize: 10, color: colors.rubric,
    letterSpacing: 0.5, textTransform: 'uppercase' as const, marginBottom: 2, marginTop: 2,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  correctionUserSaid: { fontFamily: fonts.reading, fontSize: 14, color: colors.textBody, marginBottom: 8, textDecorationLine: 'line-through' as const },
  correctionActually: { fontFamily: fonts.reading, fontSize: 15, color: colors.ink, marginBottom: 8 },
  correctionWhy: { fontFamily: fonts.readingItalic, fontSize: 13, lineHeight: 19, color: colors.textSecondary, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  anchorBox: { marginBottom: 14 },
  anchorText: { fontFamily: fonts.ui, fontSize: 12, color: colors.textSecondary, lineHeight: 18, marginBottom: 2 },
  contextText: { fontFamily: fonts.readingItalic, fontSize: 12, lineHeight: 18, color: colors.textMuted, marginBottom: 14, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  mapLinkRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 14 },
  mapLinkText: { fontFamily: fonts.ui, fontSize: 13, color: colors.info, textDecorationLine: 'underline' },
  gradeRow: { flexDirection: 'row', gap: 8 },
  gradeButton: { flex: 1, paddingVertical: 10, borderRadius: 4, alignItems: 'center', borderWidth: 1 },
  gradeCorrect: { borderColor: colors.claimNew, backgroundColor: 'rgba(42,122,74,0.05)' },
  gradeCorrectText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  gradePartial: { borderColor: colors.textMuted, backgroundColor: 'rgba(176,168,152,0.08)' },
  gradePartialText: { fontFamily: fonts.ui, fontSize: 12, color: colors.textSecondary },
  gradeWrong: { borderColor: colors.rubric, backgroundColor: 'rgba(139,37,0,0.05)' },
  gradeWrongText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  responded: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.claimNew, textAlign: 'center', paddingVertical: 12, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  followUpSection: { marginTop: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  followUpLabel: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.textMuted, letterSpacing: 0.3, marginBottom: 8, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  followUpBtn: { paddingVertical: 8, paddingHorizontal: 12, marginBottom: 6, borderLeftWidth: 2, borderLeftColor: 'rgba(139,37,0,0.2)', backgroundColor: 'rgba(139,37,0,0.02)', borderRadius: 2 },
  followUpBtnTapped: { borderLeftColor: colors.textMuted, backgroundColor: 'rgba(176,168,152,0.06)' },
  generateMoreBtn: { borderLeftColor: 'rgba(139,37,0,0.1)', borderStyle: 'dashed' as const, marginTop: 4 },
  quizSugBtn: { paddingVertical: 6, paddingHorizontal: 12, marginBottom: 4, borderLeftWidth: 2, borderLeftColor: 'rgba(42,122,74,0.25)', backgroundColor: 'rgba(42,122,74,0.03)', borderRadius: 2 },
  quizSugDone: { borderLeftColor: colors.textMuted, backgroundColor: 'transparent' },
  quizSugText: { fontFamily: fonts.reading, fontSize: 13, lineHeight: 18, color: colors.claimNew },
  followUpText: { fontFamily: fonts.reading, fontSize: 13, lineHeight: 18, color: colors.rubric },
  followUpTextTapped: { color: colors.textMuted, fontFamily: fonts.readingItalic, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
});

const ml = StyleSheet.create({
  badge: { backgroundColor: '#2a4a6a', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  badgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  cardTitle: { fontFamily: fonts.displaySemiBold, fontSize: 20, lineHeight: 26, color: colors.ink, marginBottom: 4, marginTop: 4, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  quizCardTitle: { fontFamily: fonts.displaySemiBold, fontSize: 13, color: colors.ink, flex: 1, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  content: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 23, color: colors.textBody, marginBottom: 12 },
  sectionBlock: { marginTop: 10, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(139,37,0,0.08)' },
  sectionHeading: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.rubric, letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 4, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  revealedContent: { borderLeftWidth: 2, borderLeftColor: colors.rule, paddingLeft: 14, marginTop: 12, marginBottom: 14 },
  revealedLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.textMuted, letterSpacing: 0.3, marginBottom: 8, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  topActions: { flexDirection: 'row', gap: 8 },
  topActionBtn: { paddingVertical: 4, paddingHorizontal: 10, borderWidth: 1, borderColor: colors.rule, borderRadius: 3 },
  topActionText: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  dismissBtn: { alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 10, marginTop: 12, borderRadius: 3, borderWidth: 1, borderColor: colors.rule },
  dismissText: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  quizSection: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule, paddingTop: 12, marginBottom: 8 },
  quizSectionLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.textMuted, letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 10, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  quizCard: { marginBottom: 14, paddingBottom: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  quizQuestion: { fontFamily: fonts.reading, fontSize: 16, lineHeight: 23, color: colors.ink, marginBottom: 10 },
  quizActions: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  quizGraded: { paddingVertical: 4, marginBottom: 8 },
  quizDismissed: { paddingVertical: 4, marginBottom: 8, opacity: 0.5 },
  quizDismissedText: { fontFamily: fonts.readingItalic, fontSize: 12, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  bottomActions: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  completeBtn: { paddingVertical: 10, paddingHorizontal: 20, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4, backgroundColor: 'rgba(139,37,0,0.04)' },
  completeBtnText: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric },
});

const ic = StyleSheet.create({
  introBadge: { backgroundColor: '#b8860b', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  introBadgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  introLabel: { fontFamily: fonts.readingItalic, fontSize: 11, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  entityName: { fontFamily: fonts.displaySemiBold, fontSize: 24, color: colors.ink, marginBottom: 2, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  modernName: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textSecondary, marginBottom: 8, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  miniMapWrap: { height: 140, borderRadius: 8, overflow: 'hidden', marginBottom: 14, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.rule },
  description: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.textBody, marginBottom: 12 },
  dateFact: { fontFamily: fonts.ui, fontSize: 12, color: colors.textSecondary, lineHeight: 18, marginBottom: 10 },
  continueBtn: { borderWidth: 1, borderColor: '#b8860b', borderRadius: 4, paddingVertical: 12, alignItems: 'center', backgroundColor: 'rgba(184,134,11,0.04)' },
  continueText: { fontFamily: fonts.body, fontSize: 14, color: '#b8860b' },
});

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: {
    paddingBottom: 60,
    ...(Platform.OS === 'web' ? { maxWidth: layout.readingMeasure + 2 * layout.screenPadding, width: '100%', alignSelf: 'center' as const } : {}),
  },
  loadingContainer: { flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'center', paddingVertical: 40 },
  loadingText: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  errorText: { fontFamily: fonts.reading, fontSize: 14, color: colors.rubric, textAlign: 'center', paddingVertical: 20, paddingHorizontal: layout.screenPadding },
  emptyState: { alignItems: 'center', justifyContent: 'center', padding: 40 },
  emptyTitle: { fontFamily: fonts.displaySemiBold, fontSize: 20, color: colors.ink, marginBottom: 12, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  emptySubtitle: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textSecondary, textAlign: 'center', lineHeight: 20, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  newSessionBtn: { marginHorizontal: layout.screenPadding, marginTop: 8, marginBottom: 24, paddingVertical: 12, borderWidth: 1, borderColor: colors.rule, borderRadius: 4, alignItems: 'center' },
  newSessionText: { fontFamily: fonts.body, fontSize: 14, color: colors.textSecondary },
  loadingMoreRow: { alignItems: 'center', paddingVertical: 16 },
  // Compact status bar
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  statusText: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted },
  statusCount: { fontFamily: fonts.uiMedium, fontSize: 12, color: colors.textSecondary, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  // Floating action button
  fab: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 24 : 16,
    right: 20,
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 4px 12px rgba(0,0,0,0.2)' } as any
      : { shadowColor: '#000', shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.2, shadowRadius: 8, elevation: 6 }),
  },
  fabIcon: { fontSize: 22 },
});

const ab = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'center', alignItems: 'center' },
  sheet: {
    backgroundColor: colors.parchment, borderRadius: 10, width: '90%', maxWidth: 400, maxHeight: '80%',
    paddingTop: 16, paddingHorizontal: 20, paddingBottom: 20,
    ...(Platform.OS === 'web' ? { boxShadow: '0 8px 30px rgba(0,0,0,0.15)' } as any : { shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.15, shadowRadius: 12, elevation: 8 }),
  },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title: { fontFamily: fonts.displaySemiBold, fontSize: 16, color: colors.ink, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  closeBtn: { fontFamily: fonts.ui, fontSize: 16, color: colors.textMuted, padding: 4 },
  scrollBody: { flexShrink: 1 },
  sectionLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.rubric, letterSpacing: 0.5, textTransform: 'uppercase', marginTop: 16, marginBottom: 6, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingVertical: 3 },
  label: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted, flex: 1 },
  value: { fontFamily: fonts.reading, fontSize: 13, color: colors.textBody, flex: 2, textAlign: 'right' },
  detail: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginTop: 2 },
  sourceRow: { marginBottom: 8, paddingLeft: 8, borderLeftWidth: 2, borderLeftColor: colors.rule },
  idText: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted, marginBottom: 4 },
  idRow: { flexDirection: 'row', alignItems: 'center', marginTop: 20, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  idLabel: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  idCode: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 11, color: colors.textSecondary },
});

const fim = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  backdropTouch: { ...StyleSheet.absoluteFillObject },
  sheet: {
    backgroundColor: colors.parchment,
    borderTopLeftRadius: 12, borderTopRightRadius: 12,
    padding: 20, paddingBottom: 28,
  },
  title: { fontFamily: fonts.displaySemiBold, fontSize: 18, color: colors.ink, marginBottom: 6,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  subtitle: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textSecondary, marginBottom: 12,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  input: {
    fontFamily: fonts.reading, fontSize: 15, color: colors.ink,
    borderWidth: 1, borderColor: colors.rule, borderRadius: 6,
    padding: 10, minHeight: 72, textAlignVertical: 'top',
  },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 12, marginTop: 16 },
  btnCancel: { paddingVertical: 10, paddingHorizontal: 16 },
  btnCancelText: { fontFamily: fonts.ui, fontSize: 14, color: colors.textSecondary },
  btnFlag: {
    paddingVertical: 10, paddingHorizontal: 20,
    backgroundColor: colors.rubric, borderRadius: 6,
  },
  btnFlagText: { fontFamily: fonts.uiMedium, fontSize: 14, color: '#fff',
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
});
