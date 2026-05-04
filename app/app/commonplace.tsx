import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { setFeedbackContext } from '../lib/feedback-context';
import {
  resurfaceFromText, resurfaceFromAudio,
  CommonplaceEcho, ResurfaceResult,
} from '../lib/commonplace-api';
import MicButton from '../components/MicButton';

type Phase = 'compose' | 'transcribing' | 'searching' | 'results' | 'error';

const AGE_OPTIONS = [
  { label: '> 1 month', days: 30 },
  { label: '> 3 months', days: 90 },
  { label: '> 6 months', days: 180 },
  { label: 'No filter', days: 0 },
];

const THRESHOLD_OPTIONS = [
  { label: 'Loose (0.50)', val: 0.50 },
  { label: 'Default (0.55)', val: 0.55 },
  { label: 'Tight (0.65)', val: 0.65 },
];

export default function CommonplaceScreen() {
  const [phase, setPhase] = useState<Phase>('compose');
  const [query, setQuery] = useState('');
  const [transcript, setTranscript] = useState('');
  const [result, setResult] = useState<ResurfaceResult | null>(null);
  const [error, setError] = useState('');
  const [ageDays, setAgeDays] = useState(30);
  const [threshold, setThreshold] = useState(0.55);

  useFocusEffect(
    useCallback(() => {
      logEvent('commonplace_open');
      setFeedbackContext({ screen: 'commonplace' });
    }, [])
  );

  const search = useCallback(async (text: string) => {
    setPhase('searching');
    setError('');
    try {
      const r = await resurfaceFromText(text, {
        minAgeDays: ageDays,
        threshold,
        maxResults: 8,
      });
      if (r.error) {
        setError(r.error);
        setPhase('error');
        return;
      }
      setResult(r);
      logEvent('commonplace_results', {
        echo_count: r.echoes.length,
        candidates: r.meta?.candidates_scanned ?? 0,
        threshold,
        min_age_days: ageDays,
      });
      setPhase('results');
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase('error');
    }
  }, [ageDays, threshold]);

  const handleAudio = useCallback(async (uri: string) => {
    setPhase('transcribing');
    setError('');
    try {
      const r = await resurfaceFromAudio(uri, {
        minAgeDays: ageDays,
        threshold,
        maxResults: 8,
      });
      if (r.error) {
        setError(r.error);
        setPhase('error');
        return;
      }
      if (r.transcript) {
        setTranscript(r.transcript);
        setQuery(r.transcript);
      }
      setResult(r);
      logEvent('commonplace_results', {
        echo_count: r.echoes.length,
        source: 'audio',
        threshold,
        min_age_days: ageDays,
      });
      setPhase('results');
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase('error');
    }
  }, [ageDays, threshold]);

  const handleTextSearch = useCallback(() => {
    if (query.trim().length < 8) {
      setError('Type or speak at least a phrase to search.');
      return;
    }
    search(query.trim());
  }, [query, search]);

  function handleReset() {
    setPhase('compose');
    setQuery('');
    setTranscript('');
    setResult(null);
    setError('');
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Text style={styles.title}>What you said before</Text>
          <Text style={styles.subtitle}>
            Resurface old voice captures that rhyme with what you're thinking now.
          </Text>
        </View>

        {(phase === 'compose' || phase === 'results' || phase === 'error') && (
          <View style={styles.section}>
            <Text style={styles.label}>Prompt</Text>
            <TextInput
              style={styles.textarea}
              multiline
              placeholder={'e.g. "I\'m re-reading about Khomeini\'s return — was the Shah\'s departure inevitable?"'}
              placeholderTextColor={colors.textMuted}
              value={query}
              onChangeText={setQuery}
            />
            <View style={styles.actionRow}>
              <MicButton
                onAudio={handleAudio}
                idleLabel="Speak"
                busyLabel="Transcribing…"
                recordingLabel="Stop"
              />
              <Pressable style={styles.primaryBtn} onPress={handleTextSearch}>
                <Text style={styles.primaryBtnText}>Resurface →</Text>
              </Pressable>
            </View>

            <Text style={[styles.label, { marginTop: 18 }]}>Filters</Text>
            <View style={styles.chipRow}>
              {AGE_OPTIONS.map(opt => (
                <Pressable
                  key={opt.days}
                  style={[styles.chip, ageDays === opt.days && styles.chipActive]}
                  onPress={() => setAgeDays(opt.days)}
                >
                  <Text style={[styles.chipText, ageDays === opt.days && styles.chipTextActive]}>
                    {opt.label}
                  </Text>
                </Pressable>
              ))}
            </View>
            <View style={styles.chipRow}>
              {THRESHOLD_OPTIONS.map(opt => (
                <Pressable
                  key={opt.val}
                  style={[styles.chip, threshold === opt.val && styles.chipActive]}
                  onPress={() => setThreshold(opt.val)}
                >
                  <Text style={[styles.chipText, threshold === opt.val && styles.chipTextActive]}>
                    {opt.label}
                  </Text>
                </Pressable>
              ))}
            </View>

            {error ? <Text style={styles.errorText}>{error}</Text> : null}
          </View>
        )}

        {phase === 'transcribing' && (
          <View style={styles.section}>
            <ActivityIndicator color={colors.rubric} />
            <Text style={styles.helperText}>Transcribing & searching…</Text>
          </View>
        )}

        {phase === 'searching' && (
          <View style={styles.section}>
            <ActivityIndicator color={colors.rubric} />
            <Text style={styles.helperText}>Searching your past captures…</Text>
          </View>
        )}

        {phase === 'results' && result && (
          <View style={styles.section}>
            {transcript ? (
              <View style={styles.transcriptBox}>
                <Text style={styles.transcriptLabel}>You said</Text>
                <Text style={styles.transcriptText}>{transcript}</Text>
              </View>
            ) : null}

            <Text style={styles.metaLine}>
              {result.echoes.length} echo{result.echoes.length === 1 ? '' : 'es'} ·
              {' '}{result.meta?.candidates_scanned ?? '?'} chunks scanned ·
              {' '}threshold {threshold} · age {ageDays === 0 ? 'no filter' : `>${ageDays}d`}
            </Text>

            {result.echoes.length === 0 ? (
              <View style={styles.emptyBox}>
                <Text style={styles.emptyText}>
                  Nothing surfaced. Try lowering the threshold, removing the age filter, or
                  rephrasing your prompt with more specifics.
                </Text>
              </View>
            ) : (
              result.echoes.map(echo => <EchoCard key={echo.chunk_id} echo={echo} />)
            )}

            <Pressable style={styles.linkBtn} onPress={handleReset}>
              <Text style={styles.linkBtnText}>← New prompt</Text>
            </Pressable>
          </View>
        )}

        {phase === 'error' && error ? (
          <View style={styles.section}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function EchoCard({ echo }: { echo: CommonplaceEcho }) {
  const [expanded, setExpanded] = useState(false);
  const date = new Date(echo.transcript_date);
  const dateLabel = date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });

  return (
    <Pressable style={styles.echo} onPress={() => setExpanded(v => !v)}>
      <View style={styles.echoHeader}>
        <Text style={styles.echoMeta}>
          {echo.days_ago}d ago · {dateLabel} · {echo.chunk_type.replace('_', ' ')}
        </Text>
        <Text style={styles.echoSim}>sim {echo.similarity.toFixed(2)}</Text>
      </View>
      {echo.transcript_node_title ? (
        <Text style={styles.echoNode}>{echo.transcript_node_title}</Text>
      ) : null}
      <Text style={styles.echoText}>{echo.chunk_text}</Text>
      {expanded && echo.transcript_excerpt ? (
        <View style={styles.echoExcerptBox}>
          <Text style={styles.echoExcerptLabel}>Surrounding context</Text>
          <Text style={styles.echoExcerpt}>{echo.transcript_excerpt}</Text>
        </View>
      ) : null}
      {echo.transcript_excerpt ? (
        <Text style={styles.echoExpandHint}>
          {expanded ? '↑ collapse' : '↓ tap to see surrounding context'}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: { paddingBottom: 60 },
  header: { paddingHorizontal: layout.screenPadding, paddingTop: 12, paddingBottom: 8 },
  title: { ...type.screenTitle, color: colors.ink },
  subtitle: { ...type.screenSubtitle, color: colors.textMuted, marginTop: 2 },

  section: { paddingHorizontal: layout.screenPadding, paddingTop: 16 },

  label: {
    fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.textSecondary,
    marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5,
  },
  textarea: {
    minHeight: 90, padding: 12,
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
    backgroundColor: colors.rubric, borderRadius: 6,
    alignItems: 'center', justifyContent: 'center',
  },
  primaryBtnText: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 14 },
  linkBtn: { marginTop: 16, alignSelf: 'flex-start' },
  linkBtnText: { color: colors.rubric, fontFamily: fonts.bodyMedium, fontSize: 13 },

  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 6 },
  chip: {
    paddingVertical: 6, paddingHorizontal: 10,
    backgroundColor: colors.parchmentDark,
    borderColor: colors.rule, borderWidth: StyleSheet.hairlineWidth, borderRadius: 14,
  },
  chipActive: { backgroundColor: colors.rubric, borderColor: colors.rubric },
  chipText: { fontFamily: fonts.ui, fontSize: 12, color: colors.textBody },
  chipTextActive: { color: '#fff' },

  helperText: { color: colors.textMuted, fontFamily: fonts.reading, fontSize: 13, marginTop: 8 },
  errorText: { color: colors.danger, fontFamily: fonts.bodyMedium, fontSize: 13, marginTop: 8 },

  metaLine: {
    fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted,
    marginBottom: 12,
  },

  transcriptBox: {
    padding: 12, marginBottom: 14,
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 3, borderLeftColor: colors.info, borderRadius: 4,
  },
  transcriptLabel: {
    fontFamily: fonts.bodyMedium, fontSize: 10, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
  },
  transcriptText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.ink },

  emptyBox: {
    padding: 16,
    backgroundColor: colors.parchmentDark,
    borderRadius: 6,
  },
  emptyText: {
    fontFamily: fonts.reading, fontSize: 13, lineHeight: 19,
    color: colors.textBody,
  },

  echo: {
    padding: 12, marginBottom: 10,
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 2, borderLeftColor: colors.rubric, borderRadius: 4,
  },
  echoHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    marginBottom: 4,
  },
  echoMeta: {
    fontFamily: fonts.ui, fontSize: 11, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  echoSim: { fontFamily: fonts.ui, fontSize: 11, color: colors.rubric },
  echoNode: {
    fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.textSecondary,
    fontStyle: 'italic', marginBottom: 4,
  },
  echoText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 21, color: colors.ink },
  echoExpandHint: {
    fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginTop: 8,
  },
  echoExcerptBox: {
    marginTop: 8, paddingTop: 8,
    borderTopColor: colors.rule, borderTopWidth: StyleSheet.hairlineWidth,
  },
  echoExcerptLabel: {
    fontFamily: fonts.bodyMedium, fontSize: 10, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
  },
  echoExcerpt: {
    fontFamily: fonts.reading, fontSize: 13, lineHeight: 19, fontStyle: 'italic',
    color: colors.textBody,
  },
});
