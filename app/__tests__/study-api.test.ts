const mockStorage = new Map<string,string>();
jest.mock('@react-native-async-storage/async-storage', () => ({__esModule:true,default:{
  getItem: jest.fn(async (key:string) => mockStorage.get(key) ?? null),
  setItem: jest.fn(async (key:string,value:string) => {mockStorage.set(key,value);}),
}}));
jest.mock('react-native', () => ({Platform:{OS:'ios'}}));
jest.mock('expo-constants', () => ({__esModule:true,default:{expoConfig:{version:'test-version'}}}));
jest.mock('expo-updates', () => ({updateId:'test-update',runtimeVersion:'test-runtime'}));
jest.mock('expo-file-system/legacy', () => ({
  documentDirectory:'file:///fixture/',makeDirectoryAsync:jest.fn(),copyAsync:jest.fn(),deleteAsync:jest.fn(async () => undefined),
  uploadAsync:jest.fn(async () => ({status:200})),FileSystemUploadType:{BINARY_CONTENT:0},
}));
jest.mock('../data/logger', () => ({logEvent:jest.fn()}));
jest.mock('../lib/server-urls', () => ({getResearchServerUrl:()=>'http://fixture.invalid'}));
import {flushStudyEvents, pendingAudio, preserveAudio, studyEvent, uploadAudio} from '../lib/study-api';
import * as FS from 'expo-file-system/legacy';
const fetchMock=jest.fn();
global.fetch=fetchMock;
beforeEach(() => {mockStorage.clear();jest.clearAllMocks();fetchMock.mockResolvedValue({ok:true,json:async()=>({saved:true})});});

test('network failure retains event payload and retry sends exact version and occurrence time',async () => {
  fetchMock.mockRejectedValueOnce(new Error('offline'));
  await expect(studyEvent('fixture_run_12345','fixture_card','shown',{format:'term'})).rejects.toThrow('offline');
  const first=JSON.parse(fetchMock.mock.calls[0][1].body);
  expect(first.client_context.update_id).toBe('test-update');
  expect(JSON.parse(mockStorage.get('@petrarca/study/events-v1')!)).toHaveLength(1);
  await flushStudyEvents();
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual(first);
  expect(JSON.parse(mockStorage.get('@petrarca/study/events-v1')!)).toHaveLength(0);
});
test('rapid independent events are serialized without losing any',async () => {
  await Promise.all(['shown','position_revealed','position_graded'].map(event => studyEvent('fixture_run_12345','fixture_card',event)));
  expect(fetchMock.mock.calls.map(c=>JSON.parse(c[1].body).event)).toEqual(['shown','position_revealed','position_graded']);
});
test('audio survives failed upload and is removed locally only after server and event acknowledgements',async () => {
  const saved=await preserveAudio('fixture_run_12345','fixture_card','file:///recording.m4a','wondering');
  expect((await pendingAudio())[0].uri).toMatch(/study-audio/);
  jest.mocked(FS.uploadAsync).mockResolvedValueOnce({status:503,headers:{},body:'offline',mimeType:null});
  await expect(uploadAudio(saved)).rejects.toThrow();
  expect(await pendingAudio()).toHaveLength(1);expect(FS.deleteAsync).not.toHaveBeenCalled();
  await uploadAudio(saved);
  expect(await pendingAudio()).toHaveLength(0);expect(FS.deleteAsync).toHaveBeenCalledTimes(1);
});
test('failed durable copy leaves the original recording indexed',async () => {
  jest.mocked(FS.copyAsync).mockRejectedValueOnce(new Error('disk full'));
  await preserveAudio('fixture_run_12345','fixture_card','file:///recording.m4a','reflection');
  expect((await pendingAudio())[0].uri).toBe('file:///recording.m4a');
});
test('new events reach durable storage even while an earlier network request is stalled',async () => {
  let release: (value: unknown) => void = () => undefined;
  fetchMock.mockImplementationOnce(() => new Promise(resolve => {release=resolve;}));
  const first=studyEvent('fixture_run_12345','fixture_card','shown');
  await new Promise(resolve => setImmediate(resolve));
  const second=studyEvent('fixture_run_12345','fixture_card','position_revealed');
  await new Promise(resolve => setImmediate(resolve));
  expect(JSON.parse(storageValue())).toHaveLength(2);
  release({ok:true,json:async()=>({saved:true})});await Promise.all([first,second]);
  expect(JSON.parse(storageValue())).toHaveLength(0);
});
function storageValue(){return mockStorage.get('@petrarca/study/events-v1') || '[]';}
