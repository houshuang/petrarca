import { Tabs } from 'expo-router';
import { StyleSheet } from 'react-native';
import { colors } from '../../design/tokens';
import { logEvent } from '../../data/logger';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: tabStyles.hidden,
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
  hidden: {
    display: 'none',
    height: 0,
  },
});
