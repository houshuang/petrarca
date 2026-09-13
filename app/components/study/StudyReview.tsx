import React, {useCallback, useEffect, useRef, useState} from 'react';
import {ActivityIndicator, AppState, Linking, ScrollView, Text, View} from 'react-native';
import {useFocusEffect} from 'expo-router';
import {setFeedbackContext} from '../../lib/feedback-context';
import {CaptureKind, Grade, PracticeMode, loadStudyRun, pendingAudio, PendingAudio, StudyRun, studyEvent, uploadAudio} from '../../lib/study-api';
import StudyCard from './StudyCard';
import StudyPracticeOptions from './StudyPracticeOptions';
import StudyRecorder from './StudyRecorder';
import {StudyButton, styles} from './StudyControls';

export default function StudyReview({mode}: {mode: 'review' | 'voice'}) {
  const [run, setRun] = useState<StudyRun | null>(null);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [focused, setFocused] = useState(false);
  const [error, setError] = useState('');
  const [capture, setCapture] = useState<CaptureKind | null>(null);
  const [pending, setPending] = useState<PendingAudio[]>([]);
  const [bookState, setBookState] = useState('unknown');
  const [audioSaved, setAudioSaved] = useState<Set<string>>(new Set());
  const appeared = useRef(0);
  const visible = useRef(false);
  const current = useRef({run: '', item: '', bookState: 'unknown'});
  const scroll = useRef<ScrollView>(null);
  const item = run?.items[index];
  current.current = {run: run?.run_id || '', item: item?.id || '', bookState};
  const log = useCallback((event: string, detail: Record<string, unknown> = {}) => {
    const c = current.current;
    if (!c.item) return;
    void studyEvent(c.run,c.item,event,{...detail,book_state:c.bookState,
      elapsed_since_appearance_ms: Math.round(performance.now()-appeared.current)}).catch(() => setError('Hendelser er lagret på telefonen. Trykk «Prøv igjen» når du har nett.'));
  }, []);
  async function load(fresh = false, practice: PracticeMode = run?.practice || 'scheduled', topic = run?.topic || 'all') {
    setBusy(true); setError('');
    try {
      const next = await loadStudyRun(mode,fresh,practice,topic);
      setRun(next); setCapture(null); setBookState('unknown'); setIndex(next.items.findIndex(i => !next.completed_ids.includes(i.id)) < 0 ? next.items.length : next.items.findIndex(i => !next.completed_ids.includes(i.id)));
      setPending(await pendingAudio()); setAudioSaved(new Set(next.audio_item_ids || []));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, [mode]);
  useFocusEffect(useCallback(() => {
    visible.current = true; setFocused(true); setFeedbackContext({screen:`norway-study-${mode}`});
    appeared.current = performance.now(); log('foregrounded', {reason:'screen_focus'});
    void pendingAudio().then(setPending);
    return () => { log('session_left', {reason:'screen_blur'}); visible.current = false; setFocused(false); };
  }, [mode, log]));
  useEffect(() => {
    if (!item || !focused) return;
    appeared.current = performance.now();
    log(item.needs_introduction ? 'introduction_shown' : 'shown', {
      format:item.kind, content_version:item.version,
      visible_anchor_rule: ['causal','synchronic'].includes(item.kind) ? 'first position shown' : item.kind==='sequence' ? 'all except two most-due shown' : 'none',
    });
    scroll.current?.scrollTo({y: 0, animated:false});
  }, [item?.id, focused, log]);
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
      await studyEvent(run.run_id,item.id,event,{book_state:bookState,
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
  return <ScrollView ref={scroll} style={styles.page} contentContainerStyle={styles.content}
    onScrollEndDrag={e => log('scroll',{offset_y:e.nativeEvent.contentOffset.y,viewport_height:e.nativeEvent.layoutMeasurement.height,content_height:e.nativeEvent.contentSize.height})}>
    <Text style={styles.title}>Norgeshistorie</Text>
    <Text style={styles.caption}>Bind 1 · {mode==='voice' ? 'Fortell fra hukommelsen' : 'Begreper og sammenhenger'} · andre kort er satt på pause</Text>
    {!!error && <View style={styles.panel}><Text style={styles.error}>{error}</Text><StudyButton disabled={busy} onPress={() => void load()}>Prøv igjen</StudyButton></View>}
    {pending.length > 0 && <View style={styles.panel}><Text style={styles.caption}>Opptak som venter på lagring</Text>
      {pending.map(p => <StudyButton key={p.id} disabled={busy} onPress={() => void retryAudio(p)}>Lagre {p.kind} · {p.item.replace('no-p1-','')}</StudyButton>)}
    </View>}
    {busy && <ActivityIndicator />}
    {run && <StudyPracticeOptions run={run} disabled={busy || recording}
      onChoose={(practice,topic)=>{log('feedback',{dimension:'practice_selection',practice,topic});void load(true,practice,topic);}} />}
    {item && run ? <>
      <Text style={styles.caption}>{index + 1} av {run.items.length} · du kan stoppe når du vil</Text>
      <View style={styles.row}>
        <StudyButton disabled={busy} onPress={() => {setBookState('closed'); log('feedback',{dimension:'book_state',value:'closed'});}}>Boken lukket {bookState==='closed'?'✓':''}</StudyButton>
        <StudyButton disabled={busy} onPress={() => {setBookState('open'); log('feedback',{dimension:'book_state',value:'open'});}}>Boken åpen {bookState==='open'?'✓':''}</StudyButton>
      </View>
      <View pointerEvents={busy ? 'none' : 'auto'}>
        <StudyCard key={`${run.run_id}-${item.id}-${audioSaved.has(item.id)}`} item={item} run={run.run_id} onEvent={log}
          onComplete={results => void finish('complete',results)} onIntroduce={() => void finish('introduced')}
          onBusy={setRecording} recording={recording} audioSaved={audioSaved.has(item.id)} />
      </View>
      <StudyButton disabled={busy || recording} onPress={() => void finish('skip')}>Hopp over</StudyButton>
      <View style={styles.panel}>
        <Text style={styles.caption}>Noe du vil ta vare på?</Text>
        <View style={styles.row}>{(['wondering','correction','reflection'] as CaptureKind[]).map(k =>
          <StudyButton key={k} disabled={recording || busy} onPress={() => {setCapture(k);log('feedback',{dimension:'capture_intent',value:k});}}>
            {k==='wondering'?'Jeg lurer på …':k==='correction'?'Noe er feil':'Tanken min har endret seg'}
          </StudyButton>)}</View>
        {capture && focused && <StudyRecorder key={`${item.id}-${capture}`} run={run.run_id} item={item.id} kind={capture}
          disabled={recording} onBusy={setRecording} onSaved={() => {setCapture(null); void pendingAudio().then(setPending);}} />}
        <View style={styles.row}>
          <StudyButton onPress={() => log('feedback',{dimension:'card_quality',value:'useful'})}>Nyttig</StudyButton>
          <StudyButton onPress={() => log('feedback',{dimension:'card_quality',value:'confusing'})}>Uklart</StudyButton>
          <StudyButton onPress={() => log('feedback',{dimension:'card_quality',value:'too_detailed'})}>For detaljert</StudyButton>
          <StudyButton onPress={() => log('feedback',{dimension:'card_quality',value:'too_easy'})}>For lett</StudyButton>
        </View>
      </View>
      <View style={{gap:8}}>
        <Text style={styles.caption}>Fra lesingen din · opplest tekst kan være sitater</Text>
        {item.evidence_note && <Text style={styles.caption}>{item.evidence_note}</Text>}
        {item.sources.map((source,i) => <StudyButton key={i} onPress={() => {
          log('source_opened',{recording:source.recording,segment:source.segment});
          void Linking.openURL(source.tana_link).catch(() => setError('Kunne ikke åpne Tana.'));
        }}>{source.recording} {source.start_ms != null ? `· ${Math.floor(source.start_ms/60000)}:${String(Math.floor(source.start_ms/1000)%60).padStart(2,'0')}` : ''}</StudyButton>)}
        {item.references.map(ref => <StudyButton key={ref.url} onPress={() => {log('source_opened',{reference_url:ref.url}); void Linking.openURL(ref.url).catch(() => setError('Kunne ikke åpne kilden.'));}}>{ref.title}</StudyButton>)}
      </View>
    </> : !busy && run && <View style={styles.panel}>
      <Text style={styles.heading}>Fint sted å stoppe</Text>
      <Text style={styles.body}>Du kan stoppe her eller fortsette med flere oppgaver.</Text>
      {run.availability?.next_due_at && <Text style={styles.caption}>Neste planlagte repetisjon: {new Date(run.availability.next_due_at).toLocaleString('nb-NO',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</Text>}
      {!run.items.length && <Text style={styles.caption}>Ingen oppgaver klare i dette utvalget akkurat nå. Velg et annet tema eller prøv igjen litt senere.</Text>}
      <StudyButton onPress={() => void load(true)}>Neste runde</StudyButton>
      {run.practice !== 'extra' && <StudyButton onPress={()=>void load(true,'extra')}>Øv videre selv om ingenting er forfalt</StudyButton>}
    </View>}
  </ScrollView>;
}
