import { useEffect } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';

export default function NotFound() {
  const router = useRouter();

  useEffect(() => {
    // Auto-redirect known aliases
    if (typeof window !== 'undefined') {
      const path = window.location.pathname;
      if (path === '/progress') {
        router.replace('/stats');
        return;
      }
    }
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.icon}>404</Text>
      <Text style={styles.title}>Page not found</Text>
      <Pressable style={styles.button} onPress={() => router.replace('/')}>
        <Text style={styles.buttonText}>Go to Feed</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a', gap: 16 },
  icon: { color: '#475569', fontSize: 64, fontWeight: '800' },
  title: { color: '#94a3b8', fontSize: 18 },
  button: { backgroundColor: '#2563eb', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 8, marginTop: 8 },
  buttonText: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
});
