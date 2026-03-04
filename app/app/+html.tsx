import { ScrollViewStyleReset } from 'expo-router/html';
import type { PropsWithChildren } from 'react';

function PetrarcaStyles() {
  return (
    <style
      id="petrarca-web-styles"
      dangerouslySetInnerHTML={{
        __html: `
          body, html {
            background-color: #0f172a !important;
            margin: 0;
            padding: 0;
          }

          @media (min-width: 800px) {
            #root > div:first-child {
              max-width: 860px !important;
              margin-left: auto !important;
              margin-right: auto !important;
              border-left: 1px solid #1e293b !important;
              border-right: 1px solid #1e293b !important;
            }
          }

          ::-webkit-scrollbar { width: 8px; }
          ::-webkit-scrollbar-track { background: transparent; }
          ::-webkit-scrollbar-thumb {
            background: #334155;
            border-radius: 8px;
            border: 2px solid #0f172a;
          }
          ::-webkit-scrollbar-thumb:hover { background: #475569; }

          ::selection { background: rgba(37, 99, 235, 0.25); color: #f8fafc; }

          /* Enable text selection (RN Web defaults to user-select: none) */
          [data-testid="reader-content"] * {
            -webkit-user-select: text !important;
            user-select: text !important;
          }
          div[class*="css-"] {
            -webkit-user-select: auto;
            user-select: auto;
          }
          [role="button"], [role="tab"] {
            -webkit-user-select: none !important;
            user-select: none !important;
          }

          [role="button"] {
            cursor: pointer;
            transition: background-color 0.15s ease, transform 0.15s ease, opacity 0.15s ease;
          }
          [role="tab"] {
            transition: background-color 0.15s ease;
          }
          [role="tab"]:hover {
            background-color: rgba(37, 99, 235, 0.08);
          }

          *:focus-visible {
            outline: 2px solid #2563eb;
            outline-offset: 2px;
          }

          a:hover { color: #93c5fd; }

          /* Ensure Pressable components respond to DOM clicks (fixes Playwright/automation) */
          [role="button"] {
            -webkit-tap-highlight-color: transparent;
          }
        `,
      }}
    />
  );
}

function WebClickFix() {
  return (
    <script
      dangerouslySetInnerHTML={{
        __html: `
          // React Native Web Pressable uses a custom responder system that doesn't
          // always fire onPress from synthetic DOM clicks. This bridges the gap by
          // dispatching pointer events that RN Web's responder system recognizes.
          document.addEventListener('click', function(e) {
            var target = e.target;
            // Only intervene for programmatic clicks (no isTrusted) on role="button" elements
            if (e.isTrusted) return;
            var btn = target.closest ? target.closest('[role="button"]') : null;
            if (!btn) return;
            btn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, cancelable: true, pointerId: 1}));
            setTimeout(function() {
              btn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, cancelable: true, pointerId: 1}));
            }, 50);
          }, true);
        `,
      }}
    />
  );
}

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no"
        />
        <title>Petrarca</title>
        <ScrollViewStyleReset />
        <PetrarcaStyles />
        <WebClickFix />
      </head>
      <body>{children}</body>
    </html>
  );
}
