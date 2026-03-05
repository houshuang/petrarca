import { Tabs } from 'expo-router';
import { logEvent } from '../../data/logger';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: { display: 'none' },
      }}
      screenListeners={{
        tabPress: (e) => {
          logEvent('tab_press', { tab: e.target?.split('-')[0] });
        },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Feed' }} />
      <Tabs.Screen name="library" options={{ title: 'Library' }} />
      <Tabs.Screen name="review" options={{ title: 'Review' }} />
      <Tabs.Screen name="stats" options={{ title: 'Progress' }} />
    </Tabs>
  );
}
