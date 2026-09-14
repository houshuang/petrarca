import React, {useCallback, useEffect, useState} from 'react';
import {ActivityIndicator, ScrollView, Text, TextInput, View} from 'react-native';
import {useFocusEffect} from 'expo-router';
import {AssessmentContext, AssessmentRun, cachedAssessment, loadAssessment} from '../../lib/study-assessment';
import {pendingAudio, PendingAudio, studyEvent, uploadAudio} from '../../lib/study-api';
import {setFeedbackContext} from '../../lib/feedback-context';
import {logEvent} from '../../data/logger';
import PetrarcaDrawer from '../PetrarcaDrawer';
import DoubleRule from '../DoubleRule';
import StudyRecorder from './StudyRecorder';
import {StudyButton, styles} from './StudyControls';

const occasions: [AssessmentContext['occasion'],string][] = [
  ['current','Det jeg har lest så langt'],['before_volume','Før et nytt bind'],
  ['volume_end','Ferdig med et bind'],['delayed','Senere tilbakeblikk'],['project_end','Hele serien'],
];
export default function StudyAssessment({onBack}: {onBack:()=>void}) {
  const [showOccasions,setShowOccasions] = useState(false);
  const [drawer,setDrawer] = useState(false);
  const [context,setContext] = useState<AssessmentContext>({volume:1,coverage:'',occasion:'current',help_state:'closed'});
  const [run,setRun] = useState<AssessmentRun | null>(null);
  const [busy,setBusy] = useState(false);
  const [recording,setRecording] = useState(false);
  const [confidence,setConfidence] = useState<string | null>(null);
  const [retained,setRetained] = useState(false);
  const [saved,setSaved] = useState(false);
  const [error,setError] = useState('');
  const [pending,setPending] = useState<PendingAudio[]>([]);
  const [resume,setResume] = useState<AssessmentContext | null>(null);
  const item = run?.items.find(p => !run.completed_ids.includes(p.id));
  useFocusEffect(useCallback(() => {
    setFeedbackContext({screen:'study-assessment'}); logEvent('study_assessment_open');
    void cachedAssessment().then(setResume).catch(()=>undefined); void pendingAudio().then(setPending).catch(()=>undefined);
  },[]));
  useEffect(() => {setConfidence(null);setRetained(false);setSaved(!!item && !!run?.audio_item_ids.includes(item.id));},[item?.id,run?.run_id]);
  async function open(config: AssessmentContext, fresh=false) {
    setBusy(true);setError('');
    try {setRun(await loadAssessment(config,fresh));setContext(config);setPending(await pendingAudio());}
    catch {setError('Kunne ikke åpne opptaket. Sjekk nettet og prøv igjen.');}
    finally {setBusy(false);}
  }
  async function chooseConfidence(value:string) {
    if (!run || !item) return;
    setBusy(true);setError('');
    try {await studyEvent(run.run_id,item.id,'feedback',{dimension:'assessment_confidence',value});setConfidence(value);}
    catch {setError('Kunne ikke lagre valget. Prøv igjen.');}
    finally {setBusy(false);}
  }
  async function advance(outcome:string) {
    if (!run || !item) return;
    setBusy(true);setError('');
    try {
      await studyEvent(run.run_id,item.id,'assessment_advance',{outcome,help_state:run.assessment.help_state});
      setRun({...run,completed_ids:[...run.completed_ids,item.id]});
    } catch {setError('Kunne ikke lagre fremgangen. Prøv igjen; opptaket er bevart.');}
    finally {setBusy(false);}
  }
  async function retry(entry:PendingAudio) {
    setBusy(true);setError('');
    try {
      await uploadAudio(entry);setPending(await pendingAudio());
      if (entry.run===run?.run_id && entry.item===item?.id) setSaved(true);
    } catch {setError('Opptaket er fortsatt bevart. Prøv opplasting igjen.');}
    finally {setBusy(false);}
  }
  const locked = busy || recording;
  return <ScrollView style={styles.page} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
    <StudyButton variant="quiet" disabled={locked} onPress={()=>setDrawer(true)}>✦</StudyButton>
    <PetrarcaDrawer visible={drawer} onClose={()=>setDrawer(false)} />
    <Text style={styles.title}>Fortell oversikten</Text><DoubleRule />
    <StudyButton variant="quiet" disabled={locked} onPress={() => {logEvent('study_assessment_leave',{run_id:run?.run_id});onBack();}}>Tilbake til Fortell</StudyButton>
    {!!error && <Text style={styles.error}>{error}</Text>}
    {busy && <ActivityIndicator />}
    {!run ? <View style={styles.panel}>
      <Text style={styles.body}>Fortell først fritt. Deretter får du fem korte spørsmål, uten fasit. Stopp når du er ferdig — du trenger ikke fylle tiden.</Text>
      <Text style={styles.caption}>Omtrent 7 minutter for kjernen; to ekstra spørsmål etter et ferdig bind. Ikke forbered deg. Dette er et øyeblikksbilde av forståelsen din nå.</Text>
      {resume && <StudyButton disabled={busy} onPress={() => void open(resume)}>Fortsett siste oversikt</StudyButton>}
      <Text style={styles.eyebrow}>Hva slags tilbakeblikk?</Text>
      <Text style={styles.body}>{occasions.find(([value])=>value===context.occasion)?.[1]}</Text>
      <StudyButton variant="quiet" disabled={busy} onPress={()=>{logEvent('study_assessment_occasion_options');setShowOccasions(v=>!v);}}>Endre anledning</StudyButton>
      {showOccasions && occasions.map(([value,label]) => <StudyButton key={value} variant="choice" selected={context.occasion===value} disabled={busy} onPress={() => {logEvent('study_assessment_context',{occasion:value});setContext({...context,occasion:value});setShowOccasions(false);}}>{label}</StudyButton>)}
      <Text style={styles.caption}>Bind (1–12)</Text>
      <TextInput accessibilityLabel="Bind" keyboardType="number-pad" style={styles.body} value={String(context.volume)} onChangeText={v=>setContext({...context,volume:Number(v)})} />
      <Text style={styles.caption}>Sider eller kapitler du har lest</Text>
      <TextInput accessibilityLabel="Lest dekning" placeholder="For eksempel s. 13–146, noen detaljer hoppet over" style={styles.body} value={context.coverage} maxLength={200} onChangeText={v=>setContext({...context,coverage:v})} />
      <Text style={styles.caption}>Fortell fra hukommelsen, uten bok eller notater.</Text>
      <StudyButton variant="primary" disabled={busy || !context.coverage.trim() || context.volume<1 || context.volume>12} onPress={()=>void open(context,true)}>Start ny oversikt</StudyButton>
    </View> : item ? <View style={styles.panel}>
      <Text style={styles.eyebrow}>{run.completed_ids.length+1} av {run.items.length} · bind {run.assessment.volume}</Text>
      <Text style={styles.heading}>{item.title}</Text>
      <Text style={styles.body}>{item.text}</Text>
      <Text style={styles.caption}>Inntil {item.max_seconds} sekunder. Si gjerne «vet ikke».</Text>
      {item.confidence && !confidence && !saved ? <>
        <Text style={styles.caption}>Hvor sikker føler du deg før du svarer?</Text>
        {([['sure','Sikker'],['unsure','Usikker'],['unknown','Vet ikke']] as const).map(([value,label])=><StudyButton key={value} disabled={locked} onPress={()=>void chooseConfidence(value)}>{label}</StudyButton>)}
      </> : saved ? <>
        <Text accessibilityLiveRegion="polite" style={styles.caption}>Opptaket er lagret.</Text>
        <StudyButton variant="primary" disabled={locked} onPress={()=>void advance('recorded')}>Fortsett</StudyButton>
      </> : <StudyRecorder key={item.id} run={run.run_id} item={item.id} kind="recall" maxSeconds={item.max_seconds} disabled={busy}
        onBusy={setRecording} onRetained={()=>setRetained(true)} onSaved={()=>{setSaved(true);setRetained(false);}} />}
      {!saved && <StudyButton variant="quiet" disabled={locked || retained || pending.some(p=>p.run===run?.run_id && p.item===item.id)} onPress={()=>void advance('unknown')}>Jeg vet ikke · fortsett uten opptak</StudyButton>}
      {!saved && <StudyButton variant="quiet" disabled={locked || retained || pending.some(p=>p.run===run?.run_id && p.item===item.id)} onPress={()=>void advance('skipped')}>Hopp over</StudyButton>}
    </View> : <View style={styles.panel}><Text style={styles.heading}>Oversikten er lagret</Text><Text style={styles.body}>Vi kan sammenligne dette med et senere tilbakeblikk. Ingen hukommelsesplan er endret.</Text><StudyButton onPress={onBack}>Ferdig</StudyButton></View>}
    {pending.filter(p=>p.run===run?.run_id).map(p=><StudyButton key={p.id} disabled={locked} onPress={()=>void retry(p)}>Lagre ventende opptak</StudyButton>)}
  </ScrollView>;
}
