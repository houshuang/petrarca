import React, {useCallback, useEffect, useRef, useState} from 'react';
import {ActivityIndicator, AppState, Linking, ScrollView, Text, View} from 'react-native';
import {useFocusEffect} from 'expo-router';
import {setFeedbackContext} from '../../lib/feedback-context';
import {CaptureKind, Grade, PracticeMode, loadStudyRun, pendingAudio, PendingAudio, StudyRun, studyEvent, studyRequest, uploadAudio} from '../../lib/study-api';
import StudyCard from './StudyCard';
import StudyPracticeOptions from './StudyPracticeOptions';
import StudyRecorder from './StudyRecorder';
import {StudyButton, styles} from './StudyControls';

export default function StudyReview({mode, onOpenAids, onOpenAssessment, onOpenReadings, suspended=false, readingExposure}: {
  mode: 'review' | 'voice'; onOpenAids?: () => void; onOpenAssessment?: () => void;
  onOpenReadings?: (sourceIds?:string[])=>void; suspended?:boolean;
  readingExposure?:{id:string;hash:string;sequence:number}|null;
}) {
  const [run, setRun] = useState<StudyRun | null>(null);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [focused, setFocused] = useState(false);
  const [error, setError] = useState('');
  const [capture, setCapture] = useState<CaptureKind | null>(null);
  const [pending, setPending] = useState<PendingAudio[]>([]);
  // Stian's declared practice policy: these answers are always from memory.
  const bookState = 'closed';
  const [audioSaved, setAudioSaved] = useState<Set<string>>(new Set());
  const [optionsExpanded, setOptionsExpanded] = useState(false);
  const [moreExpanded, setMoreExpanded] = useState(false);
  const [qualityFeedback, setQualityFeedback] = useState<Set<string>>(new Set());
  const [briefSources,setBriefSources] = useState<Set<string>>(new Set());
  const [readingReady,setReadingReady] = useState<Set<string>>(new Set());
  const appeared = useRef(0);
  const visible = useRef(false);
  const current = useRef({run: '', item: '', bookState: 'unknown'});
  const scroll = useRef<ScrollView>(null);
  const item = run?.items[index];
  current.current = {run: run?.run_id || '', item: item?.id || '', bookState};
  const log = useCallback((event: string, detail: Record<string, unknown> = {}) => {
    const c = current.current;
    if (!c.item) return;
    if (event==='position_revealed') setReadingReady(old=>new Set([...old,c.item]));
    void studyEvent(c.run,c.item,event,{book_state:c.bookState,book_state_basis:'participant_policy_2026-09-14',...detail,
      elapsed_since_appearance_ms: Math.round(performance.now()-appeared.current)}).catch(() => setError('Hendelser er lagret på telefonen. Trykk «Prøv igjen» når du har nett.'));
  }, []);
  async function load(fresh = false, practice: PracticeMode = run?.practice || 'scheduled', topic = run?.topic || 'all') {
    setBusy(true); setError('');
    try {
      const next = await loadStudyRun(mode,fresh,practice,topic);
      setRun(next); setCapture(null); setOptionsExpanded(false); setIndex(next.items.findIndex(i => !next.completed_ids.includes(i.id)) < 0 ? next.items.length : next.items.findIndex(i => !next.completed_ids.includes(i.id)));
      setPending(await pendingAudio()); setAudioSaved(new Set(next.audio_item_ids || []));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, [mode]);
  useEffect(() => {
    if (mode!=='review') return;
    void studyRequest<{readings:{source_id:string}[]}>('readings')
      .then(result=>setBriefSources(new Set(result.readings.map(r=>r.source_id))))
      .catch(()=>undefined);
  },[mode]);
  useEffect(()=>{
    if (!readingExposure || !current.current.item) return;
    log('feedback',{dimension:'reading_help',brief_id:readingExposure.id,
      content_sha256:readingExposure.hash,exposure_only:true});
  },[readingExposure?.sequence,log]);
  useEffect(()=>{if (!suspended) setFeedbackContext({screen:`norway-study-${mode}`});},[suspended,mode]);
  useFocusEffect(useCallback(() => {
    visible.current = true; setFocused(true); setFeedbackContext({screen:`norway-study-${mode}`});
    appeared.current = performance.now(); log('foregrounded', {reason:'screen_focus'});
    void pendingAudio().then(setPending);
    return () => { log('session_left', {reason:'screen_blur'}); visible.current = false; setFocused(false); };
  }, [mode, log]));
  useEffect(() => {
    if (!item || !focused || optionsExpanded || suspended) return;
    appeared.current = performance.now();
    log('shown', {
      exposure_version:'visible-card-v2',
      visible_content:'card',
      format:item.kind, content_version:item.version,
      visible_anchor_rule: ['causal','synchronic'].includes(item.kind) ? 'first position shown' : item.kind==='sequence' ? 'all except two most-due shown' : 'none',
    });
    scroll.current?.scrollTo({y: 0, animated:false});
  }, [run?.run_id, item?.id, focused, optionsExpanded, suspended, log]);
  useEffect(() => {
    setMoreExpanded(false);
    setQualityFeedback(new Set());
    setCapture(null);
  }, [item?.id]);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (!visible.current) return;
      if (state === 'active') { appeared.current = performance.now(); log('foregrounded',{reason:'app_state'}); void pendingAudio().then(setPending); }
      else log('backgrounded',{state});
    });
    return () => subscription.remove();
  }, [log]);
  async function finish(event: 'complete' | 'introduced' | 'skip', results?: Grade[]) {
    if (!run || !item || busy || recording) return;
    setBusy(true); setError('');
    try {
      await studyEvent(run.run_id,item.id,event,{book_state:bookState,book_state_basis:'participant_policy_2026-09-14',
        elapsed_since_appearance_ms:Math.round(performance.now()-appeared.current),assessment:'self_report'},results);
      setCapture(null); setIndex(i => i + 1);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  async function retryAudio(entry: PendingAudio) {
    setBusy(true); setError('');
    try {
      await uploadAudio(entry); setPending(await pendingAudio());
      if (entry.kind === 'recall') setAudioSaved(old => new Set([...old,entry.item]));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  function recordQuality(value: string) {
    if (qualityFeedback.has(value)) return;
    setQualityFeedback(old => new Set([...old, value]));
    log('feedback', {dimension: 'card_quality', value});
  }

  return <ScrollView ref={scroll} style={styles.page} contentContainerStyle={styles.content}
    contentInsetAdjustmentBehavior="automatic"
    onScrollEndDrag={e => log('scroll',{offset_y:e.nativeEvent.contentOffset.y,viewport_height:e.nativeEvent.layoutMeasurement.height,content_height:e.nativeEvent.contentSize.height})}>
    <View style={styles.compactRow}>
      <Text accessibilityRole="header" style={styles.eyebrow}>Norgeshistorie{item ? ` · ${index + 1} / ${run?.items.length}` : ''}</Text>
      <StudyButton variant="quiet" compact disabled={busy || recording} onPress={()=>{setOptionsExpanded(value=>!value);log('feedback',{dimension:'practice_options',value:!optionsExpanded});}}>{optionsExpanded ? 'Tilbake' : 'Valg'}</StudyButton>
    </View>
    {!!error && <View style={styles.panel}><Text style={styles.error}>{error}</Text><StudyButton disabled={busy} onPress={() => void load()}>Prøv igjen</StudyButton></View>}
    {pending.length > 0 && <View style={styles.panel}><Text style={styles.caption}>Opptak som venter på lagring</Text>
      {pending.map(p => <StudyButton key={p.id} disabled={busy} onPress={() => void retryAudio(p)}>Lagre {p.kind} · {p.item.replace('no-p1-','')}</StudyButton>)}
    </View>}
    {busy && <ActivityIndicator />}
    {optionsExpanded && <View style={styles.detailsPanel}>
      {run && <StudyPracticeOptions run={run} disabled={busy || recording}
        onChoose={(practice,topic)=>{log('feedback',{dimension:'practice_selection',practice,topic});void load(true,practice,topic);}} />}
      {onOpenAids && <StudyButton onPress={()=>{setOptionsExpanded(false);onOpenAids();}}>Bilder og tidslinje</StudyButton>}
      {onOpenReadings && <StudyButton onPress={()=>{setOptionsExpanded(false);onOpenReadings();}}>Det du lurte på · korte forklaringer</StudyButton>}
      {onOpenAssessment && <StudyButton onPress={onOpenAssessment}>Fortell oversikten · uten fasit</StudyButton>}
    </View>}
    <View style={optionsExpanded ? {display:'none'} : {gap:14}}>
    {item && run ? <>
        <View pointerEvents={busy ? 'none' : 'auto'}>
          <StudyCard key={`${run.run_id}-${item.id}-${audioSaved.has(item.id)}`} visible={focused && !optionsExpanded && !suspended} item={item} run={run.run_id} onEvent={log}
            onComplete={results => void finish('complete',results)} onIntroduce={() => void finish('introduced')}
            onBusy={setRecording} recording={recording} audioSaved={audioSaved.has(item.id)} />
        </View>
        {onOpenReadings && readingReady.has(item.id) && item.sources.some(s=>briefSources.has(s.recording)) &&
          <StudyButton onPress={()=>onOpenReadings(item.sources.map(s=>s.recording))}>Forklar kort</StudyButton>}
        <StudyButton variant="quiet" disabled={busy || recording} onPress={() => void finish('skip')}>Hopp over dette kortet</StudyButton>
        <StudyButton
          variant="quiet"
          selected={moreExpanded}
          disabled={busy || recording}
          onPress={() => setMoreExpanded(value => !value)}
        >
          {moreExpanded ? 'Skjul mer om kortet' : 'Mer om dette kortet'}
        </StudyButton>
        {moreExpanded && <View style={styles.detailsPanel}>
          <Text style={styles.eyebrow}>Ta vare på en tanke</Text>
          <Text style={styles.caption}>Valgfritt: spill inn noe kortet vekket eller noe som bør rettes.</Text>
          <View style={styles.row}>{(['wondering','correction','reflection'] as CaptureKind[]).map(k =>
            <StudyButton variant="choice" selected={capture === k} key={k} disabled={recording || busy} onPress={() => {setCapture(k);log('feedback',{dimension:'capture_intent',value:k});}}>
              {k==='wondering'?'Jeg lurer på …':k==='correction'?'Noe er feil':'Tanken min har endret seg'}
            </StudyButton>)}</View>
          {capture && focused && <StudyRecorder key={`${item.id}-${capture}`} run={run.run_id} item={item.id} kind={capture}
            disabled={recording} onBusy={setRecording} onSaved={() => {setCapture(null); void pendingAudio().then(setPending);}} />}
          <Text style={styles.eyebrow}>Hvordan var kortet?</Text>
          <View style={styles.row}>
            <StudyButton compact variant="choice" selected={qualityFeedback.has('useful')} onPress={() => recordQuality('useful')}>Nyttig</StudyButton>
            <StudyButton compact variant="choice" selected={qualityFeedback.has('confusing')} onPress={() => recordQuality('confusing')}>Uklart</StudyButton>
            <StudyButton compact variant="choice" selected={qualityFeedback.has('too_detailed')} onPress={() => recordQuality('too_detailed')}>For detaljert</StudyButton>
            <StudyButton compact variant="choice" selected={qualityFeedback.has('too_easy')} onPress={() => recordQuality('too_easy')}>For lett</StudyButton>
          </View>
          {qualityFeedback.size > 0 && <Text accessibilityLiveRegion="polite" style={styles.caption}>Takk — tilbakemeldingen er registrert.</Text>}
          {(item.evidence_note || item.sources.length > 0 || item.references.length > 0) && <>
            <Text style={styles.eyebrow}>Kilder og opphav</Text>
            <Text style={styles.caption}>Fra lesingen din · opplest tekst kan være sitater.</Text>
            {item.evidence_note && <Text style={styles.caption}>{item.evidence_note}</Text>}
            {item.sources.map((source,i) => <StudyButton variant="link" key={i} onPress={() => {
              log('source_opened',{recording:source.recording,segment:source.segment});
              void Linking.openURL(source.tana_link).catch(() => setError('Kunne ikke åpne Tana.'));
            }}>{source.recording} {source.start_ms != null ? `· ${Math.floor(source.start_ms/60000)}:${String(Math.floor(source.start_ms/1000)%60).padStart(2,'0')}` : ''}</StudyButton>)}
            {item.references.map(ref => <StudyButton variant="link" key={ref.url} onPress={() => {log('source_opened',{reference_url:ref.url}); void Linking.openURL(ref.url).catch(() => setError('Kunne ikke åpne kilden.'));}}>{ref.title}</StudyButton>)}
          </>}
        </View>}
    </> : !busy && run && <View style={styles.panel}>
      <Text style={styles.heading}>Fint sted å stoppe</Text>
      <Text style={styles.body}>Du kan stoppe her eller fortsette med flere oppgaver.</Text>
      {run.availability?.next_due_at && <Text style={styles.caption}>Neste planlagte repetisjon: {new Date(run.availability.next_due_at).toLocaleString('nb-NO',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</Text>}
      {!run.items.length && <Text style={styles.caption}>Ingen oppgaver klare i dette utvalget akkurat nå. Velg et annet tema eller prøv igjen litt senere.</Text>}
      <StudyButton variant="primary" onPress={() => void load(true)}>Neste runde</StudyButton>
      {run.practice !== 'extra' && <StudyButton onPress={()=>void load(true,'extra')}>Øv videre selv om ingenting er forfalt</StudyButton>}
    </View>}
    </View>
  </ScrollView>;
}
