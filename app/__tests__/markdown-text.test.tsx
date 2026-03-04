import {
  isSectionValid,
  parseInlineMarkdown,
  parseMarkdownBlock,
  splitMarkdownBlocks,
} from '../lib/markdown-utils';

describe('isSectionValid', () => {
  test('rejects section with "[" heading', () => {
    expect(isSectionValid({ heading: '[', content: 'Some valid content here that is long enough' })).toBe(false);
  });

  test('rejects section with "](#" heading', () => {
    expect(isSectionValid({ heading: '](#some-link)', content: 'Some valid content here that is long enough' })).toBe(false);
  });

  test('rejects section with empty heading', () => {
    expect(isSectionValid({ heading: '', content: 'Some valid content here that is long enough' })).toBe(false);
  });

  test('rejects section with content < 20 chars', () => {
    expect(isSectionValid({ heading: 'Valid Heading', content: 'Short' })).toBe(false);
  });

  test('accepts valid section', () => {
    expect(isSectionValid({
      heading: 'Introduction',
      content: 'This is a paragraph with enough content to be valid.',
    })).toBe(true);
  });
});

describe('parseInlineMarkdown', () => {
  test('renders links as structured segments', () => {
    const result = parseInlineMarkdown('Check out [this link](https://example.com) for more.');
    expect(result).toEqual([
      { type: 'text', text: 'Check out ' },
      { type: 'link', text: 'this link', url: 'https://example.com' },
      { type: 'text', text: ' for more.' },
    ]);
  });

  test('renders bold text', () => {
    const result = parseInlineMarkdown('This is **important** text.');
    expect(result).toEqual([
      { type: 'text', text: 'This is ' },
      { type: 'bold', text: 'important' },
      { type: 'text', text: ' text.' },
    ]);
  });

  test('renders italic text', () => {
    const result = parseInlineMarkdown('This is *emphasized* text.');
    expect(result).toEqual([
      { type: 'text', text: 'This is ' },
      { type: 'italic', text: 'emphasized' },
      { type: 'text', text: ' text.' },
    ]);
  });

  test('renders inline code', () => {
    const result = parseInlineMarkdown('Use the `console.log` function.');
    expect(result).toEqual([
      { type: 'text', text: 'Use the ' },
      { type: 'code', text: 'console.log' },
      { type: 'text', text: ' function.' },
    ]);
  });

  test('strips images to alt text', () => {
    const result = parseInlineMarkdown('See ![diagram](https://example.com/img.png) here.');
    expect(result).toEqual([
      { type: 'text', text: 'See ' },
      { type: 'text', text: 'diagram' },
      { type: 'text', text: ' here.' },
    ]);
  });

  test('handles multiple inline elements', () => {
    const result = parseInlineMarkdown('**bold** and [link](http://x.com) and `code`');
    expect(result).toHaveLength(5);
    expect(result[0]).toEqual({ type: 'bold', text: 'bold' });
    expect(result[2]).toEqual({ type: 'link', text: 'link', url: 'http://x.com' });
    expect(result[4]).toEqual({ type: 'code', text: 'code' });
  });

  test('returns plain text when no markdown', () => {
    const result = parseInlineMarkdown('Just plain text');
    expect(result).toEqual([{ type: 'text', text: 'Just plain text' }]);
  });
});

describe('parseMarkdownBlock', () => {
  test('parses h1 heading', () => {
    const result = parseMarkdownBlock('# Title');
    expect(result).toEqual({ type: 'heading', content: 'Title', level: 1 });
  });

  test('parses h2 heading', () => {
    const result = parseMarkdownBlock('## Subtitle');
    expect(result).toEqual({ type: 'heading', content: 'Subtitle', level: 2 });
  });

  test('parses deep headings (h4, h5, h6)', () => {
    expect(parseMarkdownBlock('#### Deep')).toEqual({ type: 'heading', content: 'Deep', level: 4 });
    expect(parseMarkdownBlock('##### Deeper')).toEqual({ type: 'heading', content: 'Deeper', level: 5 });
    expect(parseMarkdownBlock('###### Deepest')).toEqual({ type: 'heading', content: 'Deepest', level: 6 });
  });

  test('parses horizontal rules', () => {
    expect(parseMarkdownBlock('---')).toEqual({ type: 'hr', content: '' });
    expect(parseMarkdownBlock('***')).toEqual({ type: 'hr', content: '' });
    expect(parseMarkdownBlock('___')).toEqual({ type: 'hr', content: '' });
    expect(parseMarkdownBlock('----------')).toEqual({ type: 'hr', content: '' });
  });

  test('parses unordered lists', () => {
    const result = parseMarkdownBlock('- First\n- Second\n- Third');
    expect(result.type).toBe('ul');
    expect(result.items).toEqual(['First', 'Second', 'Third']);
  });

  test('parses ordered lists', () => {
    const result = parseMarkdownBlock('1. First\n2. Second\n3. Third');
    expect(result.type).toBe('ol');
    expect(result.items).toEqual(['First', 'Second', 'Third']);
  });

  test('parses blockquotes', () => {
    const result = parseMarkdownBlock('> This is a quote\n> continued here');
    expect(result.type).toBe('blockquote');
    expect(result.content).toBe('This is a quote\ncontinued here');
  });

  test('parses code blocks', () => {
    const result = parseMarkdownBlock('```js\nconst x = 1;\n```');
    expect(result.type).toBe('code');
    expect(result.content).toBe('const x = 1;');
  });

  test('parses regular paragraphs', () => {
    const result = parseMarkdownBlock('Just a regular paragraph of text.');
    expect(result).toEqual({ type: 'paragraph', content: 'Just a regular paragraph of text.' });
  });

  test('parses standard markdown tables', () => {
    const result = parseMarkdownBlock('| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |');
    expect(result.type).toBe('table');
    expect(result.headers).toEqual(['Name', 'Age']);
    expect(result.rows).toEqual([['Alice', '30'], ['Bob', '25']]);
  });

  test('parses Wikipedia infobox-style pipe tables', () => {
    const result = parseMarkdownBlock('Sicilia | |\n|---|---|\n| Regione Siciliana | |\n| Anthem:');
    expect(result.type).toBe('table');
    expect(result.headers).toBeDefined();
  });

  test('skips empty pipe-only rows in tables', () => {
    const input = ['| Name | Value |', '|------|-------|', '|  |  |', '| Capital | Palermo |'].join('\n');
    const result = parseMarkdownBlock(input);
    expect(result.type).toBe('table');
    const hasPalermo = (result.rows || []).some(r => r.includes('Palermo'));
    expect(hasPalermo).toBe(true);
  });
});

describe('splitMarkdownBlocks', () => {
  test('splits simple paragraphs on blank lines', () => {
    const blocks = splitMarkdownBlocks('First paragraph.\n\nSecond paragraph.');
    expect(blocks).toEqual(['First paragraph.', 'Second paragraph.']);
  });

  test('keeps code blocks with blank lines intact', () => {
    const md = 'Before.\n\n```js\nline1\n\nline2\n```\n\nAfter.';
    const blocks = splitMarkdownBlocks(md);
    expect(blocks).toEqual(['Before.', '```js\nline1\n\nline2\n```', 'After.']);
  });

  test('splits headings from following content', () => {
    const md = '# Title\n\nSome text here.';
    const blocks = splitMarkdownBlocks(md);
    expect(blocks).toEqual(['# Title', 'Some text here.']);
  });

  test('handles unclosed code fence gracefully', () => {
    const md = 'Before.\n\n```\ncode without closing';
    const blocks = splitMarkdownBlocks(md);
    expect(blocks).toHaveLength(2);
    expect(blocks[1]).toContain('```');
  });

  test('handles multiple blank lines', () => {
    const blocks = splitMarkdownBlocks('A\n\n\n\nB');
    expect(blocks).toEqual(['A', 'B']);
  });

  test('keeps table rows together across blank lines', () => {
    const md = 'Before.\n\n| A | B |\n|---|---|\n\n| 1 | 2 |\n\nAfter.';
    const blocks = splitMarkdownBlocks(md);
    expect(blocks[0]).toBe('Before.');
    // Table rows should be grouped together
    expect(blocks.some(b => b.includes('| A | B |') && b.includes('| 1 | 2 |'))).toBe(true);
    expect(blocks[blocks.length - 1]).toBe('After.');
  });
});
