import { Tabs } from 'expo-router';
import { StyleSheet, Platform } from 'react-native';
import { colors, fonts } from '../../design/tokens';
import { logEvent } from '../../data/logger';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: tabStyles.tabBar,
        tabBarShowLabel: true,
        tabBarLabelStyle: tabStyles.label,
        tabBarActiveTintColor: colors.rubric,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarIconStyle: { display: 'none' },
      }}
      screenListeners={{
        tabPress: (e) => {
          logEvent('tab_press', { tab: e.target?.split('-')[0] });
        },
      }}
    >
      {/* ── Visible tabs (5-tab layout) ── */}
      <Tabs.Screen name="index" options={{
        title: 'I dag',
      }} />
      <Tabs.Screen name="voice" options={{
        title: 'Fortell',
      }} />
      <Tabs.Screen name="stats" options={{
        title: 'Fremgang',
      }} />
      <Tabs.Screen name="library" options={{
        title: 'Bøker',
      }} />
      <Tabs.Screen name="more" options={{
        title: 'Mer',
      }} />

      {/* ── Hidden tabs (accessible via navigation, not in tab bar) ── */}
      <Tabs.Screen name="feed" options={{
        title: 'Feed',
        href: null,
      }} />
      <Tabs.Screen name="topics" options={{
        title: 'Topics',
        href: null,
      }} />
      <Tabs.Screen name="queue" options={{
        title: 'Queue',
        href: null,
      }} />
      <Tabs.Screen name="log" options={{
        title: 'Log',
        href: null,
      }} />
    </Tabs>
  );
}

const tabStyles = StyleSheet.create({
  tabBar: {
    backgroundColor: colors.parchmentDark,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    height: 52,
    paddingBottom: Platform.OS === 'ios' ? 20 : 4,
    paddingTop: 4,
    elevation: 0,
    shadowOpacity: 0,
  },
  label: {
    fontFamily: Platform.select({
      web: "'EB Garamond', Georgia, serif",
      default: 'EBGaramond',
    }),
    fontSize: 12,
    letterSpacing: 0.3,
  },
});
