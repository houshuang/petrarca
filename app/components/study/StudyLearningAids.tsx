import React, {useCallback, useRef, useState} from 'react';
import {ActivityIndicator, Image, Linking, ScrollView, Text, View} from 'react-native';
import {useFocusEffect} from 'expo-router';
import {clientContext, requestId, studyEvent, studyRequest} from '../../lib/study-api';
import {setFeedbackContext} from '../../lib/feedback-context';
import {logEvent} from '../../data/logger';
import {StudyButton,styles} from './StudyControls';
import StudyTimeline from './StudyTimeline';
import StudyRecorder from './StudyRecorder';
import PetrarcaDrawer from '../PetrarcaDrawer';

type Aid = {id:string;title:string;text:string;application:string;version:string;sources:string[]};
type ReferenceRun = {run_id:string;aid:string;items:Aid[];reference:{version:string;sources:{id:string;title:string;url:string}[]}};
const choices=[['ard','Ard og plog'],['akerrein','Åkerrein i landskapet'],['timeline','Flere klokker på samme tidslinje']] as const;
export default function StudyLearningAids({onBack}:{onBack:()=>void}) {
  const [clarity,setClarity]=useState<string|null>(null);
  const [run,setRun]=useState<ReferenceRun|null>(null);
  const [application,setApplication]=useState(false);
  const [busy,setBusy]=useState(false);
  const [recording,setRecording]=useState(false);
  const [error,setError]=useState('');
  const [drawer,setDrawer]=useState(false);
  const request=useRef<{id:string;aid:string;application:boolean}|null>(null);
  const item=run?.items[0];
  useFocusEffect(useCallback(()=>{setFeedbackContext({screen:'study-learning-aids'});logEvent('study_learning_aids_open');},[]));
  function log(event:string,detail:Record<string,unknown>={}) {
    if(run && item) void studyEvent(run.run_id,item.id,event,{aid:run.aid,content_version:run.reference.version,...detail}).catch(()=>setError('Hendelsen er bevart på telefonen og sendes når du har nett.'));
  }
  async function choose(aid:string,applicationMode=false,retry=false) {
    setBusy(true);setError('');
    if(!retry) request.current={id:requestId(),aid,application:applicationMode};
    try {
      const next=await studyRequest<ReferenceRun>('session',{mode:'reference',aid,request_id:request.current?.id,client_context:clientContext()});
      setRun(next);setClarity(null);setApplication(applicationMode);
      await studyEvent(next.run_id,next.items[0].id,'shown',{aid,content_version:next.reference.version,phase:applicationMode?'new_example':'explanation'});
    } catch {setError('Kunne ikke hente forklaringen. Prøv igjen.');}
    finally {setBusy(false);}
  }
  return <ScrollView style={styles.page} contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
    <PetrarcaDrawer visible={drawer} onClose={()=>setDrawer(false)} />
    <StudyButton variant="quiet" disabled={recording} onPress={()=>setDrawer(true)}>✦</StudyButton>
    <Text style={styles.title}>{item?.title || 'Se og forstå'}</Text>
    <StudyButton variant="quiet" disabled={recording} onPress={()=>{log('session_left');onBack();}}>Tilbake til øving</StudyButton>
    {!!error && <><Text style={styles.error}>{error}</Text>{request.current && <StudyButton disabled={busy} onPress={()=>void choose(request.current!.aid,request.current!.application,true)}>Prøv igjen</StudyButton>}</>}
    {busy && <ActivityIndicator />}
    {!run ? <View style={{gap:12}}>
      <Text style={styles.body}>Forklaringer du kan se på når et ord eller en tidslinje er vanskelig å forestille seg.</Text>
      {choices.map(([id,label])=><View key={id} style={styles.panel}>
        <StudyButton disabled={busy} onPress={()=>void choose(id)}>{label}</StudyButton>
        <StudyButton variant="quiet" disabled={busy} onPress={()=>void choose(id,true)}>Prøv et nytt eksempel først</StudyButton>
      </View>)}
    </View> : item && <View style={{gap:14}}>
      {application ? <>
        <Text style={styles.body}>{item.application}</Text>
        {run.aid==='akerrein' && <Image source={require('../../assets/study/akerrein-transfer-v1.png')} style={{width:'100%',aspectRatio:600/340}} resizeMode="contain" accessibilityLabel="Nytt snitt: terrenget stiger mot høyre. A er ved nedre venstre kant, B ved øvre høyre kant." />}
        <Text style={styles.caption}>Du kan si forklaringen høyt og ta den opp før du ser støtten. Det er frivillig.</Text>
        <StudyRecorder run={run.run_id} item={item.id} kind="reflection" onBusy={setRecording} onSaved={()=>log('feedback',{dimension:'application_response',value:'recorded'})} />
        <StudyButton disabled={recording} onPress={()=>{log('revealed',{phase:'explanation_after_application'});setApplication(false);}}>Se forklaringen</StudyButton>
      </> : <>
        <Text style={styles.body}>{item.text}</Text>
        {run.aid==='ard' && <>
          <Image source={require('../../assets/study/ard-v1.png')} style={{width:'100%',aspectRatio:600/430}} resizeMode="contain" onLoad={()=>log('feedback',{dimension:'image_loaded',asset:'ard-v1'})} accessibilityLabel="Ard: ås trekkes framover, håndtak bak, en symmetrisk spiss arbeider i jorda. Prinsippskisse." />
          <Image source={require('../../assets/study/soil-action-v1.png')} style={{width:'100%',aspectRatio:600/430}} resizeMode="contain" onLoad={()=>log('feedback',{dimension:'image_loaded',asset:'soil-action-v1'})} accessibilityLabel="Jordsnitt: ard løsner jord til begge sider; plog med veltefjøl vender en jordstripe til én side." />
        </>}
        {run.aid==='akerrein' && <Image source={require('../../assets/study/akerrein-v1.png')} style={{width:'100%',aspectRatio:600/400}} resizeMode="contain" onLoad={()=>log('feedback',{dimension:'image_loaded',asset:'akerrein-v1'})} accessibilityLabel="Skrånende åker: jord flyttes nedover over tid og samles ved nedkanten som en åkerrein. Stiplet linje viser tidligere terreng." />}
        {run.aid==='timeline' && <StudyTimeline />}
        <Text style={styles.caption}>Å ha sett forklaringen er en eksponering, ikke en bekreftelse på at du har forstått eller husker den.</Text>
        <StudyButton variant="choice" selected={clarity==='clearer'} onPress={()=>{setClarity('clearer');log('feedback',{dimension:'visual_clarity',value:'clearer'});}}>Dette gjorde det tydeligere</StudyButton>
        <StudyButton variant="choice" selected={clarity==='unclear'} onPress={()=>{setClarity('unclear');log('feedback',{dimension:'visual_clarity',value:'unclear'});}}>Fortsatt vanskelig å se for meg</StudyButton>
        {clarity && <Text accessibilityLiveRegion="polite" style={styles.caption}>Takk — tilbakemeldingen er registrert.</Text>}
        {run.reference.sources.filter(s=>item.sources.includes(s.id)).map(s=><StudyButton key={s.id} variant="link" onPress={()=>{log('source_opened',{source:s.id});void Linking.openURL(s.url).catch(()=>setError('Kunne ikke åpne kilden.'));}}>{s.title}</StudyButton>)}
      </>}
      <StudyButton variant="quiet" disabled={recording} onPress={()=>{log('session_left');setRun(null);}}>Andre forklaringer</StudyButton>
    </View>}
  </ScrollView>;
}
