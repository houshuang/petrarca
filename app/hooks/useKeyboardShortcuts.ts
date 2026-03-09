import { useEffect } from 'react';
import { Platform } from 'react-native';
import { logEvent } from '../data/logger';

export interface Shortcut {
  handler: () => void;
  label: string;
}

export type ShortcutMap = Record<string, Shortcut>;

export function useKeyboardShortcuts(shortcuts: ShortcutMap, enabled = true) {
  useEffect(() => {
    if (Platform.OS !== 'web' || !enabled) return;

    const handler = (e: KeyboardEvent) => {
      // Skip when typing in input fields
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      const editable = (document.activeElement as HTMLElement)?.isContentEditable;
      if (tag === 'input' || tag === 'textarea' || editable) {
        if (e.key === 'Escape') (document.activeElement as HTMLElement)?.blur();
        return;
      }

      // Skip modified keys (Ctrl/Cmd/Alt) — we only bind plain keys
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const shortcut = shortcuts[e.key];
      if (shortcut) {
        e.preventDefault();
        shortcut.handler();
        logEvent('keyboard_shortcut', { key: e.key, label: shortcut.label });
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [shortcuts, enabled]);
}
