import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View, Pressable } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { studyRequest, StudyStatus } from '../../lib/study-api';
import StudyReview from './StudyReview';
import StudyStats from './StudyStats';
import PetrarcaDrawer from '../PetrarcaDrawer';
import {logEvent} from '../../data/logger';
import {colors} from '../../design/tokens';
import { setFeedbackContext } from '../../lib/feedback-context';

/** Fail closed while focus is unknown; cached legacy cards must not leak through. */
export default function StudyGate({ mode, children }: { mode: 'review' | 'voice' | 'stats'; children: React.ReactNode }) {
  const [status, setStatus] = useState<StudyStatus | null>(null);
  const [error, setError] = useState(false);
  const [drawer,setDrawer] = useState(false);
  const refresh = useCallback(() => {
    setError(false);
    studyRequest<StudyStatus>('status').then(setStatus).catch(() => setError(true));
  }, []);
  useFocusEffect(useCallback(() => { setFeedbackContext({screen: `study-${mode}`}); refresh(); }, [refresh, mode]));
  if (!status || error) return <View style={{padding: 32, flex: 1, justifyContent: 'center'}}>
    {error ? <Pressable onPress={refresh}><Text>Kunne ikke hente studien. Trykk for å prøve igjen.</Text></Pressable> : <ActivityIndicator />}
  </View>;
  if (!status.active) return <>{children}</>;
  return <View style={{flex:1}}>
    {mode === 'stats' ? <StudyStats /> : <StudyReview mode={mode} />}
    <Pressable accessibilityRole="button" accessibilityLabel="Åpne meny" onPress={()=>{logEvent('study_drawer_open',{mode});setDrawer(true);}}
      style={{position:'absolute',top:8,right:8,padding:12}}><Text style={{fontSize:22,color:colors.rubric}}>✦</Text></Pressable>
    <PetrarcaDrawer visible={drawer} onClose={()=>setDrawer(false)} />
  </View>;
}
