import React, { useMemo, useRef, useState } from 'react';
import { Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts, layout } from '../design/tokens';

interface SynchronicPosition {
  position_id: string;
  position: number;
  question_text: string;
  answer_text: string; // entity name
  hook_type: string;
  mnemonic?: string; // connection text
  question_variants?: {
    domain?: string;
    domain_id?: string;
    label?: string;
    connection?: string;
  };
  stability_days: number;
  due_at: number;
  review_count: number;
  last_score?: string;
}

export interface SynchronicCardData {
  card_type: 'synchronic';
  card_id: string;
  title: string;
  description?: string; // subtitle ("When {anchor}")
  domain_id: string;
  domain_title: string;
  date_anchor?: number;
  positions: SynchronicPosition[];
}

interface PositionResult {
  position_id: string;
  score: 'knew' | 'missed';
  reveal_time_ms: number;
}

interface Props {
  card: SynchronicCardData;
  onComplete: (results: PositionResult[]) => void;
  onInteraction?: (event: string, detail: Record<string, unknown>) => void;
}

type SlotState = 'anchor' | 'blank' | 'revealed' | 'knew' | 'missed';

const MAX_BLANKS = 3;

function pickBlanks(positions: SynchronicPosition[]): Set<string> {
  // First position (index 0) is the anchor — never blank.
  // Pick up to MAX_BLANKS most-due positions from the rest.
  const now = Date.now();
  const candidates = positions
    .filter((_, i) => i > 0) // skip anchor (position 0)
    .map(p => ({
      id: p.position_id,
      urgency: p.review_count === 0
        ? Infinity
        : (now - p.due_at) / 86400000,
    }))
    .sort((a, b) => b.urgency - a.urgency);

  return new Set(candidates.slice(0, MAX_BLANKS).map(s => s.id));
}

function shortDomain(domain?: string): string {
  if (!domain) return '';
  // Strip long suffixes like "(800-300 BC): Political, Military..."
  return domain
    .replace(/\s*\(.*$/, '')
    .replace(/:.*/g, '')
    .trim()
    .slice(0, 30);
}

export default function SynchronicCard({ card, onComplete, onInteraction }: Props) {
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

  return (
    <View style={st.card}>
      {/* Header */}
      <View style={st.headerRow}>
        <View style={st.badge}>
          <Text style={st.badgeText}>Synchronic</Text>
        </View>
      </View>

      <Text style={st.title}>{card.title}</Text>
      {card.description ? <Text style={st.subtitle}>{card.description}</Text> : null}

      {/* Know All button */}
      {!allBlanksRevealed && (
        <View style={st.promptRow}>
          <Text style={st.prompt}>Who was active at this time?</Text>
          <Pressable style={st.knowAllBtn} onPress={revealAll}>
            <Text style={st.knowAllText}>{onInteraction ? "Vis alle svar" : "Know All"}</Text>
          </Pressable>
        </View>
      )}

      {/* Positions — geographic rows by domain */}
      <View style={st.positionList}>
        {positions.map(p => {
          const state = states[p.position_id];
          const isBlank = blankIds.has(p.position_id);
          const qv = p.question_variants || {};
          const domain = shortDomain(qv.domain);
          const label = qv.label || '';
          const connection = qv.connection || p.mnemonic || '';

          return (
            <View key={p.position_id} style={st.posRow}>
              {/* Domain label column */}
              <View style={st.domainCol}>
                <Text style={st.domainText} numberOfLines={1}>{domain}</Text>
              </View>

              {/* Entity column */}
              <View style={st.entityCol}>
                {/* Anchor / known position */}
                {!isBlank && (
                  <View>
                    <Text style={st.entityName}>{p.answer_text}</Text>
                    {label ? <Text style={st.entityLabel}>{label}</Text> : null}
                  </View>
                )}

                {/* Blank — not yet revealed */}
                {isBlank && state === 'blank' && (
                  <View style={st.blankContent}>
                    <Text style={st.questionText}>{p.question_text}</Text>
                    <Pressable style={st.revealBtn} onPress={() => revealOne(p.position_id)}>
                      <Text style={st.revealBtnText}>Reveal</Text>
                    </Pressable>
                  </View>
                )}

                {/* Blank — revealed, needs grading */}
                {isBlank && state !== 'blank' && state !== 'anchor' && (
                  <Animated.View style={{ opacity: fadeAnims[p.position_id] }}>
                    <Text style={st.revealedName}>{p.answer_text}</Text>
                    {label ? <Text style={st.entityLabel}>{label}</Text> : null}
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

                {/* Connection annotation — show after reveal or for anchors on graded cards */}
                {connection && state !== 'blank' && allBlanksRevealed && (
                  <Text style={st.connectionText}>{connection}</Text>
                )}
              </View>
            </View>
          );
        })}
      </View>

      {/* Summary */}
      {allGraded && (
        <View style={st.summaryRow}>
          <Text style={st.summaryText}>
            {knewCount}/{blanks.length} contemporaries identified
          </Text>
        </View>
      )}

      {/* Mnemonics for missed */}
      {allGraded && missedBlanks.length > 0 && (
        <View style={st.mnemonicSection}>
          {missedBlanks.map(p => {
            const qv = p.question_variants || {};
            const connection = qv.connection || p.mnemonic || '';
            return connection ? (
              <View key={`mn-${p.position_id}`} style={st.mnemonicBlock}>
                <Text style={st.mnemonicLabel}>
                  {shortDomain(qv.domain)}: {p.answer_text}
                </Text>
                <Text style={st.mnemonicText}>{connection}</Text>
              </View>
            ) : null;
          })}
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
  badge: { backgroundColor: colors.info, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 2 },
  badgeText: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.parchment, textTransform: 'uppercase', letterSpacing: 0.5, ...webBold500 },
  title: { fontFamily: fonts.displaySemiBold, fontSize: 20, lineHeight: 26, color: colors.ink, marginBottom: 2, ...webBold600 },
  subtitle: { fontFamily: fonts.readingItalic, fontSize: 14, lineHeight: 20, color: colors.textSecondary, marginBottom: 12, ...webItalic },
  promptRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  prompt: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textSecondary, ...webItalic },
  knowAllBtn: { paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.claimNew, borderRadius: 4, backgroundColor: 'rgba(42,122,74,0.05)' },
  knowAllText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },

  // Position rows
  positionList: { marginTop: 4 },
  posRow: { flexDirection: 'row', paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  domainCol: { width: 90, justifyContent: 'flex-start', paddingRight: 8, paddingTop: 2 },
  domainText: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.3, ...webBold500 },
  entityCol: { flex: 1 },

  // Anchor (filled) entity
  entityName: { fontFamily: fonts.bodyMedium, fontSize: 15, lineHeight: 21, color: colors.ink, opacity: 0.7, ...webBold500 },
  entityLabel: { fontFamily: fonts.reading, fontSize: 12, lineHeight: 17, color: colors.textMuted, marginTop: 1 },

  // Blank entity
  blankContent: {},
  questionText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.ink, marginBottom: 6 },
  revealBtn: { alignSelf: 'flex-start', paddingVertical: 5, paddingHorizontal: 12, borderWidth: 1, borderColor: colors.rubric, borderRadius: 4 },
  revealBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },

  // Revealed entity
  revealedName: { fontFamily: fonts.bodyMedium, fontSize: 15, lineHeight: 21, color: colors.ink, borderLeftWidth: 3, borderLeftColor: colors.claimNew, paddingLeft: 10, ...webBold500 },
  gradeRow: { flexDirection: 'row', gap: 8, marginTop: 6 },
  knewBtn: { flex: 1, paddingVertical: 7, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.claimNew, backgroundColor: 'rgba(42,122,74,0.05)' },
  knewBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew },
  missedBtn: { flex: 1, paddingVertical: 7, borderRadius: 4, alignItems: 'center', borderWidth: 1, borderColor: colors.rubric, backgroundColor: 'rgba(139,37,0,0.05)' },
  missedBtnText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  gradeLabel: { fontFamily: fonts.ui, fontSize: 12, color: colors.claimNew, marginTop: 4 },
  gradeLabelMissed: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric, marginTop: 4 },

  // Connection annotation
  connectionText: { fontFamily: fonts.readingItalic, fontSize: 11, lineHeight: 16, color: colors.textMuted, marginTop: 4, opacity: 0.8, ...webItalic },

  // Summary
  summaryRow: { marginTop: 12, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule },
  summaryText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textSecondary, ...webItalic },
  mnemonicSection: { marginTop: 12 },
  mnemonicBlock: { backgroundColor: 'rgba(42,74,106,0.04)', borderLeftWidth: 2, borderLeftColor: colors.info, paddingLeft: 12, paddingVertical: 8, marginBottom: 8, borderRadius: 2 },
  mnemonicLabel: { fontFamily: fonts.uiMedium, fontSize: 10, color: colors.info, letterSpacing: 0.3, marginBottom: 4, ...webBold500 },
  mnemonicText: { fontFamily: fonts.readingItalic, fontSize: 14, lineHeight: 20, color: colors.textBody, ...webItalic },
  continueBtn: { marginTop: 16, paddingVertical: 12, borderWidth: 1, borderColor: colors.info, borderRadius: 4, alignItems: 'center', backgroundColor: 'rgba(42,74,106,0.04)' },
  continueBtnText: { fontFamily: fonts.body, fontSize: 14, color: colors.info },
});
