import React, {useState} from 'react';
import {Text, View} from 'react-native';
import {PracticeMode, StudyRun} from '../../lib/study-api';
import {StudyButton, styles} from './StudyControls';

export default function StudyPracticeOptions({run, disabled, onChoose}: {
  run: StudyRun; disabled: boolean; onChoose: (practice: PracticeMode, topic: string) => void;
}) {
  const [expanded,setExpanded]=useState(false);
  const practice=run.practice || 'scheduled';
  const topic=run.topic || 'all';
  const label=run.topics?.find(t=>t.id===topic)?.label || 'Alle temaer';
  return <View style={{gap:4}}>
    <View style={styles.selectionSummary}>
      <View style={{flex:1}}>
        <Text style={styles.eyebrow}>Denne økten</Text>
        <Text style={styles.caption}>{practice==='extra' ? 'Ekstra øving' : 'Planlagt repetisjon'} · {label}</Text>
      </View>
      <StudyButton variant="quiet" compact disabled={disabled} onPress={()=>setExpanded(v=>!v)}>{expanded?'Lukk':'Bytt'}</StudyButton>
    </View>
    {practice==='extra' && <Text style={styles.caption}>Ekstra øving flytter ikke neste planlagte repetisjon.</Text>}
    {expanded && <View style={styles.panel}>
      <Text style={styles.eyebrow}>Type økt</Text>
      <StudyButton variant="choice" disabled={disabled} onPress={()=>{setExpanded(false);onChoose(practice==='extra'?'scheduled':'extra',topic);}}>
        {practice==='extra'?'Til planlagt repetisjon':'Jeg vil øve mer nå'}
      </StudyButton>
      <Text style={styles.eyebrow}>Tema</Text>
      <Text style={styles.caption}>Nødvendige grunnbegreper kan komme først.</Text>
      {run.topics?.map(t=><StudyButton variant="choice" selected={t.id===topic} key={t.id} disabled={disabled} onPress={()=>{setExpanded(false);onChoose(practice,t.id);}}>{t.id===topic?'✓ ':''}{t.label}</StudyButton>)}
    </View>}
  </View>;
}
