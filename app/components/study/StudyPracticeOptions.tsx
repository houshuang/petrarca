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
  return <View style={{gap:8}}>
    <Text style={styles.caption}>{practice==='extra' ? 'Ekstra øving' : 'Repetisjon og nytt stoff'} · {label}</Text>
    {practice==='extra' && <Text style={styles.caption}>Øv så mye du vil. Svarene lagres som ekstra øving; planlagte repetisjoner flyttes ikke.</Text>}
    <StudyButton disabled={disabled} onPress={()=>setExpanded(v=>!v)}>{expanded?'Lukk valg':'Velg øving og tema'}</StudyButton>
    {expanded && <View style={styles.panel}>
      <StudyButton disabled={disabled} onPress={()=>{setExpanded(false);onChoose(practice==='extra'?'scheduled':'extra',topic);}}>
        {practice==='extra'?'Til planlagt repetisjon':'Jeg vil øve mer nå'}
      </StudyButton>
      <Text style={styles.caption}>Velg et tema. Nødvendige grunnbegreper kan komme først.</Text>
      {run.topics?.map(t=><StudyButton key={t.id} disabled={disabled} onPress={()=>{setExpanded(false);onChoose(practice,t.id);}}>{t.label}{t.id===topic?' ✓':''}</StudyButton>)}
    </View>}
  </View>;
}
