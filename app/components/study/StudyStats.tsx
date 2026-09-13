import React, {useCallback,useState} from 'react';
import {ScrollView,Text,View} from 'react-native';
import {useFocusEffect} from 'expo-router';
import {studyRequest} from '../../lib/study-api';
import {setFeedbackContext} from '../../lib/feedback-context';
import {logEvent} from '../../data/logger';
import {StudyButton,styles} from './StudyControls';
type Summary={events:Record<string,number>;reading_recordings:number;recorded_reading_seconds:number;
  audio:{response_kind:string;transcription_status:string;count:number}[]};
export default function StudyStats() {
  const [data,setData]=useState<Summary|null>(null);
  const [error,setError]=useState('');
  const refresh=useCallback(() => {setError('');studyRequest<Summary>('summary').then(setData).catch(()=>setError('Kunne ikke hente målingene.'));},[]);
  useFocusEffect(useCallback(()=>{setFeedbackContext({screen:'norway-study-stats'});logEvent('study_stats_opened');refresh();},[refresh]));
  return <ScrollView style={styles.page} contentContainerStyle={styles.content}>
    <Text style={styles.title}>Leseforsøket</Text>
    <Text style={styles.body}>Vi følger møtene med stoffet og hvordan forklaringene dine endrer seg.</Text>
    {!!error && <Text style={styles.error}>{error}</Text>}
    {data && <>
      <View style={styles.panel}><Text style={styles.heading}>Lesingen som er registrert</Text>
        <Text style={styles.body}>{data.reading_recordings} opptak · {Math.round(data.recorded_reading_seconds/60)} minutter</Text>
        <Text style={styles.caption}>Opptakstid inkluderer høytlesing, notater og eventuelle pauser. Førlesingsopptaket holdes separat.</Text>
      </View>
      <View style={styles.panel}><Text style={styles.heading}>Møter med læringsstoffet</Text>
        <Text style={styles.body}>{data.events.introduced||0} introduksjoner lest</Text>
        <Text style={styles.body}>{data.events.complete||0} oppgaver med egenvurdering</Text>
        <Text style={styles.body}>{data.events.skip||0} oppgaver hoppet over</Text>
        <Text style={styles.caption}>Dette teller handlinger, ikke hvor mye du kan. Å se svaret eller lese boka høyt dokumenterer ikke i seg selv forståelse.</Text>
      </View>
      <View style={styles.panel}><Text style={styles.heading}>Stemmen din</Text>
        {(['recall','wondering','correction','reflection'] as const).map((kind,i)=><Text key={kind} style={styles.body}>
          {data.audio.filter(a=>a.response_kind===kind).reduce((s,a)=>s+a.count,0)} {['gjenfortellinger','undringer','rettelser','refleksjoner'][i]}
        </Text>)}
        <Text style={styles.caption}>{data.audio.filter(a=>a.transcription_status!=='complete').reduce((s,a)=>s+a.count,0)} opptak venter på ferdig transkripsjon. Original lyd er bevart.</Text>
      </View>
    </>}
    <StudyButton onPress={()=>{logEvent('study_stats_refresh');refresh();}}>Oppdater</StudyButton>
  </ScrollView>;
}
