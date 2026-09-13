import React, { useRef, useState } from 'react';
import { Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts, layout } from '../design/tokens';

interface CausalPosition {
  position_id: string;
  position: number;
  question_text: string;
  answer_text: string; // event description
  question_variants: {
    event: string;
    year_display: string;
    connection_to_next: string | null;
  };
  stability_days: number;
  due_at: number;
  review_count?: number;
  last_score?: string;
}

export interface CausalChainCardData {
  card_type: 'causal';
  card_id: string;
  title: string;
  description: string; // theme
  domain_id: string;
  domain_title: string;
  positions: CausalPosition[];
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
  card: CausalChainCardData;
  onComplete: (results: PositionResult[]) => void;
  onInteraction?: (event: string, detail: Record<string, unknown>) => void;
}

type PositionState = 'anchor' | 'hidden' | 'revealed' | 'knew' | 'missed';

export default function CausalChainCard({ card, onComplete, onInteraction }: Props) {
  const positions = [...card.positions].sort((a, b) => a.position - b.position);

  // First link is always anchor (context), pick 2 blanks by urgency from the rest
  const blankIds = new Set<string>();
  if (positions.length > 1) {
    const restByUrgency = positions.slice(1).sort((a, b) => (a.due_at || 0) - (b.due_at || 0));
    const numBlanks = Math.min(2, restByUrgency.length);
    for (let i = 0; i < numBlanks; i++) {
      blankIds.add(restByUrgency[i].position_id);
    }
  }

  const [states, setStates] = useState<Record<string, PositionState>>(() => {
    const init: Record<string, PositionState> = {};
    for (let i = 0; i < positions.length; i++) {
      const p = positions[i];
      if (i === 0) {
        init[p.position_id] = 'anchor'; // first link always shown
      } else {
        init[p.position_id] = blankIds.has(p.position_id) ? 'hidden' : 'anchor';
      }
    }
    return init;
  });
  const [revealTimes, setRevealTimes] = useState<Record<string, number>>({});
  const fadeAnims = useRef<Record<string, Animated.Value>>({}).current;

  for (const p of positions) {
    if (!fadeAnims[p.position_id]) {
      fadeAnims[p.position_id] = new Animated.Value(0);
    }
  }

  const domainLabel = (card.domain_title || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .slice(0, 40);

  const blanks = positions.filter(p => blankIds.has(p.position_id));
  const allBlanksGraded = blanks.every(
    p => states[p.position_id] === 'knew' || states[p.position_id] === 'missed',
  );
  const knewCount = blanks.filter(p => states[p.position_id] === 'knew').length;

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

  // Connection text is shown when BOTH adjacent links are visible (not hidden)
  const isVisible = (posId: string) => {
    const s = states[posId];
    return s !== 'hidden';
  };

  return (
    <View style={st.card}>
      {/* Header */}
      <View style={st.headerRow}>
        <View style={st.badge}>
          <Text style={st.badgeText}>{'\u26D3'} Causal</Text>
        </View>
        <Text style={st.domainLabel} numberOfLines={1}>{domainLabel}</Text>
      </View>

      {/* Title + theme */}
      <Text style={st.title}>{card.title}</Text>
      {card.description ? (
        <Text style={st.theme}>{card.description}</Text>
      ) : null}

      {/* Chain links */}
      {positions.map((p, i) => {
        const state = states[p.position_id];
        const qv = p.question_variants || { event: '', year_display: '', connection_to_next: null };
        const isAnchor = state === 'anchor';
        const isLast = i === positions.length - 1;

        // Show connection arrow between this link and the next
        const nextPos = positions[i + 1];
        const showConnection = !isLast && nextPos
          && isVisible(p.position_id) && isVisible(nextPos.position_id)
          && qv.connection_to_next;

        return (
          <View key={p.position_id}>
            {/* Link box */}
            <View style={[st.linkBox, isAnchor && st.linkBoxAnchor]}>
              {isAnchor ? (
                // Shown link
                <View>
                  <View style={st.linkHeader}>
                    <Text style={st.linkEvent}>{qv.event || p.answer_text}</Text>
                    {qv.year_display ? (
                      <Text style={st.linkYear}>{qv.year_display}</Text>
                    ) : null}
                  </View>
                </View>
              ) : state === 'hidden' ? (
                // Blank link
                <View>
                  <Text style={st.blankLabel}>???</Text>
                  <Text style={st.questionText}>{p.question_text}</Text>
                  <Pressable style={st.revealBtn} onPress={() => revealOne(p.position_id)}>
                    <Text style={st.revealBtnText}>Reveal</Text>
                  </Pressable>
                </View>
              ) : (
                // Revealed link
                <Animated.View style={{ opacity: fadeAnims[p.position_id] }}>
                  <View style={st.linkHeader}>
                    <Text style={st.revealedEvent}>{qv.event || p.answer_text}</Text>
                    {qv.year_display ? (
                      <Text style={st.linkYear}>{qv.year_display}</Text>
                    ) : null}
                  </View>

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
                </Animated.View>
              )}
            </View>

            {/* Connection arrow + text */}
            {!isLast && (
              <View style={st.connectionRow}>
                <Text style={st.arrow}>{'\u2193'}</Text>
                {showConnection ? (
                  <Text style={st.connectionText}>{qv.connection_to_next}</Text>
                ) : null}
              </View>
            )}
          </View>
        );
      })}

      {/* Summary */}
      {allBlanksGraded && (
        <View style={st.summaryRow}>
          <Text style={st.summaryText}>
            {knewCount}/{blanks.length} causes identified
          </Text>
        </View>
      )}

      {/* Continue */}
      {allBlanksGraded && (
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
  badge: { backgroundColor: '#8B5E3C', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  badgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...webBold500 },
  domainLabel: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, flex: 1 },
  title: { fontFamily: fonts.displaySemiBold, fontSize: 20, lineHeight: 26, color: colors.ink, marginBottom: 4, ...webBold600 },
  theme: { fontFamily: fonts.readingItalic, fontSize: 14, lineHeight: 20, color: colors.textSecondary, marginBottom: 16, ...webItalic },
  // Link box
  linkBox: { borderWidth: 1, borderColor: colors.rule, borderRadius: 6, padding: 12, backgroundColor: 'rgba(245,240,230,0.5)' },
  linkBoxAnchor: { borderColor: 'rgba(139,94,60,0.3)', backgroundColor: 'rgba(139,94,60,0.04)' },
  linkHeader: { gap: 4 },
  linkEvent: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.ink },
  linkYear: { fontFamily: fonts.uiMedium, fontSize: 12, color: colors.textMuted, ...webBold500 },
  revealedEvent: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.ink, borderLeftWidth: 3, borderLeftColor: '#8B5E3C', paddingLeft: 10 },
  blankLabel: { fontFamily: fonts.bodyMedium, fontSize: 16, color: colors.rubric, marginBottom: 4, ...webBold500 },
  questionText: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.ink, marginBottom: 8 },
  revealBtn: { alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4 },
  revealBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  // Connection
  connectionRow: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 6, paddingLeft: 16, gap: 8 },
  arrow: { fontSize: 18, color: 'rgba(139,94,60,0.5)', lineHeight: 22 },
  connectionText: { fontFamily: fonts.readingItalic, fontSize: 13, lineHeight: 18, color: colors.textSecondary, flex: 1, ...webItalic },
  // Grading
  gradeRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  knewBtn: { flex: 1, paddingVertical: 10, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.claimNew, backgroundColor: 'rgba(42,122,74,0.05)' },
  knewBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  missedBtn: { flex: 1, paddingVertical: 10, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.rubric, backgroundColor: 'rgba(139,37,0,0.05)' },
  missedBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  gradeLabel: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew, marginTop: 4 },
  gradeLabelMissed: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric, marginTop: 4 },
  summaryRow: { marginTop: 12, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  summaryText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textSecondary, ...webItalic },
  continueBtn: { marginTop: 16, paddingVertical: 12, borderWidth: 1, borderColor: '#8B5E3C', borderRadius: 4, alignItems: 'center', backgroundColor: 'rgba(139,94,60,0.04)' },
  continueBtnText: { fontFamily: fonts.body, fontSize: 14, color: '#8B5E3C' },
});
