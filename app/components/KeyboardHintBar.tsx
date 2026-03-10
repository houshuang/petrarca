import { View, Text, StyleSheet, Platform, Pressable } from 'react-native';
import { useState } from 'react';
import { colors, fonts } from '../design/tokens';
import type { ShortcutMap } from '../hooks/useKeyboardShortcuts';

interface Props {
  shortcuts: ShortcutMap;
}

export default function KeyboardHintBar({ shortcuts }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  if (Platform.OS !== 'web') return null;

  const entries = Object.entries(shortcuts).filter(([key]) => key !== '?');

  if (collapsed) {
    return (
      <Pressable
        style={styles.toggleBtn}
        onPress={() => setCollapsed(false)}
      >
        <Text style={styles.toggleText}>?</Text>
      </Pressable>
    );
  }

  return (
    <View style={styles.bar}>
      <View style={styles.inner}>
        {entries.map(([key, { label }]) => (
          <View key={key} style={styles.item}>
            <View style={styles.keyBadge}>
              <Text style={styles.keyText}>{key}</Text>
            </View>
            <Text style={styles.label}>{label}</Text>
          </View>
        ))}
        <Pressable onPress={() => setCollapsed(true)} style={styles.item}>
          <View style={[styles.keyBadge, { borderColor: colors.textMuted }]}>
            <Text style={[styles.keyText, { color: colors.textMuted }]}>×</Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: colors.parchmentDark,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    paddingVertical: 6,
    paddingHorizontal: 16,
  },
  inner: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 12,
    maxWidth: 1100,
    alignSelf: 'center',
    width: '100%',
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  keyBadge: {
    minWidth: 18,
    height: 18,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 3,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
    backgroundColor: colors.parchment,
  },
  keyText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textSecondary,
  },
  label: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },
  toggleBtn: {
    position: 'absolute' as any,
    bottom: 8,
    right: 12,
    width: 22,
    height: 22,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.parchmentDark,
    zIndex: 100,
    opacity: 0.6,
  },
  toggleText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },
});
