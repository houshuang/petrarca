import { useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Platform } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { fetchAllNotes, executeNoteAction } from '../lib/voice-notes-api';
import VoiceNoteCard from '../components/VoiceNoteCard';
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
    await executeNoteAction(noteId, actionId);
    // Refresh to get updated action status
    await loadNotes();
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

      {/* Double rule */}
      <View style={styles.doubleRule}>
        <View style={styles.doubleRuleTop} />
        <View style={styles.doubleRuleGap} />
        <View style={styles.doubleRuleBottom} />
      </View>

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
    fontFamily: fonts.displaySemiBold,
    fontSize: 24,
    lineHeight: 28,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  subtitle: {
    fontFamily: fonts.displayItalic,
    fontSize: 13,
    color: colors.textMuted,
    marginTop: 2,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },

  // Double rule
  doubleRule: {
    paddingHorizontal: layout.screenPadding,
  },
  doubleRuleTop: {
    borderTopWidth: layout.doubleRuleTop,
    borderTopColor: colors.ink,
  },
  doubleRuleGap: {
    height: layout.doubleRuleGap,
  },
  doubleRuleBottom: {
    borderTopWidth: layout.doubleRuleBottom,
    borderTopColor: colors.ink,
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
