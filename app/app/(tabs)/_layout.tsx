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
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarIconStyle: { display: 'none' },
      }}
      screenListeners={{
        tabPress: (e) => {
          logEvent('tab_press', { tab: e.target?.split('-')[0] });
        },
      }}
    >
      <Tabs.Screen name="index" options={{
        title: 'Feed',
      }} />
      <Tabs.Screen name="library" options={{
        title: 'Library',
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
