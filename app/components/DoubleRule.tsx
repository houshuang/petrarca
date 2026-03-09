import { View, StyleSheet } from 'react-native';
import { colors, layout } from '../design/tokens';

export default function DoubleRule() {
  return (
    <View style={styles.container}>
      <View style={styles.top} />
      <View style={styles.gap} />
      <View style={styles.bottom} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: layout.screenPadding,
  },
  top: {
    borderTopWidth: layout.doubleRuleTop,
    borderTopColor: colors.ink,
  },
  gap: {
    height: layout.doubleRuleGap,
  },
  bottom: {
    borderTopWidth: layout.doubleRuleBottom,
    borderTopColor: colors.ink,
  },
});
