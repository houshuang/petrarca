import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { studyRequest, StudyStatus } from '../../lib/study-api';
import StudyReview from './StudyReview';
import StudyAssessment from './StudyAssessment';
import StudyLearningAids from './StudyLearningAids';
import {logEvent} from '../../data/logger';
import StudyStats from './StudyStats';
import {StudyButton, styles} from './StudyControls';
import {colors} from '../../design/tokens';
import { setFeedbackContext } from '../../lib/feedback-context';

/** Fail closed while focus is unknown; cached legacy cards must not leak through. */
export default function StudyGate({ mode, children }: { mode: 'review' | 'voice' | 'stats'; children: React.ReactNode }) {
  const [aids,setAids] = useState(false);
  const [assessment,setAssessment] = useState(false);
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
  if (mode==='review' && aids) return <StudyLearningAids onBack={()=>setAids(false)} />;
  if (mode==='review') return <StudyReview mode="review" onOpenAids={()=>{logEvent('study_learning_aids_entry');setAids(true);}} />;
  if (mode==='voice' && assessment) return <StudyAssessment onBack={()=>setAssessment(false)} />;
  if (mode==='voice') return <StudyReview mode="voice" onOpenAssessment={()=>{logEvent('study_assessment_entry');setAssessment(true);}} />;
  return mode === 'stats' ? <StudyStats /> : <StudyReview mode={mode} />;
}
