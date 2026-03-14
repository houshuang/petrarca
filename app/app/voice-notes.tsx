import { useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Platform, ScrollView } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { colors, fonts, type, spacing, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { fetchAllNotes, executeNoteAction } from '../lib/voice-notes-api';
import VoiceNoteCard from '../components/VoiceNoteCard';
import DoubleRule from '../components/DoubleRule';
import type { VoiceNote } from '../lib/voice-notes-api';

interface NoteSection {
  title: string;
  data: VoiceNote[];
}

function groupByDate(notes: VoiceNote[]): NoteSection[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  const yesterday = today - 86400;

  const groups: Record<string, VoiceNote[]> = {};
  const order: string[] = [];

  for (const note of notes) {
    let label: string;
    if (note.created_at >= today) {
      label = 'TODAY';
    } else if (note.created_at >= yesterday) {
      label = 'YESTERDAY';
    } else {
      const d = new Date(note.created_at * 1000);
      label = d.toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
      }).toUpperCase();
    }
    if (!groups[label]) {
      groups[label] = [];
      order.push(label);
    }
    groups[label].push(note);
  }

  return order.map(title => ({ title, data: groups[title] }));
}

export default function VoiceNotesScreen() {
  const router = useRouter();
  const [notes, setNotes] = useState<VoiceNote[]>([]);
  const [loading, setLoading] = useState(true);

  const loadNotes = useCallback(async () => {
    setLoading(true);
    const fetched = await fetchAllNotes();
    setNotes(fetched);
    setLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      logEvent('voice_notes_screen_open');
      loadNotes();
    }, [loadNotes])
  );

  const handleArticlePress = useCallback((articleId: string) => {
    router.push({ pathname: '/reader', params: { id: articleId } });
  }, [router]);

  const handleActionExecute = useCallback(async (noteId: string, actionId: string) => {
    try {
      await executeNoteAction(noteId, actionId);
      await loadNotes();
    } catch (e) {
      logEvent('warning', { message: 'Failed to execute action', error: String(e) });
    }
  }, [loadNotes]);

  const sections = groupByDate(notes);

  // Build flat list items with section headers
  const items: Array<{ type: 'header'; title: string; key: string } | { type: 'note'; note: VoiceNote; key: string }> = [];
  for (const section of sections) {
    items.push({ type: 'header', title: section.title, key: `header-${section.title}` });
    for (const note of section.data) {
      items.push({ type: 'note', note, key: note.id });
    }
  }

  // --- Web layout ---
  if (Platform.OS === 'web') {
    return (
      <View style={styles.container}>
        <ScrollView
          style={webStyles.scrollView}
          contentContainerStyle={webStyles.scrollContent}
        >
          <View style={webStyles.centeredColumn}>
            <Pressable
              onPress={() => router.back()}
              style={webStyles.backButton}
            >
              <Text style={webStyles.backText}>{'\u2190'} Feed</Text>
            </Pressable>

            <View style={styles.header}>
              <Text style={styles.title}>Voice Notes</Text>
              <Text style={styles.subtitle}>
                {notes.length} note{notes.length !== 1 ? 's' : ''}
              </Text>
            </View>

            <DoubleRule />

            {items.length > 0 ? (
              items.map(item => {
                if (item.type === 'header') {
                  return (
                    <Text key={item.key} style={styles.sectionHead}>
                      <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
                      {item.title}
                    </Text>
                  );
                }
                return (
                  <VoiceNoteCard
                    key={item.key}
                    note={item.note}
                    showArticleLink
                    onArticlePress={handleArticlePress}
                    onActionExecute={handleActionExecute}
                  />
                );
              })
            ) : !loading ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>No voice notes yet</Text>
              </View>
            ) : null}
          </View>
        </ScrollView>
      </View>
    );
  }

  // --- Mobile layout ---
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Text style={styles.backText}>{'\u2190'} Feed</Text>
        </Pressable>
        <Text style={styles.title}>Voice Notes</Text>
        <Text style={styles.subtitle}>
          {notes.length} note{notes.length !== 1 ? 's' : ''}
        </Text>
      </View>

      <DoubleRule />

      <FlatList
        data={items}
        keyExtractor={item => item.key}
        renderItem={({ item }) => {
          if (item.type === 'header') {
            return (
              <Text style={styles.sectionHead}>
                <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
                {item.title}
              </Text>
            );
          }
          return (
            <VoiceNoteCard
              note={item.note}
              showArticleLink
              onArticlePress={handleArticlePress}
              onActionExecute={handleActionExecute}
            />
          );
        }}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          !loading ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>No voice notes yet</Text>
            </View>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  header: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 8,
    paddingBottom: 8,
  },
  backButton: {
    paddingVertical: 4,
    marginBottom: 4,
    alignSelf: 'flex-start',
    minHeight: 44,
    justifyContent: 'center',
  },
  backText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textMuted,
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

  // Section headers
  sectionHead: {
    ...type.sectionHead,
    color: colors.rubric,
    marginTop: 16,
    marginBottom: 4,
  },

  listContent: {
    paddingHorizontal: layout.screenPadding,
    paddingBottom: 40,
  },

  // Empty state
  empty: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  emptyText: {
    fontFamily: fonts.reading,
    fontSize: 16,
    color: colors.textSecondary,
  },
});

// --- Web-specific styles ---
const webStyles = StyleSheet.create({
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 60,
  },
  centeredColumn: {
    maxWidth: layout.readingMeasure,
    marginHorizontal: 'auto' as any,
    paddingHorizontal: spacing.xxxl,
    width: '100%' as any,
  },
  backButton: {
    paddingVertical: spacing.xs,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
    alignSelf: 'flex-start',
    minHeight: layout.touchTarget,
    justifyContent: 'center',
  },
  backText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textMuted,
    cursor: 'pointer' as any,
  },
});
