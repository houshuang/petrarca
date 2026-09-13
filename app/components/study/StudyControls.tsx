import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { colors, fonts } from '../../design/tokens';
export function StudyButton({children, onPress, disabled = false}: {children: React.ReactNode; onPress: () => void; disabled?: boolean}) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}
    style={[styles.button, disabled && {opacity: 0.45}]}><Text style={styles.buttonText}>{children}</Text></Pressable>;
}
export const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: colors.parchment},
  content: {padding: 20, paddingBottom: 90, gap: 16, maxWidth: 700, width: '100%', alignSelf: 'center'},
  title: {fontFamily: fonts.display, fontSize: 32, color: colors.ink},
  heading: {fontFamily: fonts.body, fontSize: 25, color: colors.ink},
  body: {fontFamily: fonts.reading, fontSize: 20, lineHeight: 28, color: colors.ink},
  caption: {fontFamily: fonts.ui, fontSize: 13, lineHeight: 20, color: colors.textSecondary},
  button: {borderWidth: 1, borderColor: colors.rule, paddingHorizontal: 16, paddingVertical: 14, minHeight: 48, borderRadius: 5},
  buttonText: {fontFamily: fonts.ui, fontSize: 15, color: colors.rubric},
  panel: {gap: 12, padding: 18, backgroundColor: colors.parchmentDark, borderRadius: 5},
  row: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  error: {fontFamily: fonts.ui, color: colors.danger, fontSize: 14},
});
