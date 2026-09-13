import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Text, View } from 'react-native';
import { Audio } from 'expo-av';
import { useFocusEffect } from 'expo-router';
import { CaptureKind, PendingAudio, preserveAudio, requestId, studyEvent, uploadAudio } from '../../lib/study-api';
import { StudyButton, styles } from './StudyControls';

export default function StudyRecorder({run, item, kind, onSaved, onBusy, disabled = false, maxSeconds = 240, onRetained}: {
  run: string; item: string; kind: CaptureKind; onSaved: () => void; onBusy: (busy: boolean) => void; disabled?: boolean; maxSeconds?: number; onRetained?: () => void;
}) {
  const attempt = useRef('');
  const recording = useRef<Audio.Recording | null>(null);
  const sound = useRef<Audio.Sound | null>(null);
  const [active, setActive] = useState(false);
  const [pending, setPending] = useState<PendingAudio | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [seconds, setSeconds] = useState(0);
  const mounted = useRef(true);
  const log = (event: string, detail = {}) => studyEvent(run,item,event,{response_kind:kind,attempt_id:attempt.current,...detail}).catch(() => undefined);
  async function retainCurrent() {
    const current = recording.current;
    if (!current) return null;
    recording.current = null;
    await current.stopAndUnloadAsync();
    const uri = current.getURI();
    if (!uri) throw new Error('Opptaket mangler en lydfil.');
    // Keep the original URI in storage as a fallback if copying fails.
    const saved = await preserveAudio(run,item,uri,kind,attempt.current);
    void log('recording_stopped', {duration_ms: (await current.getStatusAsync()).durationMillis});
    await Audio.setAudioModeAsync({allowsRecordingIOS: false});
    return saved;
  }
  useFocusEffect(useCallback(() => () => {
    if (recording.current) void stop();
  }, []));
  useEffect(() => () => {
    mounted.current = false;
    void sound.current?.unloadAsync();
    if (recording.current) void retainCurrent().catch(() => undefined);
  }, []);
  useEffect(() => {
    const sub = AppState.addEventListener('change', state => { if (state !== 'active' && recording.current) void stop(); });
    return () => sub.remove();
  }, []);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setSeconds(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, [active]);
  useEffect(() => { if (active && seconds >= maxSeconds) void stop(); }, [seconds, active, maxSeconds]);
  async function start() {
    setError(''); setBusy(true); onBusy(true);
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) throw new Error('Tillat mikrofonen for å ta opp svaret.');
      await Audio.setAudioModeAsync({allowsRecordingIOS: true, playsInSilentModeIOS: true});
      const result = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      attempt.current = requestId();
      recording.current = result.recording; setSeconds(0); setActive(true); void log('recording_started');
    } catch (e) { setError(String(e)); onBusy(false); void log('recording_failed'); }
    finally { setBusy(false); }
  }
  async function stop() {
    if (!recording.current) return;
    setBusy(true);
    try { const saved = await retainCurrent(); if (mounted.current) {setPending(saved); if (saved) onRetained?.();} }
    catch (e) { setError(String(e)); }
    finally { setActive(false); setBusy(false); onBusy(false); }
  }
  async function upload() {
    if (!pending) return;
    setBusy(true); onBusy(true); setError('');
    try { await uploadAudio(pending); setPending(null); onSaved(); }
    catch (e) { setError(String(e)); void log('audio_upload_failed'); }
    finally { setBusy(false); onBusy(false); }
  }
  async function play() {
    if (!pending) return;
    try {
      await sound.current?.unloadAsync();
      const result = await Audio.Sound.createAsync({uri: pending.uri}, {shouldPlay: true});
      sound.current = result.sound; void log('audio_played');
    } catch { setError('Kunne ikke spille av. Opptaket er fortsatt lagret.'); }
  }
  return <View style={{gap: 10}}>
    {active ? <StudyButton variant="primary" disabled={busy} onPress={() => void stop()}>Stopp opptak · {seconds} s</StudyButton>
      : pending ? <><StudyButton disabled={busy || disabled} onPress={() => void play()}>Lytt til opptaket</StudyButton>
        <StudyButton variant="primary" disabled={busy || disabled} onPress={() => void upload()}>Lagre opptaket</StudyButton></>
      : <StudyButton variant="primary" disabled={busy || disabled} onPress={() => void start()}>Start opptak</StudyButton>}
    {!!error && <Text style={styles.error}>{error}</Text>}
  </View>;
}
