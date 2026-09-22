import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { studyRequest, StudyStatus } from '../../lib/study-api';
import StudyReview from './StudyReview';
import StudyAssessment from './StudyAssessment';
import StudyLearningAids from './StudyLearningAids';
import StudyReadings, {Reading} from './StudyReadings';
import {logEvent} from '../../data/logger';
import StudyStats from './StudyStats';
import {StudyButton, styles} from './StudyControls';
import {colors} from '../../design/tokens';
import { setFeedbackContext } from '../../lib/feedback-context';

/** Fail closed while focus is unknown; cached legacy cards must not leak through. */
export default function StudyGate({ mode, children }: { mode: 'review' | 'voice' | 'stats'; children: React.ReactNode }) {
  const [aids,setAids] = useState(false);
  const [assessment,setAssessment] = useState(false);
  const [readings,setReadings] = useState<{sourceIds?:string[]}|null>(null);
  const [readingExposure,setReadingExposure] = useState<{id:string;hash:string;sequence:number}|null>(null);
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
  if (mode==='review') return <View style={{flex:1}}>
    <View style={readings || aids ? {display:'none'} : {flex:1}}>
      <StudyReview mode="review" suspended={!!readings || aids} readingExposure={readingExposure}
        onOpenReadings={sourceIds=>setReadings({sourceIds})}
        onOpenAids={()=>{logEvent('study_learning_aids_entry');setAids(true);}} />
    </View>
    {aids && !readings && <StudyLearningAids onBack={()=>setAids(false)} onOpenReadings={()=>setReadings({})} />}
    {readings && <StudyReadings sourceIds={readings.sourceIds} onBack={()=>setReadings(null)}
      onShown={(reading:Reading)=>setReadingExposure(old=>({id:reading.id,hash:reading.content_sha256,sequence:(old?.sequence||0)+1}))} />}
  </View>;
  if (mode==='voice' && assessment) return <StudyAssessment onBack={()=>setAssessment(false)} />;
  if (mode==='voice') return <StudyReview mode="voice" onOpenAssessment={()=>{logEvent('study_assessment_entry');setAssessment(true);}} />;
  return mode === 'stats' ? <StudyStats /> : <StudyReview mode={mode} />;
}
