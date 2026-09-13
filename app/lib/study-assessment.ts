import AsyncStorage from '@react-native-async-storage/async-storage';
import {clientContext, flushStudyEvents, requestId, studyRequest} from './study-api';

export type AssessmentContext = {
  volume: number; coverage: string; help_state: 'closed' | 'supported';
  occasion: 'current' | 'before_volume' | 'volume_end' | 'delayed' | 'project_end';
};
export type AssessmentRun = {
  run_id: string; assessment: AssessmentContext; completed_ids: string[]; audio_item_ids: string[];
  protocol: {version: string};
  items: {id: string; title: string; text: string; max_seconds: number; confidence: boolean}[];
};
const KEY = '@petrarca/study/assessment-v1';
export async function cachedAssessment(): Promise<AssessmentContext | null> {
  const saved = await AsyncStorage.getItem(KEY);
  return saved ? JSON.parse(saved).context as AssessmentContext : null;
}
export async function loadAssessment(context: AssessmentContext, fresh = false): Promise<AssessmentRun> {
  await flushStudyEvents();
  const stored = await AsyncStorage.getItem(KEY);
  const saved = stored ? JSON.parse(stored) as {id:string;context:AssessmentContext} : null;
  const entry = !fresh && saved && JSON.stringify(saved.context) === JSON.stringify(context)
    ? saved : {id:requestId(),context};
  await AsyncStorage.setItem(KEY,JSON.stringify(entry));
  return studyRequest('session',{request_id:entry.id,mode:'assessment',assessment:context,client_context:clientContext()});
}
