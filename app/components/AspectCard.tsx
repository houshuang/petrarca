import React, { useRef, useState } from 'react';
import { Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts, layout } from '../design/tokens';

interface AspectPosition {
  position_id: string;
  position: number;
  question_text: string;
  answer_text: string;
  hook_type: string;
  fact_type: string;
  mnemonic?: string;
  mnemonic_type?: string;
  stability_days: number;
  due_at: number;
  review_count: number;
  last_score: string | null;
}

export interface AspectCardData {
  card_type: 'aspect';
  card_id: string;
  title: string;
  domain_id: string;
  domain_title: string;
  node_id: string;
  positions: AspectPosition[];
  provenance?: {
    origin: string;
    review_count: number;
  };
}

interface PositionResult {
  position_id: string;
  score: 'knew' | 'missed';
  reveal_time_ms: number;
}

interface Props {
  card: AspectCardData;
  onComplete: (results: PositionResult[]) => void;
  onInteraction?: (event: string, detail: Record<string, unknown>) => void;
}

type PositionState = 'hidden' | 'revealed' | 'knew' | 'missed';

function formatDueDate(dueMs: number): string {
  const now = Date.now();
  const diffDays = Math.ceil((dueMs - now) / 86400000);
  if (diffDays <= 0) return 'now';
  if (diffDays === 1) return 'tomorrow';
  if (diffDays < 7) {
    const day = new Date(dueMs).toLocaleDateString('en', { weekday: 'long' });
    return day;
  }
  return `${diffDays}d`;
}

export default function AspectCard({ card, onComplete, onInteraction }: Props) {
  const [states, setStates] = useState<Record<string, PositionState>>(() => {
    const init: Record<string, PositionState> = {};
    for (const p of card.positions) init[p.position_id] = 'hidden';
    return init;
  });
  const [revealTimes, setRevealTimes] = useState<Record<string, number>>({});
  const fadeAnims = useRef<Record<string, Animated.Value>>({}).current;

  const positions = [...card.positions].sort((a, b) => a.position - b.position);

  for (const p of positions) {
    if (!fadeAnims[p.position_id]) {
      fadeAnims[p.position_id] = new Animated.Value(0);
    }
  }

  const domainLabel = (card.domain_title || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .slice(0, 40);

  const allRevealed = positions.every(
    p => states[p.position_id] !== 'hidden',
  );
  const allGraded = positions.every(
    p => states[p.position_id] === 'knew' || states[p.position_id] === 'missed',
  );
  const knewCount = positions.filter(p => states[p.position_id] === 'knew').length;
  const missedPositions = positions.filter(p => states[p.position_id] === 'missed');

  // Trust line: show prior mastery before interaction
  const masteredCount = positions.filter(
    p => p.review_count > 0 && p.last_score === 'knew',
  ).length;
  const totalReviewed = positions.filter(p => p.review_count > 0).length;
  const allMastered = masteredCount === positions.length && positions.length > 0;
  const showTrustLine = totalReviewed > 0;

  // Next due position (future, not overdue) for the trust line
  const now = Date.now();
  const futureDue = positions
    .filter(p => p.due_at > now && p.review_count > 0)
    .sort((a, b) => a.due_at - b.due_at);
  const nextDue = futureDue.length > 0 ? futureDue[0] : null;

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
    const updates: Record<string, PositionState> = {};
    const times: Record<string, number> = {};
    for (const p of positions) {
      if (states[p.position_id] === 'hidden') {
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
    const results: PositionResult[] = positions.map(p => ({
      position_id: p.position_id,
      score: states[p.position_id] === 'knew' ? 'knew' as const : 'missed' as const,
      reveal_time_ms: revealTimes[p.position_id]
        ? now - revealTimes[p.position_id]
        : 0,
    }));
    onComplete(results);
  };

  const nextDueInfo = missedPositions.length > 0
    ? missedPositions.reduce((earliest, p) =>
        p.due_at < earliest.due_at ? p : earliest, missedPositions[0])
    : null;

  return (
    <View style={st.card}>
      {/* Header: badge + domain */}
      <View style={st.headerRow}>
        <View style={st.badge}>
          <Text style={st.badgeText}>Aspect</Text>
        </View>
        <Text style={st.domainLabel} numberOfLines={1}>{domainLabel}</Text>
      </View>

      {/* Title */}
      <Text style={st.title}>{card.title}</Text>

      {/* Trust line: prior mastery context */}
      {showTrustLine && (
        <Text style={[st.trustLine, allMastered && st.trustLineGreen]}>
          {allMastered
            ? `All ${positions.length} known`
            : `${masteredCount}/${positions.length} known`}
          {nextDue
            ? ` \u00B7 \u2018${nextDue.question_text}\u2019 due ${formatDueDate(nextDue.due_at)}`
            : allMastered
              ? ` \u00B7 next review ${formatDueDate(Math.min(...positions.map(p => p.due_at)))}`
              : ''}
        </Text>
      )}

      {/* Prompt + Know All */}
      {!allRevealed && (
        <View style={st.promptRow}>
          <Text style={st.prompt}>What do you remember?</Text>
          <Pressable style={st.knowAllBtn} onPress={revealAll}>
            <Text style={st.knowAllText}>{onInteraction ? "Vis alle svar" : "Know All"}</Text>
          </Pressable>
        </View>
      )}

      {/* Positions list */}
      {positions.map((p, i) => {
        const state = states[p.position_id];
        return (
          <View
            key={p.position_id}
            style={[st.positionRow, i > 0 && st.positionBorder]}
          >
            <Text style={st.questionText}>{p.question_text}</Text>

            {state === 'hidden' && (
              <Pressable style={st.revealBtn} onPress={() => revealOne(p.position_id)}>
                <Text style={st.revealBtnText}>Reveal</Text>
              </Pressable>
            )}

            {state !== 'hidden' && (
              <Animated.View style={{ opacity: fadeAnims[p.position_id] }}>
                <Text style={st.answerText}>{p.answer_text}</Text>

                {state === 'revealed' && (
                  <View style={st.gradeRow}>
                    <Pressable
                      style={st.knewBtn}
                      onPress={() => grade(p.position_id, 'knew')}
                    >
                      <Text style={st.knewBtnText}>Knew</Text>
                    </Pressable>
                    <Pressable
                      style={st.missedBtn}
                      onPress={() => grade(p.position_id, 'missed')}
                    >
                      <Text style={st.missedBtnText}>Missed</Text>
                    </Pressable>
                  </View>
                )}

                {state === 'knew' && (
                  <Text style={st.gradeLabel}>{'\u2713'} Knew</Text>
                )}
                {state === 'missed' && (
                  <Text style={st.gradeLabelMissed}>{'\u2717'} Missed</Text>
                )}
              </Animated.View>
            )}
          </View>
        );
      })}

      {/* Summary line */}
      {allGraded && (
        <View style={st.summaryRow}>
          <Text style={st.summaryText}>
            {knewCount}/{positions.length} known
            {nextDueInfo
              ? ` \u00B7 '${nextDueInfo.question_text}' due ${formatDueDate(nextDueInfo.due_at)}`
              : ''}
          </Text>
        </View>
      )}

      {/* Mnemonics for missed positions */}
      {allGraded && missedPositions.length > 0 && (
        <View style={st.mnemonicSection}>
          {missedPositions
            .filter(p => p.mnemonic)
            .map(p => (
              <View key={`mn-${p.position_id}`} style={st.mnemonicBlock}>
                <Text style={st.mnemonicLabel}>
                  Mnemonic for: {p.question_text}
                </Text>
                {p.mnemonic_type && (
                  <Text style={st.mnemonicType}>{p.mnemonic_type}</Text>
                )}
                <Text style={st.mnemonicText}>{p.mnemonic}</Text>
              </View>
            ))}
        </View>
      )}

      {/* Continue button */}
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
  badge: { backgroundColor: colors.warning, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  badgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...webBold500 },
  domainLabel: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, flex: 1 },
  title: { fontFamily: fonts.displaySemiBold, fontSize: 20, lineHeight: 26, color: colors.ink, marginBottom: 4, ...webBold600 },
  trustLine: { fontFamily: fonts.readingItalic, fontSize: 12, color: colors.textMuted, marginBottom: 12, ...webItalic },
  trustLineGreen: { color: colors.claimNew },
  promptRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  prompt: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textSecondary, ...webItalic },
  knowAllBtn: { paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.claimNew, borderRadius: 4, backgroundColor: 'rgba(42,122,74,0.05)' },
  knowAllText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  positionRow: { paddingVertical: 12 },
  positionBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  questionText: { fontFamily: fonts.reading, fontSize: 16, lineHeight: 23, color: colors.ink, marginBottom: 8 },
  revealBtn: { alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4 },
  revealBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  answerText: { fontFamily: fonts.bodyMedium, fontSize: 15, lineHeight: 22, color: colors.textBody, borderLeftWidth: 3, borderLeftColor: colors.claimNew, paddingLeft: 12, marginBottom: 8, ...webBold500 },
  gradeRow: { flexDirection: 'row', gap: 8 },
  knewBtn: { flex: 1, paddingVertical: 10, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.claimNew, backgroundColor: 'rgba(42,122,74,0.05)' },
  knewBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  missedBtn: { flex: 1, paddingVertical: 10, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.rubric, backgroundColor: 'rgba(139,37,0,0.05)' },
  missedBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  gradeLabel: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew, marginTop: 4 },
  gradeLabelMissed: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric, marginTop: 4 },
  summaryRow: { marginTop: 12, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  summaryText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textSecondary, ...webItalic },
  mnemonicSection: { marginTop: 12 },
  mnemonicBlock: { backgroundColor: 'rgba(139,37,0,0.04)', borderLeftWidth: 2, borderLeftColor: colors.rubric, paddingLeft: 12, paddingVertical: 8, marginBottom: 8, borderRadius: 2 },
  mnemonicLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.rubric, letterSpacing: 0.3, marginBottom: 4, ...webBold500 },
  mnemonicType: { fontFamily: fonts.ui, fontSize: 9, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  mnemonicText: { fontFamily: fonts.readingItalic, fontSize: 14, lineHeight: 20, color: colors.textBody, ...webItalic },
  continueBtn: { marginTop: 16, paddingVertical: 12, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4, alignItems: 'center', backgroundColor: 'rgba(139,37,0,0.04)' },
  continueBtnText: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric },
});
