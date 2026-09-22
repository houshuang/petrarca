import React from 'react';
import TestRenderer, {act,ReactTestInstance} from 'react-test-renderer';
import StudyReadings from '../components/study/StudyReadings';
import {studyRequest} from '../lib/study-api';

(globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
jest.mock('react-native',()=>({View:'View',Text:'Text',ScrollView:'ScrollView',ActivityIndicator:'Spinner',Image:'Image',Linking:{openURL:jest.fn()}}));
jest.mock('../lib/study-api',()=>({studyRequest:jest.fn()}));
jest.mock('../lib/feedback-context',()=>({setFeedbackContext:jest.fn()}));
jest.mock('../data/logger',()=>({logEvent:jest.fn()}));
jest.mock('../components/PetrarcaDrawer',()=>()=>null);
jest.mock('../components/study/StudyControls',()=>({
  styles:{page:{},content:{},title:{},body:{},caption:{},panel:{},error:{},eyebrow:{},detailsPanel:{}},
  StudyButton:({children,onPress,disabled}:{children:React.ReactNode;onPress:()=>void;disabled?:boolean})=>
    require('react').createElement('Button',{onPress,disabled},children),
}));

const reading={id:'brief-fixture',intent_id:'wonder-fixture',source_id:'original-fixture',
  source_quote:'I wonder how it works.',source_title:'My original note',source_date:'2026-09-18T10:00:00Z',
  source_url:'https://app.tana.inc/fixture',title:'Short explanation',question:'How?',
  text:'A short explanation for testing the interaction.',content_sha256:'abc123',
  citations:[{title:'Source',url:'https://example.org/source'}],
  targets:[{id:'target-fixture',topic:'concepts',question:'What is it?',answer:'An answer.',selected:false}]};
function text(node:ReactTestInstance):string {
  return node.children.map(child=>typeof child==='string'?child:text(child)).join('');
}
function button(root:ReactTestInstance,part:string) {
  return root.findAll(node=>String(node.type)==='Button' && text(node).includes(part))[0];
}
function has(root:ReactTestInstance,part:string) {
  return root.findAll(node=>String(node.type)==='Text' && text(node).includes(part)).length>0;
}

test('viewing a brief does not select a quiz; failed save keeps selection for retry',async()=>{
  let attempts=0;
  jest.mocked(studyRequest).mockImplementation(async(path:string)=>{
    if(path==='readings')return {readings:[reading]};
    if(path==='readings/select') {
      attempts++;
      if(attempts===1)throw new Error('offline');
      return {added:['no-reading-target-fixture'],selected:['no-reading-target-fixture'],already_selected:0};
    }
    throw new Error('unexpected request');
  });
  let renderer:TestRenderer.ReactTestRenderer;
  await act(async()=>{renderer=TestRenderer.create(<StudyReadings onBack={jest.fn()} sourceIds={['original-fixture']} onShown={jest.fn()} />);});
  expect(studyRequest).toHaveBeenCalledTimes(1);
  expect(has(renderer!.root,'Short explanation')).toBe(true);
  await act(async()=>button(renderer!.root,'Velg spørsmål å øve på').props.onPress());
  expect(studyRequest).toHaveBeenCalledTimes(1);
  await act(async()=>button(renderer!.root,'Velg · What is it?').props.onPress());
  expect(button(renderer!.root,'✓ Valgt · What is it?')).toBeTruthy();
  await act(async()=>button(renderer!.root,'Legg til 1 spørsmål').props.onPress());
  expect(has(renderer!.root,'Valgene dine er bevart')).toBe(true);
  expect(button(renderer!.root,'✓ Valgt · What is it?')).toBeTruthy();
  await act(async()=>button(renderer!.root,'Prøv igjen').props.onPress());
  expect(attempts).toBe(2);
  expect(has(renderer!.root,'1 nytt spørsmål lagt til øvingen')).toBe(true);
});
