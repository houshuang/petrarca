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
    </Tabs>
  );
}
