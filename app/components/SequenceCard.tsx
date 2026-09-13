import React, { useMemo, useRef, useState } from 'react';
import { Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts, layout } from '../design/tokens';

interface SequencePosition {
  position_id: string;
  position: number;
  question_text: string;
  answer_text: string;
  hook_type: string;
  mnemonic?: string;
  year?: number;
  year_display?: string;
  scale_to_next?: string;
  stability_days: number;
  due_at: number;
  review_count: number;
  last_score?: string;
}

export interface SequenceCardData {
  card_type: 'sequence';
  card_id: string;
  title: string;
  description?: string;
  domain_id: string;
  domain_title: string;
  date_start?: number;
  date_end?: number;
  positions: SequencePosition[];
}

interface PositionResult {
  position_id: string;
  score: 'knew' | 'missed';
  reveal_time_ms: number;
}

interface Props {
  card: SequenceCardData;
  onComplete: (results: PositionResult[]) => void;
  onInteraction?: (event: string, detail: Record<string, unknown>) => void;
}

type SlotState = 'anchor' | 'blank' | 'revealed' | 'knew' | 'missed';

const MAX_BLANKS = 2;

function pickBlanks(positions: SequencePosition[]): Set<string> {
  // Pick the 2 most-due positions as blanks.
  // Prefer positions that are overdue or never-reviewed.
  const now = Date.now();
  const scoreable = positions
    .map(p => ({
      id: p.position_id,
      urgency: p.review_count === 0
        ? Infinity
        : (now - p.due_at) / 86400000, // days overdue (negative = not yet due)
    }))
    .sort((a, b) => b.urgency - a.urgency);

  return new Set(scoreable.slice(0, MAX_BLANKS).map(s => s.id));
}

function formatYear(year?: number, display?: string): string {
  if (display) return display;
  if (year == null) return '?';
  if (year < 0) return `${Math.abs(year)} BC`;
  return `${year} AD`;
}

function formatGap(yearA?: number, yearB?: number): string | null {
  if (yearA == null || yearB == null) return null;
  const gap = Math.abs(yearB - yearA);
  if (gap < 5) return null;
  return `${gap} years`;
}

export default function SequenceCard({ card, onComplete, onInteraction }: Props) {
  const positions = useMemo(
    () => [...card.positions].sort((a, b) => a.position - b.position),
    [card.positions],
  );

  const blankIds = useMemo(() => pickBlanks(positions), [positions]);

  const [states, setStates] = useState<Record<string, SlotState>>(() => {
    const init: Record<string, SlotState> = {};
    for (const p of positions) {
      init[p.position_id] = blankIds.has(p.position_id) ? 'blank' : 'anchor';
    }
    return init;
  });
  const [revealTimes, setRevealTimes] = useState<Record<string, number>>({});
  const fadeAnims = useRef<Record<string, Animated.Value>>({}).current;

  for (const p of positions) {
    if (!fadeAnims[p.position_id]) {
      fadeAnims[p.position_id] = new Animated.Value(
        blankIds.has(p.position_id) ? 0 : 1,
      );
    }
  }

  const blanks = positions.filter(p => blankIds.has(p.position_id));
  const allBlanksRevealed = blanks.every(
    p => states[p.position_id] !== 'blank',
  );
  const allGraded = blanks.every(
    p => states[p.position_id] === 'knew' || states[p.position_id] === 'missed',
  );
  const knewCount = blanks.filter(p => states[p.position_id] === 'knew').length;
  const missedBlanks = blanks.filter(p => states[p.position_id] === 'missed');

  const domainLabel = (card.domain_title || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .slice(0, 40);

  const animateReveal = (positionId: string) => {
    fadeAnims[positionId].setValue(0);
    Animated.timing(fadeAnims[positionId], {
      toValue: 1,
      duration: 250,
      useNativeDriver: true,
    }).start();
  };

  const revealOne = (positionId: string) => {
    onInteraction?.('position_revealed', { position_id: positionId });
    setStates(prev => ({ ...prev, [positionId]: 'revealed' }));
    setRevealTimes(prev => ({ ...prev, [positionId]: Date.now() }));
    animateReveal(positionId);
  };

  const revealAll = () => {
    const now = Date.now();
    const updates: Record<string, SlotState> = {};
    const times: Record<string, number> = {};
    for (const p of blanks) {
      if (states[p.position_id] === 'blank') {
        onInteraction?.('position_revealed', { position_id: p.position_id, reveal_all: true });
        updates[p.position_id] = 'revealed';
        times[p.position_id] = now;
        animateReveal(p.position_id);
      }
    }
    setStates(prev => ({ ...prev, ...updates }));
    setRevealTimes(prev => ({ ...prev, ...times }));
  };

  const grade = (positionId: string, score: 'knew' | 'missed') => {
    onInteraction?.('position_graded', { position_id: positionId, score });
    setStates(prev => ({ ...prev, [positionId]: score }));
  };

  const handleContinue = () => {
    const now = Date.now();
    const results: PositionResult[] = blanks.map(p => ({
      position_id: p.position_id,
      score: states[p.position_id] === 'knew' ? 'knew' as const : 'missed' as const,
      reveal_time_ms: revealTimes[p.position_id]
        ? now - revealTimes[p.position_id]
        : 0,
    }));
    onComplete(results);
  };

  const dateRange = card.date_start != null && card.date_end != null
    ? `${formatYear(card.date_start)} \u2014 ${formatYear(card.date_end)}`
    : '';

  return (
    <View style={st.card}>
      {/* Header */}
      <View style={st.headerRow}>
        <View style={st.badge}>
          <Text style={st.badgeText}>Sequence</Text>
        </View>
        <Text style={st.domainLabel} numberOfLines={1}>{domainLabel}</Text>
      </View>

      <Text style={st.title}>{card.title}</Text>
      {dateRange ? <Text style={st.dateRange}>{dateRange}</Text> : null}

      {/* Know All button for blanks */}
      {!allBlanksRevealed && (
        <View style={st.promptRow}>
          <Text style={st.prompt}>Fill in the timeline</Text>
          <Pressable style={st.knowAllBtn} onPress={revealAll}>
            <Text style={st.knowAllText}>{onInteraction ? "Vis alle svar" : "Know All"}</Text>
          </Pressable>
        </View>
      )}

      {/* Timeline */}
      <View style={st.timeline}>
        {positions.map((p, i) => {
          const state = states[p.position_id];
          const isBlank = blankIds.has(p.position_id);
          const yearStr = formatYear(p.year, p.year_display);
          const isLast = i === positions.length - 1;

          return (
            <View key={p.position_id} style={st.milestoneRow}>
              {/* Timeline connector */}
              <View style={st.timelineGutter}>
                <View style={[st.dot, isBlank && state === 'blank' && st.dotBlank, state === 'knew' && st.dotKnew, state === 'missed' && st.dotMissed]} />
                {!isLast && <View style={st.connector} />}
              </View>

              {/* Content */}
              <View style={st.milestoneContent}>
                {/* Anchor position — always visible */}
                {!isBlank && (
                  <View style={st.anchorRow}>
                    <Text style={st.yearLabel}>{yearStr}</Text>
                    <Text style={st.anchorText}>{p.answer_text}</Text>
                  </View>
                )}

                {/* Blank — not yet revealed */}
                {isBlank && state === 'blank' && (
                  <View style={st.blankRow}>
                    <Text style={st.yearLabelBlank}>???</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={st.questionText}>{p.question_text}</Text>
                      <Pressable style={st.revealBtn} onPress={() => revealOne(p.position_id)}>
                        <Text style={st.revealBtnText}>Reveal</Text>
                      </Pressable>
                    </View>
                  </View>
                )}

                {/* Blank — revealed, needs grading */}
                {isBlank && state !== 'blank' && state !== 'anchor' && (
                  <Animated.View style={{ opacity: fadeAnims[p.position_id] }}>
                    <View style={st.revealedRow}>
                      <Text style={st.yearLabel}>{yearStr}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={st.answerText}>{p.answer_text}</Text>
                        {state === 'revealed' && (
                          <View style={st.gradeRow}>
                            <Pressable style={st.knewBtn} onPress={() => grade(p.position_id, 'knew')}>
                              <Text style={st.knewBtnText}>Knew</Text>
                            </Pressable>
                            <Pressable style={st.missedBtn} onPress={() => grade(p.position_id, 'missed')}>
                              <Text style={st.missedBtnText}>Missed</Text>
                            </Pressable>
                          </View>
                        )}
                        {state === 'knew' && <Text style={st.gradeLabel}>{'\u2713'} Knew</Text>}
                        {state === 'missed' && <Text style={st.gradeLabelMissed}>{'\u2717'} Missed</Text>}
                      </View>
                    </View>
                  </Animated.View>
                )}

                {/* Hook annotation */}
                {p.mnemonic && state !== 'blank' && (
                  <Text style={st.hookText}>{p.mnemonic}</Text>
                )}

                {/* Scale annotation — gap to next milestone */}
                {!isLast && (() => {
                  const next = positions[i + 1];
                  const gap = formatGap(p.year, next?.year);
                  if (!gap) return null;
                  const label = p.scale_to_next
                    ? `${gap} \u2014 ${p.scale_to_next}`
                    : gap;
                  return <Text style={st.gapLabel}>{'\u2014'} {label} {'\u2014'}</Text>;
                })()}
              </View>
            </View>
          );
        })}
      </View>

      {/* Summary */}
      {allGraded && (
        <View style={st.summaryRow}>
          <Text style={st.summaryText}>
            {knewCount}/{blanks.length} gaps filled correctly
          </Text>
        </View>
      )}

      {/* Mnemonics for missed */}
      {allGraded && missedBlanks.length > 0 && (
        <View style={st.mnemonicSection}>
          {missedBlanks.filter(p => p.mnemonic).map(p => (
            <View key={`mn-${p.position_id}`} style={st.mnemonicBlock}>
              <Text style={st.mnemonicLabel}>
                {p.question_text}
              </Text>
              <Text style={st.mnemonicText}>{p.mnemonic}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Continue */}
      {allGraded && (
        <Pressable style={st.continueBtn} onPress={handleContinue}>
          <Text style={st.continueBtnText}>Continue {'\u2192'}</Text>
        </Pressable>
      )}
    </View>
  );
}

const webBold500 = Platform.OS === 'web' ? { fontWeight: '500' as const } : {};
const webBold600 = Platform.OS === 'web' ? { fontWeight: '600' as const } : {};
const webItalic = Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {};

const st = StyleSheet.create({
  card: { marginHorizontal: layout.screenPadding, marginBottom: 20, paddingVertical: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  badge: { backgroundColor: '#5B6770', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  badgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...webBold500 },
  domainLabel: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, flex: 1 },
  title: { fontFamily: fonts.displaySemiBold, fontSize: 20, lineHeight: 26, color: colors.ink, marginBottom: 4, ...webBold600 },
  dateRange: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted, marginBottom: 12 },
  promptRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  prompt: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textSecondary, ...webItalic },
  knowAllBtn: { paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.claimNew, borderRadius: 4, backgroundColor: 'rgba(42,122,74,0.05)' },
  knowAllText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },

  // Timeline
  timeline: { marginTop: 4 },
  milestoneRow: { flexDirection: 'row', minHeight: 48 },
  timelineGutter: { width: 24, alignItems: 'center' },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.textMuted, marginTop: 6 },
  dotBlank: { backgroundColor: colors.rubric, borderWidth: 2, borderColor: colors.rubric },
  dotKnew: { backgroundColor: colors.claimNew },
  dotMissed: { backgroundColor: colors.rubric },
  connector: { width: 2, flex: 1, backgroundColor: colors.rule, marginVertical: 2 },
  milestoneContent: { flex: 1, paddingLeft: 10, paddingBottom: 14 },

  // Anchor (filled) milestone
  anchorRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  yearLabel: { fontFamily: fonts.uiMedium, fontSize: 12, color: colors.textSecondary, minWidth: 52, ...webBold500 },
  anchorText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.textMuted, flex: 1, opacity: 0.7 },

  // Blank milestone
  blankRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  yearLabelBlank: { fontFamily: fonts.uiMedium, fontSize: 12, color: colors.rubric, minWidth: 52, ...webBold500 },
  questionText: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.ink, marginBottom: 8 },
  revealBtn: { alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4 },
  revealBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },

  // Revealed milestone
  revealedRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  answerText: { fontFamily: fonts.bodyMedium, fontSize: 14, lineHeight: 21, color: colors.textBody, borderLeftWidth: 3, borderLeftColor: colors.claimNew, paddingLeft: 10, marginBottom: 8, ...webBold500 },
  gradeRow: { flexDirection: 'row', gap: 8 },
  knewBtn: { flex: 1, paddingVertical: 8, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.claimNew, backgroundColor: 'rgba(42,122,74,0.05)' },
  knewBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  missedBtn: { flex: 1, paddingVertical: 8, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.rubric, backgroundColor: 'rgba(139,37,0,0.05)' },
  missedBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  gradeLabel: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew, marginTop: 4 },
  gradeLabelMissed: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric, marginTop: 4 },

  // Hook annotation
  hookText: { fontFamily: fonts.readingItalic, fontSize: 11, color: colors.textMuted, marginTop: 2, opacity: 0.8, ...webItalic },
  gapLabel: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted, opacity: 0.5, marginTop: 6, letterSpacing: 0.5 },

  // Summary
  summaryRow: { marginTop: 12, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  summaryText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textSecondary, ...webItalic },
  mnemonicSection: { marginTop: 12 },
  mnemonicBlock: { backgroundColor: 'rgba(139,37,0,0.04)', borderLeftWidth: 2, borderLeftColor: colors.rubric, paddingLeft: 12, paddingVertical: 8, marginBottom: 8, borderRadius: 2 },
  mnemonicLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.rubric, letterSpacing: 0.3, marginBottom: 4, ...webBold500 },
  mnemonicText: { fontFamily: fonts.readingItalic, fontSize: 14, lineHeight: 20, color: colors.textBody, ...webItalic },
  continueBtn: { marginTop: 16, paddingVertical: 12, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4, alignItems: 'center', backgroundColor: 'rgba(139,37,0,0.04)' },
  continueBtnText: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric },
});
