import React from 'react';
import TestRenderer, {act, ReactTestInstance} from 'react-test-renderer';

(globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT: boolean}).IS_REACT_ACT_ENVIRONMENT = true;
const consoleError = console.error;

beforeAll(() => {
  jest.spyOn(console, 'error').mockImplementation((message, ...args) => {
    if (String(message).includes('react-test-renderer is deprecated')) return;
    consoleError(message, ...args);
  });
});

afterAll(() => jest.mocked(console.error).mockRestore());

jest.mock('react-native', () => ({
  Text: 'Text',
  View: 'View',
  Pressable: 'Pressable',
  StyleSheet: {create: (value: unknown) => value, hairlineWidth: 1},
  Platform: {OS: 'ios', select: (choices: {ios?: unknown; default?: unknown}) => choices.ios ?? choices.default},
}));

jest.mock('../components/AspectCard', () => () => null);
jest.mock('../components/SequenceCard', () => () => null);
jest.mock('../components/SynchronicCard', () => () => null);
jest.mock('../components/CausalChainCard', () => () => null);
jest.mock('../components/study/StudyRecorder', () => () => null);

import StudyCard from '../components/study/StudyCard';
import type {StudyItem} from '../lib/study-api';

const termItem: StudyItem = {
  id: 'no-p1-term-ard',
  kind: 'term',
  title: 'Ard',
  version: 'norway-intensive-v2',
  needs_introduction: false,
  intended_depth: 'recognition',
  sources: [],
  references: [],
  positions: [{
    position_id: 'ard-meaning',
    question_text: 'Hva er en ard?',
    answer_text: 'Et enkelt plogredskap som risser opp jorda uten å vende den.',
  }],
};

function renderTermCard(item=termItem) {
  const onEvent = jest.fn();
  const onComplete = jest.fn();
  let renderer: TestRenderer.ReactTestRenderer;
  act(() => {
    renderer = TestRenderer.create(
      <StudyCard
        item={item}
        run="fixture-run"
        onEvent={onEvent}
        onComplete={onComplete}
        onIntroduce={jest.fn()}
        onBusy={jest.fn()}
        audioSaved={false}
        recording={false}
      />,
    );
  });
  return {renderer: renderer!, onEvent, onComplete};
}

function textContent(node: ReactTestInstance): string {
  return node.children.map(child => typeof child === 'string' ? child : textContent(child)).join('');
}

function button(root: ReactTestInstance, label: string): ReactTestInstance {
  return root.findAll(node => node.props.accessibilityRole === 'button' && textContent(node) === label)[0];
}

function hasText(root: ReactTestInstance, value: string): boolean {
  return root.findAll(node => textContent(node) === value).length > 0;
}

test('term recognition gives immediate visible confirmation and logs only once per choice', () => {
  const {renderer, onEvent} = renderTermCard();

  act(() => button(renderer.root, 'Kjenner igjen ordet').props.onPress());

  expect(hasText(renderer.root, '✓ Kjenner igjen ordet')).toBe(true);
  expect(hasText(renderer.root, 'Registrert. Vis betydningen når du er klar.')).toBe(true);
  expect(onEvent).toHaveBeenCalledWith('feedback', {
    dimension: 'term_recognition',
    value: 'familiar',
  });

  act(() => button(renderer.root, '✓ Kjenner igjen ordet').props.onPress());
  expect(onEvent).toHaveBeenCalledTimes(1);
});

test('the answer is hidden until the primary reveal action and ends in a clear judgment', () => {
  const {renderer, onComplete} = renderTermCard();

  expect(hasText(renderer.root, 'Det viktigste')).toBe(false);
  act(() => button(renderer.root, 'Vis omtrentlig betydning').props.onPress());

  expect(hasText(renderer.root, 'Det viktigste')).toBe(true);
  expect(hasText(renderer.root, 'Et enkelt plogredskap som risser opp jorda uten å vende den.')).toBe(true);
  act(() => button(renderer.root, 'Jeg hadde hovedideen').props.onPress());
  expect(onComplete).toHaveBeenCalledWith([
    expect.objectContaining({position_id: 'ard-meaning', score: 'knew'}),
  ]);
});


test('first introduction withholds meaning until familiarity is captured',()=>{
  const {renderer,onEvent}=renderTermCard({...termItem,needs_introduction:true,introduction:'Forklaringen som skal skjules.'});
  expect(hasText(renderer.root,'Forklaringen som skal skjules.')).toBe(false);
  expect(hasText(renderer.root,'Jeg har lest · fortsett')).toBe(false);
  act(()=>button(renderer.root,'Ukjent ord').props.onPress());
  expect(hasText(renderer.root,'Forklaringen som skal skjules.')).toBe(true);
  expect(onEvent).toHaveBeenCalledWith('feedback',{dimension:'term_recognition',value:'unfamiliar',phase:'before_introduction'});
});
