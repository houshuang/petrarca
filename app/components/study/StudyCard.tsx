import React, {useState} from 'react';
import {Text, View} from 'react-native';
import AspectCard from '../AspectCard';
import SequenceCard from '../SequenceCard';
import SynchronicCard from '../SynchronicCard';
import CausalChainCard from '../CausalChainCard';
import {StudyItem, Grade} from '../../lib/study-api';
import StudyRecorder from './StudyRecorder';
import {StudyButton, styles} from './StudyControls';

export default function StudyCard({item, run, onEvent, onComplete, onIntroduce, onBusy, audioSaved, recording}: {
  item: StudyItem; run: string; onEvent: (event: string, detail?: Record<string, unknown>) => void;
  onComplete: (results: Grade[]) => void; onIntroduce: () => void; onBusy: (busy: boolean) => void; audioSaved: boolean; recording: boolean;
}) {
  const [revealed, setRevealed] = useState(false);
  const [hasAudio, setHasAudio] = useState(audioSaved);
  const [revealTime, setRevealTime] = useState(0);
  const [recognition, setRecognition] = useState<'familiar' | 'unfamiliar' | null>(null);

  function chooseRecognition(value: 'familiar' | 'unfamiliar') {
    if (recognition === value) return;
    setRecognition(value);
    onEvent('feedback', {dimension: 'term_recognition', value});
  }

  if (item.needs_introduction) return <View style={styles.panel}>
    <Text style={styles.eyebrow}>Ny idé · les for å forstå</Text>
    <Text accessibilityRole="header" style={styles.heading}>{item.title}</Text>
    <Text style={styles.body}>{item.introduction}</Text>
    <Text style={styles.caption}>Du skal ikke huske alt nå. En senere oppgave spør etter hovedideen.</Text>
    <StudyButton variant="primary" onPress={onIntroduce}>Jeg har lest · fortsett</StudyButton>
  </View>;
  const props = {onComplete, onInteraction: onEvent};
  if (item.kind === 'aspect') return <View style={{gap: 8}}><Text style={styles.eyebrow}>Sammenheng · finn den manglende delen</Text><AspectCard card={item} {...props} /></View>;
  if (item.kind === 'sequence') return <View style={{gap: 8}}><Text style={styles.eyebrow}>Tidslinje · plasser periodene</Text><SequenceCard card={item} {...props} /></View>;
  if (item.kind === 'synchronic') return <View style={{gap: 8}}><Text style={styles.eyebrow}>Samtidig · koble steder og hendelser</Text><SynchronicCard card={item} {...props} /></View>;
  if (item.kind === 'causal') return <View style={{gap: 8}}><Text style={styles.eyebrow}>Årsak · forklar forbindelsen</Text><CausalChainCard card={item} {...props} /></View>;
  const pos = item.positions[0];
  function reveal() {
    setRevealed(true); setRevealTime(Date.now()); onEvent('position_revealed', {position_id: pos.position_id});
  }
  return <View style={styles.panel}>
    <Text style={styles.eyebrow}>{item.kind === 'term' ? 'Begrep · omtrentlig betydning' : item.kind === 'voice' ? 'Fortell · 30–90 sekunder' : 'Spørsmål · hovedidé'}</Text>
    <Text accessibilityRole="header" style={styles.heading}>{item.title}</Text>
    <Text style={styles.body}>{pos.question_text}</Text>
    {!revealed && item.kind === 'term' && <>
      <Text style={styles.caption}>Tenk først: Hva tror du ordet betyr? Velg så om det virket kjent.</Text>
      <View accessibilityRole="radiogroup" style={styles.row}>
        <StudyButton
          variant="choice"
          selected={recognition === 'familiar'}
          onPress={() => chooseRecognition('familiar')}
        >
          {recognition === 'familiar' ? '✓ Kjenner igjen ordet' : 'Kjenner igjen ordet'}
        </StudyButton>
        <StudyButton
          variant="choice"
          selected={recognition === 'unfamiliar'}
          onPress={() => chooseRecognition('unfamiliar')}
        >
          {recognition === 'unfamiliar' ? '✓ Ukjent ord' : 'Ukjent ord'}
        </StudyButton>
      </View>
      {recognition && <Text accessibilityLiveRegion="polite" style={styles.caption}>Registrert. Vis betydningen når du er klar.</Text>}
    </>}
    {!revealed && item.kind === 'voice' && <>
      <Text style={styles.caption}>Si det du husker, gjerne med usikkerhet og spørsmål. 30–90 sekunder er nok.</Text>
      <StudyRecorder run={run} item={item.id} kind="recall" disabled={recording} onBusy={onBusy} onSaved={() => setHasAudio(true)} />
    </>}
    {!revealed ? <StudyButton variant="primary" disabled={item.kind === 'voice' && !hasAudio} onPress={reveal}>
      {item.kind === 'voice' ? 'Se holdepunkter for svaret' : item.kind === 'term' ? 'Vis omtrentlig betydning' : 'Vis svaret'}
    </StudyButton> : <>
      <Text style={styles.eyebrow}>Det viktigste</Text>
      <Text style={styles.body}>{pos.answer_text}</Text>
      <Text style={styles.caption}>Sammenlign med det du tenkte eller sa før svaret kom fram.</Text>
      <StudyButton variant="primary" onPress={() => onComplete([{position_id:pos.position_id,score:'knew',reveal_time_ms:Date.now()-revealTime}])}>Jeg hadde hovedideen</StudyButton>
      <StudyButton onPress={() => onComplete([{position_id:pos.position_id,score:'missed',reveal_time_ms:Date.now()-revealTime}])}>Jeg trengte svaret</StudyButton>
    </>}
  </View>;
}
