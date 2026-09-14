import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';
(globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT = true;
jest.mock('react-native',()=>({Text:'Text',View:'View',Pressable:'Pressable',ScrollView:'ScrollView',ActivityIndicator:'Spinner',
  StyleSheet:{create:(v:unknown)=>v,hairlineWidth:1},Platform:{OS:'ios',select:(v:{default:unknown})=>v.default},
  AppState:{addEventListener:()=>({remove:jest.fn()})},Linking:{openURL:jest.fn()}}));
jest.mock('expo-router',()=>({useFocusEffect:(callback:()=>void)=>{jest.requireActual('react').useEffect(callback,[callback]);}}));
jest.mock('../lib/feedback-context',()=>({setFeedbackContext:jest.fn()}));
jest.mock('../lib/study-api',()=>({loadStudyRun:jest.fn(),pendingAudio:jest.fn().mockResolvedValue([]),studyEvent:jest.fn().mockResolvedValue({saved:true}),uploadAudio:jest.fn()}));
jest.mock('../components/study/StudyRecorder',()=>()=>null);
jest.mock('../components/AspectCard',()=>()=>null);
jest.mock('../components/SequenceCard',()=>()=>null);
jest.mock('../components/SynchronicCard',()=>()=>null);
jest.mock('../components/CausalChainCard',()=>()=>null);
import StudyReview from '../components/study/StudyReview';
import {loadStudyRun,studyEvent,StudyRun} from '../lib/study-api';
const fixture:StudyRun={run_id:'fixture_run_12345',practice:'scheduled',topic:'all',completed_ids:[],audio_item_ids:[],
  experiment:{id:'fixture',design_version:'norway-intensive-v2'},items:[{id:'fixture_term',kind:'term',title:'Fixture term',
  version:'fixture',needs_introduction:true,introduction:'Hidden explanation',intended_depth:'recognition',sources:[],references:[],
  positions:[{position_id:'fixture_p0',question_text:'Fixture question?',answer_text:'Fixture answer'}]}]};
function text(node:TestRenderer.ReactTestInstance):string{return node.children.map(c=>typeof c==='string'?c:text(c)).join('');}
function press(renderer:TestRenderer.ReactTestRenderer,label:string){
  const button=renderer.root.findAll(n=>n.props.accessibilityRole==='button' && text(n)===label)[0];
  if(!button)throw new Error('Button missing: '+label);
  button.props.onPress();
}
function count(event:string){return jest.mocked(studyEvent).mock.calls.filter(c=>c[2]===event).length;}
let renderer:TestRenderer.ReactTestRenderer;
beforeEach(()=>{jest.clearAllMocks();jest.mocked(loadStudyRun).mockResolvedValue(fixture);});
afterEach(()=>{if(renderer)act(()=>renderer.unmount());});
test('practice starts directly; hidden definitions and options are not exposure',async()=>{
  await act(async()=>{renderer=TestRenderer.create(<StudyReview mode="review" onOpenAids={jest.fn()}/>);});
  expect(count('shown')).toBe(1);expect(count('introduction_shown')).toBe(0);
  expect(text(renderer.root)).not.toContain('Bilder og tidslinje');
  expect(text(renderer.root)).not.toContain('Hvordan øver du nå?');
  expect(count('shown')).toBe(1);expect(count('introduction_shown')).toBe(0);
  await act(async()=>press(renderer,'Ukjent ord'));
  expect(count('introduction_shown')).toBe(1);
  await act(async()=>press(renderer,'Valg'));
  expect(text(renderer.root)).toContain('Bilder og tidslinje');
  expect(count('shown')).toBe(1);expect(count('introduction_shown')).toBe(1);
  await act(async()=>press(renderer,'Tilbake'));
  expect(text(renderer.root)).toContain('Hidden explanation');
  expect(count('shown')).toBe(2);expect(count('introduction_shown')).toBe(2);
});
test('consecutive batches follow the participant closed-book policy without a prompt',async()=>{
  await act(async()=>{renderer=TestRenderer.create(<StudyReview mode="review"/>);});
  await act(async()=>press(renderer,'Ukjent ord'));
  await act(async()=>press(renderer,'Jeg har lest · fortsett'));
  expect(jest.mocked(studyEvent).mock.calls.find(c=>c[2]==='introduced')?.[3]).toMatchObject({book_state:'closed',book_state_basis:'participant_policy_2026-09-14'});
  jest.mocked(loadStudyRun).mockResolvedValue({...fixture,run_id:'next_fixture_run'});
  await act(async()=>press(renderer,'Neste runde'));
  expect(text(renderer.root)).not.toContain('Hvordan øver du nå?');
  expect(text(renderer.root)).toContain('Fixture term');
});

test('a completed memory answer carries declared context and its own position grade',async()=>{
  jest.mocked(loadStudyRun).mockResolvedValue({...fixture,items:[{...fixture.items[0],needs_introduction:false}]});
  await act(async()=>{renderer=TestRenderer.create(<StudyReview mode="review"/>);});
  await act(async()=>press(renderer,'Vis omtrentlig betydning'));
  await act(async()=>press(renderer,'Jeg hadde hovedideen'));
  const complete=jest.mocked(studyEvent).mock.calls.find(c=>c[2]==='complete');
  expect(complete?.[3]).toMatchObject({book_state:'closed',book_state_basis:'participant_policy_2026-09-14'});
  expect(complete?.[4]).toEqual([expect.objectContaining({position_id:'fixture_p0',score:'knew'})]);
});
