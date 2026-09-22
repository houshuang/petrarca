import React, {useCallback, useEffect, useState} from 'react';
import {ActivityIndicator, Image, Linking, ScrollView, Text, View} from 'react-native';
import {logEvent} from '../../data/logger';
import {setFeedbackContext} from '../../lib/feedback-context';
import {studyRequest} from '../../lib/study-api';
import {StudyButton, styles} from './StudyControls';
import PetrarcaDrawer from '../PetrarcaDrawer';

type Target = {id:string;topic:string;question:string;answer:string;selected:boolean};
export type Reading = {id:string;intent_id:string;source_id:string;source_quote:string;
  source_date?:string|null;source_title?:string|null;source_url?:string|null;title:string;question:string;text:string;
  citations:{title:string;url:string}[];targets:Target[];content_sha256:string;
  illustration?:string|null};
type Catalogue = {readings:Reading[]};
type Selection = {added:string[];selected:string[];already_selected:number};

export default function StudyReadings({onBack, sourceIds, onShown}: {
  onBack:()=>void; sourceIds?:string[]; onShown:(reading:Reading)=>void;
}) {
  const [all,setAll]=useState<Reading[]|null>(null);
  const [active,setActive]=useState<string|null>(null);
  const [selected,setSelected]=useState<string[]>([]);
  const [choosing,setChoosing]=useState(false);
  const [quoteOpen,setQuoteOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [retry,setRetry]=useState<'load'|'save'|null>(null);
  const [receipt,setReceipt]=useState('');
  const [drawer,setDrawer]=useState(false);
  const load=useCallback(async()=>{
    setBusy(true);setError('');setRetry(null);
    try {
      const response=await studyRequest<Catalogue>('readings');
      setAll(response.readings);
      if (sourceIds?.length) {
        const match=response.readings.find(r=>sourceIds.includes(r.source_id));
        if (match) setActive(match.id);
      }
    } catch {setError('Kunne ikke hente de korte forklaringene. Sjekk nettet og prøv igjen.');setRetry('load');}
    finally {setBusy(false);}
  },[sourceIds?.join('|')]);
  useEffect(()=>{setFeedbackContext({screen:'study-bounded-readings'});logEvent('study_readings_open',{source_ids:sourceIds||[]});void load();},[load]);
  const readings=sourceIds?.length ? (all||[]).filter(r=>sourceIds.includes(r.source_id)) : all||[];
  const reading=readings.find(r=>r.id===active);
  useEffect(()=>{
    if (!reading) return;
    onShown(reading);
    logEvent('study_reading_shown',{brief_id:reading.id,intent_id:reading.intent_id,
      content_sha256:reading.content_sha256,source_id:reading.source_id,exposure_only:true});
  },[reading?.id,reading?.content_sha256]);
  function open(readingId:string) {
    setActive(readingId);setSelected([]);setChoosing(false);setQuoteOpen(false);setReceipt('');setError('');
    logEvent(readingId?'study_reading_chosen':'study_reading_list_returned',{brief_id:readingId||undefined});
  }
  function toggle(id:string) {
    setSelected(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id]);
    logEvent('study_reading_target_toggled',{brief_id:reading?.id,target_id:id});
  }
  async function save() {
    if (!reading || !selected.length || busy) return;
    setBusy(true);setError('');setRetry(null);
    try {
      const result=await studyRequest<Selection>('readings/select',{brief_id:reading.id,target_ids:selected});
      setAll(old=>old?.map(r=>({...r,targets:r.targets.map(t=>result.selected.includes('no-reading-'+t.id)?{...t,selected:true}:t)}))||null);
      setReceipt(`${result.added.length} ${result.added.length===1?'nytt spørsmål':'nye spørsmål'} lagt til øvingen.${result.already_selected ? ` ${result.already_selected} var allerede valgt.`:''}`);
      setSelected([]);setChoosing(false);
      logEvent('study_reading_targets_selected',{brief_id:reading.id,target_ids:selected,added:result.added.length,
        already_selected:result.already_selected});
    } catch {setError('Kunne ikke legge til spørsmålene. Valgene dine er bevart; prøv igjen når du har nett.');setRetry('save');}
    finally {setBusy(false);}
  }
  return <ScrollView style={styles.page} contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
    <PetrarcaDrawer visible={drawer} onClose={()=>setDrawer(false)} />
    <StudyButton variant="quiet" onPress={()=>setDrawer(true)}>✦</StudyButton>
    <Text accessibilityRole="header" style={styles.title}>{reading?.title || 'Det du lurte på'}</Text>
    <StudyButton variant="quiet" onPress={()=>{logEvent('study_readings_back',{brief_id:reading?.id});onBack();}}>Tilbake til øving</StudyButton>
    {!!error && <View style={styles.panel}><Text style={styles.error}>{error}</Text>
      {retry && <StudyButton disabled={busy} onPress={()=>void (retry==='save'?save():load())}>Prøv igjen</StudyButton>}</View>}
    {busy && <ActivityIndicator />}
    {!reading ? <>
      <Text style={styles.body}>Korte forklaringer fra spørsmål du stilte mens du leste. Ingen blir en øvingsoppgave før du velger den.</Text>
      {all && !readings.length && <Text style={styles.caption}>Ingen forklaring er klargjort for dette kortet ennå.</Text>}
      {readings.map(r=><View key={r.id} style={styles.detailsPanel}>
        <Text style={styles.eyebrow}>{r.source_title||'Lesernotat'}{r.source_date?` · ${r.source_date.slice(0,10)}`:''}</Text>
        <StudyButton variant="link" onPress={()=>open(r.id)}>{r.question}</StudyButton>
        <Text style={styles.caption}>Omtrent {r.text.trim().split(/\s+/).length} ord · valgfritt</Text>
      </View>)}
    </> : <View style={{gap:14}}>
      <Text style={styles.eyebrow}>Forklar kort · fra ditt eget spørsmål</Text>
      <Text style={styles.caption}>{reading.question}</Text>
      {reading.text.split(/\n\s*\n/).map((paragraph,i)=><Text key={i} style={styles.body} selectable>{paragraph}</Text>)}
      {reading.illustration==='karveskurd-diagram-v1' && <View style={styles.panel}>
        <Image source={require('../../assets/study/karveskurd-diagram-v1.png')}
          style={{width:'100%',aspectRatio:960/510}} resizeMode="contain"
          accessibilityLabel="Prinsippskisse av et V-formet snitt skåret ned i en overflate; ikke en gjengivelse av et arkeologisk funn." />
        <Text style={styles.caption}>Prinsippskisse · ikke et arkeologisk funn.</Text>
      </View>}
      <Text style={styles.caption}>Å lese dette teller som støtte, ikke som at du husker det uten hjelp.</Text>
      <View style={styles.detailsPanel}>
        <Text style={styles.eyebrow}>Kilder</Text>
        {reading.citations.map(c=><StudyButton key={c.url} variant="link" onPress={()=>{
          logEvent('study_reading_source_opened',{brief_id:reading.id,url:c.url});
          void Linking.openURL(c.url).catch(()=>setError('Kunne ikke åpne kilden.'));
        }}>{c.title}</StudyButton>)}
        {reading.source_url && <StudyButton variant="quiet" onPress={()=>{
          logEvent('study_reading_original_opened',{brief_id:reading.id,source_id:reading.source_id});
          void Linking.openURL(reading.source_url!).catch(()=>setError('Kunne ikke åpne lesernotatet.'));
        }}>Åpne lesernotatet</StudyButton>}
        <StudyButton variant="quiet" onPress={()=>{setQuoteOpen(v=>!v);logEvent('study_reading_quote_toggled',{brief_id:reading.id,shown:!quoteOpen});}}>{quoteOpen?'Skjul':'Vis'} den opprinnelige formuleringen</StudyButton>
        {quoteOpen && <Text style={styles.caption} selectable>{reading.source_quote}</Text>}
      </View>
      {!!receipt && <Text accessibilityLiveRegion="polite" style={styles.caption}>{receipt}</Text>}
      {!choosing ? <StudyButton onPress={()=>{setChoosing(true);logEvent('study_reading_quiz_options_opened',{brief_id:reading.id});}}>Velg spørsmål å øve på</StudyButton>
        : <View style={styles.detailsPanel}>
          <Text style={styles.eyebrow}>Valgfrie spørsmål · maks tre</Text>
          {reading.targets.length===0 && <Text style={styles.caption}>Ingen øvingsspørsmål er foreslått for denne forklaringen.</Text>}
          {reading.targets.map(t=><View key={t.id} style={{gap:5}}>
            <StudyButton variant="choice" selected={t.selected||selected.includes(t.id)} disabled={t.selected||busy}
              onPress={()=>toggle(t.id)}>{t.selected?'✓ Allerede i øvingen':selected.includes(t.id)?'✓ Valgt':'Velg'} · {t.question}</StudyButton>
            <Text style={styles.caption}>{t.selected?'Dette spørsmålet er allerede planlagt.':'Hva det spør om: '+t.answer}</Text>
          </View>)}
          <StudyButton variant="primary" disabled={!selected.length||busy} onPress={()=>void save()}>
            Legg til {selected.length} {selected.length===1?'spørsmål':'spørsmål'}
          </StudyButton>
          <StudyButton variant="quiet" onPress={()=>{setChoosing(false);setSelected([]);logEvent('study_reading_quiz_options_closed',{brief_id:reading.id});}}>La være nå</StudyButton>
        </View>}
      <StudyButton variant="quiet" onPress={()=>open('')}>Andre korte forklaringer</StudyButton>
    </View>}
  </ScrollView>;
}
