import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { colors, fonts, layout } from '../design/tokens';

const NAV_ITEMS = [
  { label: 'Feed', path: '/' },
  { label: 'Library', path: '/library' },
  { label: 'Review', path: '/review' },
  { label: 'Progress', path: '/stats' },
] as const;

export function WebSidebar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <View style={styles.sidebar}>
      {/* Monogram */}
      <Text style={styles.monogram}>P</Text>
      <Text style={styles.wordmark}>PETRARCA</Text>

      {/* Double rule */}
      <View style={styles.doubleRule}>
        <View style={styles.ruleThick} />
        <View style={styles.ruleThin} />
      </View>

      {/* Nav links */}
      <View style={styles.nav}>
        {NAV_ITEMS.map(({ label, path }) => {
          const active = pathname === path || (path === '/' && pathname === '');
          return (
            <Pressable
              key={path}
              style={({ hovered }: any) => [
                styles.navItem,
                hovered && styles.navItemHover,
              ]}
              onPress={() => router.push(path as any)}
            >
              <View style={styles.navRow}>
                {active && <View style={styles.activeDot} />}
                <Text style={[styles.navLabel, active && styles.navLabelActive]}>
                  {label}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sidebar: {
    width: layout.sidebarNavWidth,
    backgroundColor: colors.parchmentDark,
    borderRightWidth: 1,
    borderRightColor: colors.rule,
    paddingTop: 32,
    paddingHorizontal: 20,
  },
  monogram: {
    fontFamily: Platform.OS === 'web' ? "'Cormorant Garamond', Georgia, serif" : 'CormorantGaramond-Bold',
    fontSize: 48,
    color: colors.rubric,
    textAlign: 'center',
    lineHeight: 52,
    ...(Platform.OS === 'web' ? { fontWeight: '700' } : {}),
  },
  wordmark: {
    fontFamily: Platform.OS === 'web' ? "'Cormorant Garamond', Georgia, serif" : 'CormorantGaramond',
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
    letterSpacing: 4,
    marginTop: 2,
  },
  doubleRule: {
    marginTop: 20,
    marginBottom: 24,
    gap: 5,
  },
  ruleThick: {
    height: 2,
    backgroundColor: colors.ruleDark,
  },
  ruleThin: {
    height: 1,
    backgroundColor: colors.ruleDark,
  },
  nav: {
    gap: 2,
  },
  navItem: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 4,
  },
  navItemHover: {
    backgroundColor: colors.parchmentHover,
  },
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  activeDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: colors.rubric,
  },
  navLabel: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 16,
    color: colors.textMuted,
  },
  navLabelActive: {
    color: colors.ink,
  },
});
