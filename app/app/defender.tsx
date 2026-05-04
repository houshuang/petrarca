import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { setFeedbackContext } from '../lib/feedback-context';
import {
  startDefenderSession, respondToObjection, listDefenderSessions,
  listCurriculumDomains,
  DefenderObjection, DefenderSessionSummary, DefenderGrade,
  CurriculumDomainInfo,
} from '../lib/defender-api';
import { transcribeAudio } from '../lib/commonplace-api';
import MicButton from '../components/MicButton';

type Phase =
  | 'compose' | 'transcribing_thesis' | 'pending_objections'
  | 'objections' | 'transcribing_response' | 'pending_grade'
  | 'graded' | 'concluded' | 'error' | 'history';

interface RoundLog {
  objections: DefenderObjection[];
  picked?: number;
  response?: string;
  grade?: DefenderGrade;
}

export default function DefenderScreen() {
  const [phase, setPhase] = useState<Phase>('compose');
  const [thesis, setThesis] = useState('');
  const [draft, setDraft] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [contextSummary, setContextSummary] = useState('');
  const [rounds, setRounds] = useState<RoundLog[]>([]);
  const [activeObjections, setActiveObjections] = useState<DefenderObjection[]>([]);
  const [pickedIdx, setPickedIdx] = useState(0);
  const [error, setError] = useState('');
  const [conclusion, setConclusion] = useState('');
  const [history, setHistory] = useState<DefenderSessionSummary[]>([]);
  const [domains, setDomains] = useState<CurriculumDomainInfo[]>([]);
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      logEvent('defender_open');
      setFeedbackContext({ screen: 'defender' });
    }, [])
  );

  const loadHistory = useCallback(async () => {
    try {
      const r = await listDefenderSessions(20);
      setHistory(r.sessions);
    } catch { /* ignore */ }
  }, []);

  const loadDomains = useCallback(async () => {
    try {
      const r = await listCurriculumDomains();
      setDomains(r.curricula || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadHistory(); loadDomains(); }, [loadHistory, loadDomains]);

  const handleThesisAudio = useCallback(async (uri: string) => {
    setPhase('transcribing_thesis');
    setError('');
    try {
      const r = await transcribeAudio(uri);
      if (r.error || !r.transcript) {
        setError(r.error || 'No transcript returned.');
        setPhase('compose');
        return;
      }
      setThesis(prev => (prev.trim() ? `${prev.trim()} ${r.transcript}` : r.transcript));
      setPhase('compose');
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase('compose');
    }
  }, []);

  const handleResponseAudio = useCallback(async (uri: string) => {
    setPhase('transcribing_response');
    setError('');
    try {
      const r = await transcribeAudio(uri);
      if (r.error || !r.transcript) {
        setError(r.error || 'No transcript returned.');
        setPhase('objections');
        return;
      }
      setDraft(prev => (prev.trim() ? `${prev.trim()} ${r.transcript}` : r.transcript));
      setPhase('objections');
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase('objections');
    }
  }, []);

  async function handleStart() {
    if (thesis.trim().length < 10) {
      setError('Assert a substantive thesis (at least one full sentence).');
      return;
    }
    setPhase('pending_objections');
    setError('');
    logEvent('defender_start', {
      thesis_len: thesis.trim().length,
      domain_id: selectedDomainId || undefined,
    });
    try {
      const r = await startDefenderSession(thesis.trim(), {
        domainId: selectedDomainId || undefined,
      });
      if (r.error) {
        setError(r.error);
        setPhase('error');
        return;
      }
      setSessionId(r.session_id);
      setContextSummary(r.context_summary);
      setActiveObjections(r.objections);
      setRounds([{ objections: r.objections }]);
      setPhase('objections');
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase('error');
    }
  }

  async function handleRespond() {
    if (draft.trim().length < 5) {
      setError('Type or record at least a sentence in defense.');
      return;
    }
    setPhase('pending_grade');
    setError('');
    logEvent('defender_respond', {
      session_id: sessionId, response_len: draft.trim().length, objection_index: pickedIdx,
    });
    try {
      const r = await respondToObjection(sessionId, draft.trim(), pickedIdx);
      if (r.error) {
        setError(r.error);
        setPhase('objections');
        return;
      }
      setRounds(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        last.picked = pickedIdx;
        last.response = draft.trim();
        last.grade = r.grade;
        if (r.next_move !== 'conclude' && r.follow_up) {
          updated.push({ objections: [r.follow_up] });
        }
        return updated;
      });
      setDraft('');
      if (r.status === 'concluded') {
        setConclusion(r.conclusion || 'Session concluded.');
        setPhase('concluded');
        loadHistory();
      } else if (r.follow_up) {
        setActiveObjections([r.follow_up]);
        setPickedIdx(0);
        setPhase('graded');
      } else {
        setActiveObjections([]);
        setPhase('graded');
      }
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase('error');
    }
  }

  function handleReset() {
    setPhase('compose');
    setThesis(''); setDraft(''); setSessionId(''); setRounds([]);
    setActiveObjections([]); setPickedIdx(0); setError('');
    setConclusion(''); setContextSummary('');
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Text style={styles.title}>Defender</Text>
          <Text style={styles.subtitle}>
            Assert a thesis. The system challenges; you defend. Geluk-style.
          </Text>
        </View>

        {phase === 'compose' && (
          <View style={styles.section}>
            {domains.length > 0 && (
              <>
                <Text style={styles.label}>Scope (optional)</Text>
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={styles.chipScroll}
                >
                  <Pressable
                    style={[styles.chip, selectedDomainId === null && styles.chipActive]}
                    onPress={() => setSelectedDomainId(null)}
                  >
                    <Text style={[
                      styles.chipText,
                      selectedDomainId === null && styles.chipTextActive,
                    ]}>
                      No scope
                    </Text>
                  </Pressable>
                  {domains.map(d => (
                    <Pressable
                      key={d.id}
                      style={[styles.chip, selectedDomainId === d.id && styles.chipActive]}
                      onPress={() => setSelectedDomainId(d.id)}
                    >
                      <Text style={[
                        styles.chipText,
                        selectedDomainId === d.id && styles.chipTextActive,
                      ]}>
                        {d.title}
                      </Text>
                    </Pressable>
                  ))}
                </ScrollView>
                <Text style={styles.scopeHint}>
                  {selectedDomainId
                    ? 'Objections will be drawn from your facts, voice captures, and entity neighbors in this domain.'
                    : 'Without a scope the LLM reasons from general historical knowledge.'}
                </Text>
              </>
            )}

            <Text style={[styles.label, domains.length > 0 && { marginTop: 18 }]}>
              Your thesis
            </Text>
            <TextInput
              style={styles.textarea}
              multiline
              placeholder={'e.g. "Justinian\'s reconquest was strategically catastrophic — it bankrupted the eastern empire to recover territory it could not hold."'}
              placeholderTextColor={colors.textMuted}
              value={thesis}
              onChangeText={setThesis}
            />
            <View style={styles.actionRow}>
              <MicButton
                onAudio={handleThesisAudio}
                idleLabel="Speak the thesis"
                busyLabel="Transcribing…"
                recordingLabel="Stop"
              />
              <Pressable style={styles.primaryBtn} onPress={handleStart}>
                <Text style={styles.primaryBtnText}>Surface objections →</Text>
              </Pressable>
            </View>
            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <Pressable style={styles.linkBtn} onPress={() => { loadHistory(); setPhase('history'); }}>
              <Text style={styles.linkBtnText}>Past sessions ({history.length})</Text>
            </Pressable>
          </View>
        )}

        {phase === 'transcribing_thesis' && (
          <View style={styles.section}>
            <ActivityIndicator color={colors.rubric} />
            <Text style={styles.helperText}>Transcribing…</Text>
          </View>
        )}

        {phase === 'pending_objections' && (
          <View style={styles.section}>
            <View style={styles.thesisBox}>
              <Text style={styles.thesisLabel}>Thesis</Text>
              <Text style={styles.thesisText}>{thesis}</Text>
            </View>
            <ActivityIndicator color={colors.rubric} />
            <Text style={styles.helperText}>Generating objections (10–20s)…</Text>
          </View>
        )}

        {(phase === 'objections' || phase === 'pending_grade'
          || phase === 'transcribing_response'
          || phase === 'graded' || phase === 'concluded') && (
          <View style={styles.section}>
            <View style={styles.thesisBox}>
              <Text style={styles.thesisLabel}>Thesis</Text>
              <Text style={styles.thesisText}>{thesis}</Text>
              {contextSummary ? (
                <Text style={styles.contextText}>Context: {contextSummary}</Text>
              ) : null}
            </View>

            {rounds.map((r, ri) => (
              <View key={ri} style={styles.roundBox}>
                <Text style={styles.roundLabel}>Round {ri + 1}</Text>
                {r.objections.map((obj, oi) => {
                  const isLastRound = ri === rounds.length - 1;
                  const isPickable = isLastRound && phase === 'objections';
                  const isSelectedNow = isPickable && pickedIdx === oi;
                  const wasPicked = !isLastRound && r.picked === oi;
                  return (
                    <Pressable
                      key={oi}
                      style={[
                        styles.objection,
                        isSelectedNow && styles.objectionPicked,
                        wasPicked && styles.objectionResolved,
                      ]}
                      disabled={!isPickable}
                      onPress={() => setPickedIdx(oi)}
                    >
                      <Text style={styles.angleTag}>{obj.angle.toUpperCase()}</Text>
                      <Text style={styles.objectionText}>{obj.text}</Text>
                      {obj.evidence_hint ? (
                        <Text style={styles.evidenceHint}>↳ {obj.evidence_hint}</Text>
                      ) : null}
                    </Pressable>
                  );
                })}
                {r.response ? (
                  <View style={styles.responseBox}>
                    <Text style={styles.responseLabel}>You</Text>
                    <Text style={styles.responseText}>{r.response}</Text>
                    {r.grade ? (
                      <View style={styles.gradeBox}>
                        <Text style={styles.gradeMeta}>
                          engagement: {r.grade.engagement} · evidence: {r.grade.evidence} · {r.grade.concession}
                        </Text>
                        {r.grade.feedback ? (
                          <Text style={styles.gradeFeedback}>{r.grade.feedback}</Text>
                        ) : null}
                      </View>
                    ) : null}
                  </View>
                ) : null}
              </View>
            ))}

            {phase === 'objections' && (
              <View style={styles.composeBox}>
                <Text style={styles.label}>
                  Defend against objection #{pickedIdx + 1} (tap another to switch)
                </Text>
                <TextInput
                  style={styles.textarea}
                  multiline
                  placeholder="Mount your defense. Bring specific evidence — dates, names, mechanisms."
                  placeholderTextColor={colors.textMuted}
                  value={draft}
                  onChangeText={setDraft}
                />
                <View style={styles.actionRow}>
                  <MicButton
                    onAudio={handleResponseAudio}
                    idleLabel="Speak defense"
                    busyLabel="Transcribing…"
                    recordingLabel="Stop"
                  />
                  <Pressable style={styles.primaryBtn} onPress={handleRespond}>
                    <Text style={styles.primaryBtnText}>Submit defense →</Text>
                  </Pressable>
                </View>
                {error ? <Text style={styles.errorText}>{error}</Text> : null}
              </View>
            )}

            {phase === 'transcribing_response' && (
              <View style={styles.composeBox}>
                <ActivityIndicator color={colors.rubric} />
                <Text style={styles.helperText}>Transcribing your defense…</Text>
              </View>
            )}

            {phase === 'pending_grade' && (
              <View style={styles.composeBox}>
                <ActivityIndicator color={colors.rubric} />
                <Text style={styles.helperText}>Grading and surfacing follow-up (10–20s)…</Text>
              </View>
            )}

            {phase === 'graded' && activeObjections.length > 0 && (
              <View style={styles.composeBox}>
                <Pressable style={styles.primaryBtn} onPress={() => setPhase('objections')}>
                  <Text style={styles.primaryBtnText}>Defend the next objection →</Text>
                </Pressable>
              </View>
            )}

            {phase === 'concluded' && (
              <View style={styles.conclusionBox}>
                <Text style={styles.conclusionLabel}>Session concluded</Text>
                <Text style={styles.conclusionText}>{conclusion}</Text>
                <Pressable style={styles.linkBtn} onPress={handleReset}>
                  <Text style={styles.linkBtnText}>New thesis</Text>
                </Pressable>
              </View>
            )}
          </View>
        )}

        {phase === 'error' && (
          <View style={styles.section}>
            <Text style={styles.errorText}>{error || 'Something went wrong.'}</Text>
            <Pressable style={styles.primaryBtn} onPress={handleReset}>
              <Text style={styles.primaryBtnText}>Start over</Text>
            </Pressable>
          </View>
        )}

        {phase === 'history' && (
          <View style={styles.section}>
            <View style={styles.headerRow}>
              <Text style={styles.label}>Past sessions</Text>
              <Pressable onPress={() => setPhase('compose')}>
                <Text style={styles.linkBtnText}>← back</Text>
              </Pressable>
            </View>
            {history.length === 0 ? (
              <Text style={styles.helperText}>No sessions yet.</Text>
            ) : (
              history.map(s => (
                <View key={s.id} style={styles.historyRow}>
                  <Text style={styles.historyThesis} numberOfLines={2}>{s.thesis}</Text>
                  <Text style={styles.historyMeta}>
                    {s.status} · {s.rounds} round{s.rounds === 1 ? '' : 's'} ·{' '}
                    {new Date(s.created_at).toLocaleDateString()}
                  </Text>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: { paddingBottom: 60 },
  header: { paddingHorizontal: layout.screenPadding, paddingTop: 12, paddingBottom: 8 },
  title: { ...type.screenTitle, color: colors.ink },
  subtitle: { ...type.screenSubtitle, color: colors.textMuted, marginTop: 2 },

  section: { paddingHorizontal: layout.screenPadding, paddingTop: 16 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },

  label: {
    fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.textSecondary,
    marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5,
  },
  textarea: {
    minHeight: 100, padding: 12,
    backgroundColor: colors.parchmentDark,
    borderColor: colors.rule, borderWidth: StyleSheet.hairlineWidth, borderRadius: 6,
    fontFamily: fonts.reading, fontSize: 14.5, lineHeight: 21,
    color: colors.ink, textAlignVertical: 'top',
  },
  actionRow: {
    flexDirection: 'row', gap: 12, marginTop: 12,
    flexWrap: 'wrap', alignItems: 'center',
  },
  primaryBtn: {
    paddingVertical: 12, paddingHorizontal: 18,
    backgroundColor: colors.rubric, borderRadius: 6, alignItems: 'center', justifyContent: 'center',
  },
  primaryBtnText: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 14 },
  linkBtn: { marginTop: 16, alignSelf: 'flex-start' },
  linkBtnText: { color: colors.rubric, fontFamily: fonts.bodyMedium, fontSize: 13 },

  helperText: { color: colors.textMuted, fontFamily: fonts.reading, fontSize: 13, marginTop: 8 },
  errorText: {
    color: colors.danger, fontFamily: fonts.bodyMedium, fontSize: 13, marginTop: 8,
  },

  chipScroll: { gap: 6, paddingRight: 12 },
  chip: {
    paddingVertical: 6, paddingHorizontal: 10,
    backgroundColor: colors.parchmentDark,
    borderColor: colors.rule, borderWidth: StyleSheet.hairlineWidth, borderRadius: 14,
  },
  chipActive: { backgroundColor: colors.rubric, borderColor: colors.rubric },
  chipText: { fontFamily: fonts.ui, fontSize: 12, color: colors.textBody },
  chipTextActive: { color: '#fff' },
  scopeHint: {
    fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted,
    marginTop: 8, fontStyle: 'italic',
  },

  thesisBox: {
    padding: 12, marginBottom: 16,
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 3, borderLeftColor: colors.rubric, borderRadius: 4,
  },
  thesisLabel: {
    fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
  },
  thesisText: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.ink },
  contextText: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginTop: 6 },

  roundBox: { marginBottom: 16 },
  roundLabel: {
    fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8,
  },
  objection: {
    padding: 12, marginBottom: 8,
    backgroundColor: colors.parchmentDark,
    borderColor: colors.rule, borderWidth: StyleSheet.hairlineWidth, borderRadius: 4,
  },
  objectionPicked: {
    borderColor: colors.rubric, borderWidth: 1.5, backgroundColor: colors.parchmentHover,
  },
  objectionResolved: { opacity: 0.55 },
  angleTag: {
    fontFamily: fonts.ui, fontSize: 10, color: colors.rubric,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
  },
  objectionText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.ink },
  evidenceHint: { fontFamily: fonts.ui, fontSize: 11, color: colors.textSecondary, marginTop: 6 },

  responseBox: {
    marginTop: 12, padding: 12,
    backgroundColor: colors.parchment,
    borderLeftWidth: 2, borderLeftColor: colors.info,
  },
  responseLabel: {
    fontFamily: fonts.bodyMedium, fontSize: 10, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
  },
  responseText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.textBody },
  gradeBox: { marginTop: 8, paddingTop: 8, borderTopColor: colors.rule, borderTopWidth: StyleSheet.hairlineWidth },
  gradeMeta: { fontFamily: fonts.ui, fontSize: 11, color: colors.textSecondary },
  gradeFeedback: {
    fontFamily: fonts.reading, fontSize: 13, fontStyle: 'italic',
    color: colors.textBody, marginTop: 4, lineHeight: 19,
  },

  composeBox: { marginTop: 16 },
  conclusionBox: {
    marginTop: 16, padding: 14,
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 3, borderLeftColor: colors.success, borderRadius: 4,
  },
  conclusionLabel: {
    fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.success,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6,
  },
  conclusionText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 21, color: colors.ink },

  historyRow: {
    paddingVertical: 12,
    borderBottomColor: colors.rule, borderBottomWidth: StyleSheet.hairlineWidth,
  },
  historyThesis: { fontFamily: fonts.reading, fontSize: 14, color: colors.ink, lineHeight: 20 },
  historyMeta: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginTop: 4 },
});
