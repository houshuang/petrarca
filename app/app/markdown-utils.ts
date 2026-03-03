/**
 * Pure utility functions for markdown processing.
 * Extracted from reader.tsx for testability.
 */

/** Check if a section has valid heading and sufficient content */
export function isSectionValid(section: { heading: string; content: string }): boolean {
  const h = (section.heading || '').trim();
  if (h === '[' || h.startsWith('](#') || h === '') return false;
  if ((section.content || '').trim().length < 20) return false;
  return true;
}

/** Parse inline markdown and return structured segments */
export type InlineSegment =
  | { type: 'text'; text: string }
  | { type: 'link'; text: string; url: string }
  | { type: 'bold'; text: string }
  | { type: 'italic'; text: string }
  | { type: 'code'; text: string };

export function parseInlineMarkdown(text: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  // Order matters: links first, then images (stripped), bold (**), italic (*), code (`)
  // Image links ![]() are stripped to just their alt text
  const inlineRe = /!\[([^\]]*)\]\([^)]+\)|\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = inlineRe.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', text: text.slice(lastIndex, match.index) });
    }

    if (match[1] !== undefined) {
      // Image — render alt text as plain text
      if (match[1]) {
        segments.push({ type: 'text', text: match[1] });
      }
    } else if (match[2] !== undefined && match[3] !== undefined) {
      segments.push({ type: 'link', text: match[2], url: match[3] });
    } else if (match[4] !== undefined) {
      segments.push({ type: 'bold', text: match[4] });
    } else if (match[5] !== undefined) {
      segments.push({ type: 'italic', text: match[5] });
    } else if (match[6] !== undefined) {
      segments.push({ type: 'code', text: match[6] });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    segments.push({ type: 'text', text: text.slice(lastIndex) });
  }

  return segments.length > 0 ? segments : [{ type: 'text', text }];
}

/** Block types produced by splitMarkdownBlocks */
export type BlockType = 'heading' | 'hr' | 'ul' | 'ol' | 'code' | 'blockquote' | 'paragraph';

export interface ParsedBlock {
  type: BlockType;
  content: string;
  level?: number; // heading level
  items?: string[]; // list items
}

/**
 * Split raw markdown into blocks, correctly handling code fences
 * that may contain blank lines. Returns trimmed, non-empty blocks.
 */
export function splitMarkdownBlocks(markdown: string): string[] {
  const lines = markdown.split('\n');
  const blocks: string[] = [];
  let current: string[] = [];
  let inCodeFence = false;

  for (const line of lines) {
    if (!inCodeFence && line.trimStart().startsWith('```')) {
      // Start of code fence — flush any accumulated paragraph first
      if (current.length > 0) {
        blocks.push(current.join('\n'));
        current = [];
      }
      current.push(line);
      inCodeFence = true;
    } else if (inCodeFence) {
      current.push(line);
      if (line.trimStart().startsWith('```') && current.length > 1) {
        // End of code fence
        blocks.push(current.join('\n'));
        current = [];
        inCodeFence = false;
      }
    } else if (line.trim() === '') {
      // Blank line separates blocks
      if (current.length > 0) {
        blocks.push(current.join('\n'));
        current = [];
      }
    } else {
      current.push(line);
    }
  }

  // Flush remaining (including unclosed code fences)
  if (current.length > 0) {
    blocks.push(current.join('\n'));
  }

  return blocks.map(b => b.trim()).filter(Boolean);
}

/** Parse a single block of markdown text into a typed structure */
export function parseMarkdownBlock(trimmed: string): ParsedBlock {
  // Heading (h1-h6) — must be the only content on the line
  const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
  if (headingMatch) {
    return { type: 'heading', content: headingMatch[2], level: headingMatch[1].length };
  }

  // Horizontal rule
  if (/^(---+|\*\*\*+|___+)\s*$/.test(trimmed)) {
    return { type: 'hr', content: '' };
  }

  // Unordered list (- or *)
  if (/^[-*]\s/.test(trimmed)) {
    const items = trimmed
      .split('\n')
      .filter(l => /^\s*[-*]\s/.test(l))
      .map(l => l.replace(/^\s*[-*]\s+/, ''));
    return { type: 'ul', content: trimmed, items };
  }

  // Ordered list (1. 2. etc)
  if (/^\d+\.\s/.test(trimmed)) {
    const items = trimmed
      .split('\n')
      .filter(l => /^\s*\d+\.\s/.test(l))
      .map(l => l.replace(/^\s*\d+\.\s+/, ''));
    return { type: 'ol', content: trimmed, items };
  }

  // Code block
  if (trimmed.startsWith('```')) {
    const code = trimmed.replace(/^```\w*\n?/, '').replace(/\n?```$/, '');
    return { type: 'code', content: code };
  }

  // Blockquote
  if (trimmed.startsWith('>')) {
    const content = trimmed
      .split('\n')
      .map(l => l.replace(/^>\s?/, ''))
      .join('\n');
    return { type: 'blockquote', content };
  }

  // Regular paragraph
  return { type: 'paragraph', content: trimmed };
}

// Keep backward compat — old code used 'list' type
export type { BlockType as MarkdownBlockType };
