import React from 'react';
import {
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  ViewStyle,
} from 'react-native';
import { colors, fonts } from '../../design/tokens';

export type StudyButtonVariant = 'primary' | 'secondary' | 'choice' | 'quiet' | 'link';

export function StudyButton({
  children,
  onPress,
  disabled = false,
  selected = false,
  variant = 'secondary',
  compact = false,
  style,
}: {
  children: React.ReactNode;
  onPress: () => void;
  disabled?: boolean;
  selected?: boolean;
  variant?: StudyButtonVariant;
  compact?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const isPrimary = variant === 'primary';
  const isQuiet = variant === 'quiet';
  const isLink = variant === 'link';
  const filled = isPrimary || selected;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled, selected: selected || undefined }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        compact && styles.buttonCompact,
        isQuiet && styles.buttonQuiet,
        isLink && styles.buttonLink,
        filled && styles.buttonFilled,
        pressed && !disabled && styles.buttonPressed,
        disabled && styles.buttonDisabled,
        style,
      ]}
    >
      <Text
        style={[
          styles.buttonText,
          isQuiet && styles.buttonTextQuiet,
          isLink && styles.buttonTextLink,
          filled && styles.buttonTextFilled,
        ]}
      >
        {children}
      </Text>
    </Pressable>
  );
}

export const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: colors.parchment},
  content: {padding: 20, paddingBottom: 90, gap: 14, maxWidth: 700, width: '100%', alignSelf: 'center'},
  title: {fontFamily: fonts.display, fontSize: 28, lineHeight: 34, color: colors.ink},
  heading: {fontFamily: fonts.body, fontSize: 23, lineHeight: 29, color: colors.ink},
  body: {fontFamily: fonts.reading, fontSize: 18, lineHeight: 26, color: colors.ink},
  caption: {fontFamily: fonts.ui, fontSize: 13, lineHeight: 20, color: colors.textSecondary},
  eyebrow: {fontFamily: fonts.uiMedium, fontSize: 11, lineHeight: 16, letterSpacing: 0.8, textTransform: 'uppercase', color: colors.rubric},
  screenHeader: {gap: 4, paddingBottom: 4},
  progressText: {fontFamily: fonts.uiMedium, fontSize: 12, lineHeight: 18, color: colors.textSecondary},
  selectionSummary: {flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule},
  setupPanel: {gap: 10, paddingVertical: 18, borderTopWidth: 2, borderTopColor: colors.ink, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule},
  modeSummary: {flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4},
  detailsPanel: {gap: 12, paddingVertical: 16, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule},
  button: {borderWidth: 1, borderColor: colors.rule, paddingHorizontal: 16, paddingVertical: 13, minHeight: 48, borderRadius: 5, justifyContent: 'center', alignItems: 'center'},
  buttonCompact: {minHeight: 44, paddingVertical: 9, paddingHorizontal: 12},
  buttonFilled: {backgroundColor: colors.rubric, borderColor: colors.rubric},
  buttonQuiet: {borderColor: 'transparent', backgroundColor: 'transparent', alignSelf: 'flex-start', paddingHorizontal: 4},
  buttonLink: {alignItems: 'flex-start', backgroundColor: colors.parchment},
  buttonPressed: {opacity: 0.7, transform: [{scale: 0.995}]},
  buttonDisabled: {opacity: 0.45},
  buttonText: {fontFamily: fonts.uiMedium, fontSize: 15, lineHeight: 20, color: colors.rubric, textAlign: 'center'},
  buttonTextFilled: {color: colors.parchment},
  buttonTextQuiet: {color: colors.textSecondary, fontSize: 13},
  buttonTextLink: {textAlign: 'left'},
  panel: {gap: 12, padding: 18, backgroundColor: colors.parchmentDark, borderRadius: 5},
  row: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  compactRow: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12},
  divider: {height: StyleSheet.hairlineWidth, backgroundColor: colors.rule},
  error: {fontFamily: fonts.ui, color: colors.danger, fontSize: 14},
});
