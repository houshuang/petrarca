import React from 'react';
import {ScrollView, Text, View} from 'react-native';
import {colors} from '../../design/tokens';
import {styles} from './StudyControls';

const origin=-10000, end=500, width=920;
const x=(year:number)=>(year-origin)/(end-origin)*width;
const rows = [
  {label:'Arkeologi · sør/vest',bands:[[-9300,-4000,'Eldre steinalder'],[-4000,-1700,'Yngre steinalder'],[-1700,-500,'Bronsealder']]},
  {label:'Geologi',bands:[[-9700,500,'Holocen → fortsetter til i dag']]},
  {label:'Jordbruk · Oslofjorden',bands:[[-4000,500,'Tydelige tegn fra ca. 4000 fvt. →']]},
  {label:'Arkeologi · nord',bands:[[-2000,300,'Tidlig metalltid']]},
] as const;

export default function StudyTimeline() {
  return <View style={{gap:12}}>
    <Text style={styles.caption}>Sveip sidelengs. Alle radene bruker samme årsskala.</Text>
    <ScrollView horizontal contentContainerStyle={{paddingRight:20}}>
      <View style={{width:width+90,paddingTop:8}}>
        <View style={{height:34,marginLeft:10}}>{[-10000,-8000,-6000,-4000,-2000,0].map(year=><Text key={year} style={[styles.caption,{position:'absolute',left:x(year),fontSize:12}]}>{year===0?'0':`${-year} fvt.`}</Text>)}</View>
        {rows.map(row=><View key={row.label} style={{height:100}}>
          <Text style={styles.eyebrow}>{row.label}</Text>
          <View style={{height:70,marginTop:8}}>
            {[-10000,-8000,-6000,-4000,-2000,0].map(year=><View key={year} style={{position:'absolute',left:x(year),top:0,height:60,borderLeftWidth:1,borderColor:colors.rule}} />)}
            {row.bands.map(([start,stop,label])=><View key={label} style={{position:'absolute',left:x(start),width:x(stop)-x(start),height:53,padding:6,borderWidth:1,borderColor:colors.rubric,backgroundColor:colors.parchmentDark}}><Text style={[styles.caption,{fontSize:12,lineHeight:17}]}>{label}</Text></View>)}
          </View>
        </View>)}
      </View>
    </ScrollView>
    <Text style={styles.body}>På Vestlandet holdt jakt, fiske og sanking seg langt inn i yngre steinalder. Jordbruk ble viktig mot slutten av perioden. En periodegrense er derfor ingen samtidig omlegging av alle menneskers liv.</Text>
    <Text style={styles.caption}>Ca. 9300, 4000, 1700 og 500 fvt. er holdepunkter, ikke eksakte overganger overalt. «Tidlig metalltid» i nord overlapper flere sørlige perioder. Bokens kapittelinndeling er en egen fortellerstruktur og er ikke lagt inn som daterte hendelser.</Text>
  </View>;
}
