import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { studyRequest, StudyStatus } from '../../lib/study-api';
import StudyReview from './StudyReview';
import StudyStats from './StudyStats';
import {StudyButton, styles} from './StudyControls';
import {colors} from '../../design/tokens';
import { setFeedbackContext } from '../../lib/feedback-context';

/** Fail closed while focus is unknown; cached legacy cards must not leak through. */
export default function StudyGate({ mode, children }: { mode: 'review' | 'voice' | 'stats'; children: React.ReactNode }) {
  const [status, setStatus] = useState<StudyStatus | null>(null);
  const [error, setError] = useState(false);
  const refresh = useCallback(() => {
    setError(false);
    studyRequest<StudyStatus>('status').then(setStatus).catch(() => setError(true));
  }, []);
  useFocusEffect(useCallback(() => { setFeedbackContext({screen: `study-${mode}`}); refresh(); }, [refresh, mode]));
  if (!status || error) return <View style={{padding: 32, gap: 16, flex: 1, justifyContent: 'center', backgroundColor: colors.parchment}}>
    {error ? <><Text style={styles.body}>Kunne ikke hente dagens oppgaver.</Text><Text style={styles.caption}>Sjekk nettet og prøv igjen. Ingenting er mistet.</Text><StudyButton variant="primary" onPress={refresh}>Prøv igjen</StudyButton></> : <><ActivityIndicator color={colors.rubric} /><Text style={[styles.caption,{textAlign:'center'}]}>Henter dagens oppgaver …</Text></>}
  </View>;
  if (!status.active) return <>{children}</>;
  return mode === 'stats' ? <StudyStats /> : <StudyReview mode={mode} />;
}
