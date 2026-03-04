import { isSectionValid } from '../lib/markdown-utils';

describe('SectionCard filtering via isSectionValid', () => {
  test('accepts valid section heading', () => {
    expect(isSectionValid({
      heading: 'Introduction to Machine Learning',
      content: 'Machine learning is a subset of artificial intelligence that focuses on building systems.',
    })).toBe(true);
  });

  test('skips sections with "[" heading', () => {
    expect(isSectionValid({
      heading: '[',
      content: 'This content is valid but the heading is broken',
    })).toBe(false);
  });

  test('skips sections with empty content', () => {
    expect(isSectionValid({
      heading: 'Comments',
      content: '',
    })).toBe(false);
  });

  test('skips sections with very short content', () => {
    expect(isSectionValid({
      heading: 'Follow the author',
      content: 'XY',
    })).toBe(false);
  });

  test('accepts sections with 20+ char content', () => {
    expect(isSectionValid({
      heading: 'Conclusion',
      content: 'In conclusion, this is a valid section with enough text.',
    })).toBe(true);
  });
});
