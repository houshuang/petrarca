import { useEffect, useRef, useCallback } from 'react';
import { View, Text, Pressable, StyleSheet, Platform, Animated, Dimensions } from 'react-native';
import { getArticleById } from '../data/store';
import { getDisplayTitle } from '../lib/display-utils';
import { logEvent } from '../data/logger';
import { fonts } from '../design/tokens';

const fc = {
  bg: '#f5f1e8', ink: '#2e2924', accent: '#8b2500', body: '#3a3632',
  secondary: '#6e675e', muted: '#a69e90', line: '#ddd8cc',
  surface: '#edeade', green: '#2a7a4a',
};

interface ArticlePopoverProps {
  articleId: string;
  position: { x: number; y: number };
  onClose: () => void;
  onQueue: (articleId: string) => void;
  onSeen: (articleId: string) => void;
  onDisregard: (articleId: string) => void;
  uniqueContributions?: string[];
  coveragePercent?: number;
}

export default function ArticlePopover({
  articleId, position, onClose, onQueue, onSeen, onDisregard,
  uniqueContributions, coveragePercent,
}: ArticlePopoverProps) {
  if (Platform.OS !== 'web') return null;

  const fadeAnim = useRef(new Animated.Value(0)).current;
  const popoverRef = useRef<View>(null);

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1, duration: 150, useNativeDriver: true,
    }).start();
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const el = (popoverRef.current as any)?._nativeTag
        ? undefined
        : (popoverRef.current as any);
      if (el && typeof el.contains === 'function' && el.contains(e.target as Node)) return;
      onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const article = getArticleById(articleId);
  if (!article) return null;

  const title = getDisplayTitle(article);
  const readMin = article.estimated_read_minutes;
  const host = article.hostname;

  const handleAction = useCallback((action: 'queue' | 'seen' | 'disregard') => {
    logEvent('article_popover_action', { article_id: articleId, action });
    if (action === 'queue') onQueue(articleId);
    else if (action === 'seen') onSeen(articleId);
    else onDisregard(articleId);
  }, [articleId, onQueue, onSeen, onDisregard]);

  const win = Dimensions.get('window');
  const popW = 280;
  const popH = 180;
  const margin = 12;

  let left = position.x + margin;
  let top = position.y + margin;
  if (left + popW > win.width - margin) left = position.x - popW - margin;
  if (top + popH > win.height - margin) top = position.y - popH - margin;
  if (left < margin) left = margin;
  if (top < margin) top = margin;

  return (
    <Animated.View
      ref={popoverRef as any}
      style={[styles.container, { left, top, opacity: fadeAnim }]}
      {...{ onMouseEnter: () => {}, onMouseLeave: onClose } as any}
    >
      <Text style={styles.title} numberOfLines={2}>{title}</Text>

      {coveragePercent != null && (
        <View style={styles.coverageRow}>
          <View style={styles.coverageTrack}>
            <View style={[styles.coverageFill, { width: `${coveragePercent}%` }]} />
          </View>
          <Text style={styles.coverageLabel}>{coveragePercent}% covered</Text>
        </View>
      )}

      {uniqueContributions && uniqueContributions.length > 0 && (
        <Text style={styles.contribution} numberOfLines={2}>
          {uniqueContributions[0]}
        </Text>
      )}

      <Text style={styles.meta}>
        {host}{readMin ? ` · ${readMin} min` : ''}
      </Text>

      <View style={styles.actions}>
        <Pressable onPress={() => handleAction('queue')} style={styles.actionBtn}>
          <Text style={styles.actionText}>Queue</Text>
        </Pressable>
        <Pressable onPress={() => handleAction('seen')} style={styles.actionBtn}>
          <Text style={styles.actionText}>Seen</Text>
        </Pressable>
        <Pressable onPress={() => handleAction('disregard')} style={styles.actionBtn}>
          <Text style={styles.actionText}>Disregard</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'fixed' as any,
    width: 280,
    backgroundColor: fc.bg,
    borderWidth: 1,
    borderColor: fc.line,
    borderRadius: 6,
    padding: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    zIndex: 9999,
  },
  title: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 19,
    color: fc.ink,
    marginBottom: 8,
  },
  coverageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  coverageTrack: {
    flex: 1,
    height: 2,
    backgroundColor: fc.line,
    borderRadius: 1,
    overflow: 'hidden',
  },
  coverageFill: {
    height: 2,
    backgroundColor: fc.green,
    borderRadius: 1,
  },
  coverageLabel: {
    fontFamily: fonts.ui,
    fontSize: 9,
    color: fc.muted,
  },
  contribution: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    lineHeight: 17,
    color: fc.secondary,
    marginBottom: 6,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  meta: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: fc.muted,
    marginBottom: 10,
  },
  actions: {
    flexDirection: 'row',
    gap: 16,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: fc.line,
    paddingTop: 8,
  },
  actionBtn: {
    paddingVertical: 2,
  },
  actionText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: fc.accent,
  },
});
