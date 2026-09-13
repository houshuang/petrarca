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
  if (item.needs_introduction) return <View style={styles.panel}>
    <Text style={styles.heading}>{item.title}</Text><Text style={styles.body}>{item.introduction}</Text>
    <Text style={styles.caption}>Les for å forstå hovedideen. En senere oppgave lar deg prøve uten svaret foran deg.</Text>
    <StudyButton onPress={onIntroduce}>Lest · fortsett</StudyButton>
  </View>;
  const props = {onComplete, onInteraction: onEvent};
  if (item.kind === 'aspect') return <AspectCard card={item} {...props} />;
  if (item.kind === 'sequence') return <SequenceCard card={item} {...props} />;
  if (item.kind === 'synchronic') return <SynchronicCard card={item} {...props} />;
  if (item.kind === 'causal') return <CausalChainCard card={item} {...props} />;
  const pos = item.positions[0];
  function reveal() {
    setRevealed(true); setRevealTime(Date.now()); onEvent('position_revealed', {position_id: pos.position_id});
  }
  return <View style={styles.panel}>
    <Text style={styles.heading}>{item.title}</Text><Text style={styles.body}>{pos.question_text}</Text>
    {!revealed && item.kind === 'term' && <View style={styles.row}>
      <StudyButton onPress={() => onEvent('feedback',{dimension:'term_recognition',value:'familiar'})}>Kjenner igjen ordet</StudyButton>
      <StudyButton onPress={() => onEvent('feedback',{dimension:'term_recognition',value:'unfamiliar'})}>Ukjent ord</StudyButton>
    </View>}
    {!revealed && item.kind === 'voice' && <>
      <Text style={styles.caption}>Si det du husker, gjerne med usikkerhet og spørsmål. 30–90 sekunder er nok.</Text>
      <StudyRecorder run={run} item={item.id} kind="recall" disabled={recording} onBusy={onBusy} onSaved={() => setHasAudio(true)} />
    </>}
    {!revealed ? <StudyButton disabled={item.kind === 'voice' && !hasAudio} onPress={reveal}>
      {item.kind === 'voice' ? 'Se holdepunkter for svaret' : item.kind === 'term' ? 'Vis omtrentlige betydning' : 'Vis svaret'}
    </StudyButton> : <>
      <Text style={styles.body}>{pos.answer_text}</Text>
      <Text style={styles.caption}>Sammenlign med det du tenkte eller sa før svaret kom fram.</Text>
      <StudyButton onPress={() => onComplete([{position_id:pos.position_id,score:'knew',reveal_time_ms:Date.now()-revealTime}])}>Hadde hovedideen</StudyButton>
      <StudyButton onPress={() => onComplete([{position_id:pos.position_id,score:'missed',reveal_time_ms:Date.now()-revealTime}])}>Trengte hjelp med hovedideen</StudyButton>
    </>}
  </View>;
}
