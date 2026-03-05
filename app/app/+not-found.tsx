import { useEffect } from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, type } from '../design/tokens';

export default function NotFound() {
  const router = useRouter();

  useEffect(() => {
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
      <Text style={styles.number}>404</Text>
      <Text style={styles.title}>Page not found</Text>
      <Pressable style={styles.button} onPress={() => router.replace('/')}>
        <Text style={styles.buttonText}>Go to Feed</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.parchment,
    gap: 16,
  },
  number: {
    fontFamily: Platform.OS === 'web' ? "'Cormorant Garamond', Georgia, serif" : 'CormorantGaramond-SemiBold',
    color: colors.rule,
    fontSize: 64,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  title: {
    fontFamily: Platform.OS === 'web' ? "'Crimson Pro', Georgia, serif" : 'CrimsonPro',
    color: colors.textSecondary,
    fontSize: 18,
  },
  button: {
    borderWidth: 1,
    borderColor: colors.rubric,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 3,
    marginTop: 8,
  },
  buttonText: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond-Medium',
    color: colors.rubric,
    fontSize: 15,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
});
