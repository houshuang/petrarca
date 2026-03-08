import { Tabs } from 'expo-router';
import { View, Text, StyleSheet, Platform } from 'react-native';
import { colors, fonts } from '../../design/tokens';
import { logEvent } from '../../data/logger';

function TabBarLabel({ label, focused }: { label: string; focused: boolean }) {
  return (
    <View style={tabStyles.labelContainer}>
      <Text style={[tabStyles.label, focused && tabStyles.labelActive]}>{label}</Text>
      {focused && <View style={tabStyles.activeDot} />}
    </View>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: tabStyles.bar,
        tabBarShowLabel: false,
      }}
      screenListeners={{
        tabPress: (e) => {
          logEvent('tab_press', { tab: e.target?.split('-')[0] });
        },
      }}
    >
      <Tabs.Screen name="index" options={{
        title: 'Feed',
        tabBarIcon: ({ focused }) => <TabBarLabel label="Feed" focused={focused} />,
      }} />
      <Tabs.Screen name="topics" options={{
        title: 'Topics',
        tabBarIcon: ({ focused }) => <TabBarLabel label="Topics" focused={focused} />,
      }} />
      <Tabs.Screen name="queue" options={{
        title: 'Queue',
        tabBarIcon: ({ focused }) => <TabBarLabel label="Queue" focused={focused} />,
      }} />
    </Tabs>
  );
}

const tabStyles = StyleSheet.create({
  bar: {
    backgroundColor: colors.parchmentDark,
    borderTopWidth: 1.5,
    borderTopColor: colors.ink,
    paddingTop: 12,
    paddingBottom: Platform.OS === 'ios' ? 28 : 12,
    height: Platform.OS === 'ios' ? 80 : 60,
  },
  labelContainer: {
    alignItems: 'center',
    gap: 4,
  },
  label: {
    fontFamily: fonts.body,
    fontSize: 11,
    color: colors.textMuted,
  },
  labelActive: {
    color: colors.ink,
  },
  activeDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rubric,
  },
});
