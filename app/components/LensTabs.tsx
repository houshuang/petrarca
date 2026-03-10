import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import type { FeedLens } from '../data/store';

const LENSES: { key: FeedLens; label: string }[] = [
  { key: 'latest', label: 'Latest' },
  { key: 'best', label: 'Best' },
  { key: 'topics', label: 'Topics' },
  { key: 'quick', label: 'Quick' },
];

interface LensTabsProps {
  activeLens: FeedLens;
  onLensChange: (lens: FeedLens) => void;
}

export default function LensTabs({ activeLens, onLensChange }: LensTabsProps) {
  return (
    <View style={styles.container}>
      <View style={styles.tabs}>
        {LENSES.map(({ key, label }) => {
          const active = activeLens === key;
          return (
            <Pressable
              key={key}
              style={styles.tab}
              onPress={() => {
                if (key !== activeLens) {
                  logEvent('lens_switch', { from: activeLens, to: key });
                  onLensChange(key);
                }
              }}
            >
              <Text style={[styles.tabText, active && styles.tabTextActive]}>
                {label}
              </Text>
              {active && <View style={styles.activeIndicator} />}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.parchment,
    paddingHorizontal: layout.screenPadding,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
    zIndex: 10,
    ...(Platform.OS === 'web' ? {
      maxWidth: layout.webFeedMaxWidth,
      width: '100%',
      alignSelf: 'center' as const,
    } : {}),
  },
  tabs: {
    flexDirection: 'row',
    gap: 0,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: 'center',
  },
  tabText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? {} : {}),
  },
  tabTextActive: {
    color: colors.ink,
  },
  activeIndicator: {
    position: 'absolute',
    bottom: 0,
    left: '25%',
    right: '25%',
    height: 2,
    backgroundColor: colors.rubric,
  },
});
