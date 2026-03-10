import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { logEvent } from '../data/logger';

export interface Shortcut {
  handler: () => void;
  label: string;
}

export type ShortcutMap = Record<string, Shortcut>;

const SEQUENCE_TIMEOUT_MS = 500;

export function useKeyboardShortcuts(shortcuts: ShortcutMap, enabled = true) {
  const pendingKey = useRef<string | null>(null);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

      const key = e.key;

      // Check if this completes a two-key sequence (e.g. "gi")
      if (pendingKey.current) {
        const seq = pendingKey.current + key;
        pendingKey.current = null;
        if (pendingTimer.current) { clearTimeout(pendingTimer.current); pendingTimer.current = null; }

        const seqShortcut = shortcuts[seq];
        if (seqShortcut) {
          e.preventDefault();
          seqShortcut.handler();
          logEvent('keyboard_shortcut', { key: seq, label: seqShortcut.label });
          return;
        }
        // Sequence didn't match — fall through to check single key
      }

      // Check if this key is a prefix for any multi-key shortcut
      const isPrefix = Object.keys(shortcuts).some(k => k.length > 1 && k[0] === key);

      if (isPrefix) {
        // Also check if it's a standalone shortcut
        const standalone = shortcuts[key];
        if (standalone) {
          // It's both a prefix and standalone — wait briefly for second key
          pendingKey.current = key;
          pendingTimer.current = setTimeout(() => {
            pendingKey.current = null;
            pendingTimer.current = null;
            e.preventDefault();
            standalone.handler();
            logEvent('keyboard_shortcut', { key, label: standalone.label });
          }, SEQUENCE_TIMEOUT_MS);
          e.preventDefault();
          return;
        }
        // Only a prefix, wait for second key
        pendingKey.current = key;
        pendingTimer.current = setTimeout(() => {
          pendingKey.current = null;
          pendingTimer.current = null;
        }, SEQUENCE_TIMEOUT_MS);
        e.preventDefault();
        return;
      }

      // Single key shortcut
      const shortcut = shortcuts[key];
      if (shortcut) {
        e.preventDefault();
        shortcut.handler();
        logEvent('keyboard_shortcut', { key, label: shortcut.label });
      }
    };

    document.addEventListener('keydown', handler);
    return () => {
      document.removeEventListener('keydown', handler);
      if (pendingTimer.current) clearTimeout(pendingTimer.current);
    };
  }, [shortcuts, enabled]);
}
