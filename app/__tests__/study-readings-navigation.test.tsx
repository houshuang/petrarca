import React from 'react';
import TestRenderer, {act, ReactTestInstance} from 'react-test-renderer';
import StudyGate from '../components/study/StudyGate';
import {studyRequest} from '../lib/study-api';

(globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

jest.mock('react-native',()=>({View:'View',Text:'Text',ActivityIndicator:'ActivityIndicator'}));
jest.mock('expo-router',()=>({useFocusEffect:(callback:()=>void)=>require('react').useEffect(callback,[callback])}));
jest.mock('../lib/study-api',()=>({studyRequest:jest.fn()}));
jest.mock('../lib/feedback-context',()=>({setFeedbackContext:jest.fn()}));
jest.mock('../data/logger',()=>({logEvent:jest.fn()}));
jest.mock('../design/tokens',()=>({colors:{parchment:'#f7f4ec'}}));
jest.mock('../components/study/StudyControls',()=>({
  styles:{body:{},caption:{}},
  StudyButton:({children,onPress}:{children:React.ReactNode;onPress:()=>void})=>
    require('react').createElement('Button',{onPress,label:children},children),
}));
jest.mock('../components/study/StudyReview',()=>{
  const React=require('react');
  return function Review({onOpenReadings,onOpenAids}:{onOpenReadings:(ids?:string[])=>void;onOpenAids:()=>void}) {
    const [revealed,setRevealed]=React.useState(false);
    return React.createElement('View',{},
      React.createElement('Button',{onPress:()=>setRevealed(true),label:'Reveal'},'Reveal'),
      React.createElement('Text',{},revealed?'Answer remains revealed':'Answer hidden'),
      React.createElement('Button',{onPress:()=>onOpenReadings(['original-source']),label:'Forklar kort'},'Forklar kort'),
      React.createElement('Button',{onPress:onOpenAids,label:'Bilder og tidslinje'},'Bilder og tidslinje'));
  };
});
jest.mock('../components/study/StudyReadings',()=>function Readings({onBack}:{onBack:()=>void}){
  return require('react').createElement('Button',{onPress:onBack,label:'Tilbake til øving'},'Tilbake til øving');
});
jest.mock('../components/study/StudyLearningAids',()=>function Aids({onBack,onOpenReadings}:{onBack:()=>void;onOpenReadings:()=>void}){
  return require('react').createElement('View',{},
    require('react').createElement('Button',{onPress:onOpenReadings,label:'Read from aids'},'Read from aids'),
    require('react').createElement('Button',{onPress:onBack,label:'Back from aids'},'Back from aids'));
});
jest.mock('../components/study/StudyAssessment',()=>()=>null);
jest.mock('../components/study/StudyStats',()=>()=>null);

function button(root:ReactTestInstance,label:string) {
  return root.findAll(node=>String(node.type)==='Button' && node.props.label===label)[0];
}
function shown(root:ReactTestInstance) {
  return root.findAll(node=>String(node.type)==='Text' && node.children.includes('Answer remains revealed')).length>0;
}

test('reading and learning aid overlays preserve the current review card state',async()=>{
  jest.mocked(studyRequest).mockResolvedValue({active:true});
  let renderer:TestRenderer.ReactTestRenderer;
  await act(async()=>{renderer=TestRenderer.create(<StudyGate mode="review"><></></StudyGate>);});
  act(()=>button(renderer!.root,'Reveal').props.onPress());
  expect(shown(renderer!.root)).toBe(true);
  act(()=>button(renderer!.root,'Forklar kort').props.onPress());
  act(()=>button(renderer!.root,'Tilbake til øving').props.onPress());
  expect(shown(renderer!.root)).toBe(true);
  act(()=>button(renderer!.root,'Bilder og tidslinje').props.onPress());
  act(()=>button(renderer!.root,'Read from aids').props.onPress());
  act(()=>button(renderer!.root,'Tilbake til øving').props.onPress());
  act(()=>button(renderer!.root,'Back from aids').props.onPress());
  expect(shown(renderer!.root)).toBe(true);
});
