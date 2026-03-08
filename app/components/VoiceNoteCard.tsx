import { useState } from 'react';
import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { colors, fonts } from '../design/tokens';
import { logEvent } from '../data/logger';
import type { VoiceNote, NoteAction } from '../lib/voice-notes-api';

interface VoiceNoteCardProps {
  note: VoiceNote;
  showArticleLink?: boolean;
  onArticlePress?: (articleId: string) => void;
  onActionExecute?: (noteId: string, actionId: string) => Promise<void>;
}

const ACTION_BORDER_COLORS: Record<string, string> = {
  research: colors.rubric,
  tag: colors.warning,
  remember: colors.info,
};

const ACTION_LABELS: Record<string, string> = {
  research: 'Research',
  tag: 'Tag',
  remember: 'Remember',
};

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function formatDuration(seconds?: number): string | null {
  if (!seconds) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function ActionChip({
  action,
  noteId,
  onExecute,
}: {
  action: NoteAction;
  noteId: string;
  onExecute?: (noteId: string, actionId: string) => Promise<void>;
}) {
  const [executing, setExecuting] = useState(false);
  const borderColor = ACTION_BORDER_COLORS[action.type] || colors.rule;
  const isDone = action.status === 'done' || action.status === 'running';

  const handlePress = async () => {
    if (isDone || executing || !onExecute) return;
    setExecuting(true);
    logEvent('voice_note_action_execute', {
      note_id: noteId,
      action_id: action.id,
      action_type: action.type,
    });
    try {
      await onExecute(noteId, action.id);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <Pressable
      onPress={handlePress}
      disabled={isDone || executing}
      style={[
        styles.actionChip,
        { borderLeftColor: borderColor },
        isDone && styles.actionChipDone,
      ]}
    >
      <Text style={[styles.actionLabel, { color: borderColor }]}>
        {ACTION_LABELS[action.type] || action.type}
      </Text>
      <Text style={[styles.actionDescription, isDone && styles.actionDescriptionDone]} numberOfLines={2}>
        {action.description}
      </Text>
      {isDone && (
        <Text style={styles.actionStatus}>
          {action.status === 'running' ? 'Running...' : 'Done'}
        </Text>
      )}
    </Pressable>
  );
}

export default function VoiceNoteCard({
  note,
  showArticleLink = true,
  onArticlePress,
  onActionExecute,
}: VoiceNoteCardProps) {
  const durationStr = formatDuration(note.duration);

  return (
    <View style={styles.container}>
      <View style={styles.metaRow}>
        <Text style={styles.timestamp}>{formatTime(note.created_at)}</Text>
        {durationStr && (
          <View style={styles.durationBadge}>
            <Text style={styles.durationText}>{durationStr}</Text>
          </View>
        )}
        {note.status === 'transcribing' && (
          <Text style={styles.statusText}>Transcribing...</Text>
        )}
      </View>

      {note.transcript ? (
        <Text style={styles.transcript} numberOfLines={3}>
          {note.transcript}
        </Text>
      ) : note.status === 'failed' ? (
        <Text style={styles.failedText}>Transcription failed</Text>
      ) : null}

      {showArticleLink && note.article_title ? (
        <Pressable
          onPress={() => {
            if (onArticlePress) {
              logEvent('voice_note_article_tap', {
                note_id: note.id,
                article_id: note.article_id,
              });
              onArticlePress(note.article_id);
            }
          }}
          style={styles.articleLink}
        >
          <Text style={styles.articleLinkText} numberOfLines={1}>
            {note.article_title}
          </Text>
        </Pressable>
      ) : null}

      {note.actions && note.actions.length > 0 ? (
        <View style={styles.actionsRow}>
          {note.actions.map(action => (
            <ActionChip
              key={action.id}
              action={action}
              noteId={note.id}
              onExecute={onActionExecute}
            />
          ))}
        </View>
      ) : null}

      <View style={styles.divider} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 12,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  timestamp: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
  durationBadge: {
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  durationText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },
  statusText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.rubric,
    fontStyle: 'italic',
  },
  transcript: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textBody,
    marginBottom: 6,
  },
  failedText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
    fontStyle: 'italic',
    marginBottom: 6,
  },
  articleLink: {
    marginBottom: 8,
    minHeight: 24,
    justifyContent: 'center',
  },
  articleLinkText: {
    fontFamily: fonts.bodyItalic,
    fontSize: 13,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  actionsRow: {
    gap: 6,
    marginBottom: 4,
  },
  actionChip: {
    borderLeftWidth: 2,
    paddingLeft: 10,
    paddingVertical: 6,
  },
  actionChipDone: {
    opacity: 0.6,
  },
  actionLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 10,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 2,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  actionDescription: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textBody,
  },
  actionDescriptionDone: {
    color: colors.textMuted,
  },
  actionStatus: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    marginTop: 2,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.rule,
    marginTop: 4,
  },
});
