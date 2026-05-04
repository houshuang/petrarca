import { useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, Platform } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { colors, fonts, type, layout } from '../../design/tokens';
import { logEvent } from '../../data/logger';
import { setFeedbackContext } from '../../lib/feedback-context';
import DoubleRule from '../../components/DoubleRule';

export default function VoiceTab() {
  const router = useRouter();

  useFocusEffect(
    useCallback(() => {
      logEvent('voice_tab_open');
      setFeedbackContext({ screen: 'voice-tab' });
    }, [])
  );

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>Voice</Text>
        <Text style={styles.subtitle}>Capture and recall what you know</Text>
      </View>

      <DoubleRule />

      {/* Elicitation — guided curriculum recall */}
      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('voice_tab_elicitation_tap');
          router.push('/voice-elicitation' as any);
        }}
      >
        <Text style={styles.cardTitle}>Guided Recall</Text>
        <Text style={styles.cardDescription}>
          The system prompts you with curriculum topics. Record what you remember
          — it tracks what you know and creates review items for gaps.
        </Text>
        <Text style={styles.cardHint}>Structured elicitation by domain</Text>
      </Pressable>

      {/* Capture — free-form voice input */}
      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('voice_tab_capture_tap');
          router.push('/voice-capture' as any);
        }}
      >
        <Text style={styles.cardTitle}>Capture Voice</Text>
        <Text style={styles.cardDescription}>
          Just heard something interesting? Record it. The system extracts facts,
          matches entities, and creates review items automatically.
        </Text>
        <Text style={styles.cardHint}>Podcasts, conversations, reading insights</Text>
      </Pressable>

      {/* Knowledge Sweep */}
      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('voice_tab_sweep_tap');
          router.push('/knowledge-sweep' as any);
        }}
      >
        <Text style={styles.cardTitle}>Knowledge Sweep</Text>
        <Text style={styles.cardDescription}>
          Test your recall across an entire domain. The system scores what you
          remembered vs. what it knows you've studied.
        </Text>
        <Text style={styles.cardHint}>Domain-wide assessment</Text>
      </Pressable>

      {/* Defender mode — adversarial retrieval */}
      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('voice_tab_defender_tap');
          router.push('/defender' as any);
        }}
      >
        <Text style={styles.cardTitle}>Defender Mode</Text>
        <Text style={styles.cardDescription}>
          Assert a thesis. The system surfaces sharp objections drawn from your
          curriculum and voice corpus; you defend. Geluk-style adversarial recall.
        </Text>
        <Text style={styles.cardHint}>Voice or text · Tibetan-debate pearl</Text>
      </Pressable>

      {/* Commonplace — what you said before */}
      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('voice_tab_commonplace_tap');
          router.push('/commonplace' as any);
        }}
      >
        <Text style={styles.cardTitle}>What You Said Before</Text>
        <Text style={styles.cardDescription}>
          Resurface old voice captures that rhyme with what you're thinking now.
          Type or speak a prompt; the system finds echoes from months ago.
        </Text>
        <Text style={styles.cardHint}>Locke's commonplace book · associative pull</Text>
      </Pressable>

      {/* Voice notes history */}
      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('voice_tab_notes_tap');
          router.push('/voice-notes' as any);
        }}
      >
        <Text style={styles.cardTitle}>Voice Notes</Text>
        <Text style={styles.cardDescription}>
          Browse your recorded voice captures and their extracted knowledge.
        </Text>
        <Text style={styles.cardHint}>History of all recordings</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  content: {
    paddingBottom: 40,
  },
  header: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 8,
  },
  title: {
    ...type.screenTitle,
    color: colors.ink,
  },
  subtitle: {
    ...type.screenSubtitle,
    color: colors.textMuted,
    marginTop: 2,
  },
  card: {
    marginHorizontal: layout.screenPadding,
    marginTop: 16,
    padding: 16,
    backgroundColor: colors.parchmentDark,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  cardTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    color: colors.ink,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  cardDescription: {
    fontFamily: fonts.reading,
    fontSize: 13.5,
    lineHeight: 20,
    color: colors.textBody,
  },
  cardHint: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    marginTop: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
});
