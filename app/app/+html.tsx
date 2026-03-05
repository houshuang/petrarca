import { ScrollViewStyleReset } from 'expo-router/html';
import type { PropsWithChildren } from 'react';

function GoogleFonts() {
  return (
    <>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link
        href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Crimson+Pro:ital,wght@0,400;0,500;1,400&family=DM+Sans:wght@400;500;600;700&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&display=swap"
        rel="stylesheet"
      />
    </>
  );
}

function PetrarcaStyles() {
  return (
    <style
      id="petrarca-web-styles"
      dangerouslySetInnerHTML={{
        __html: `
          body, html {
            background-color: #f7f4ec !important;
            margin: 0;
            padding: 0;
          }

          @media (min-width: 800px) {
            #root > div:first-child {
              max-width: 860px !important;
              margin-left: auto !important;
              margin-right: auto !important;
              border-left: 1px solid #e4dfd4 !important;
              border-right: 1px solid #e4dfd4 !important;
              box-shadow: -20px 0 40px rgba(42, 36, 32, 0.03), 20px 0 40px rgba(42, 36, 32, 0.03);
            }
          }

          ::-webkit-scrollbar { width: 6px; }
          ::-webkit-scrollbar-track { background: transparent; }
          ::-webkit-scrollbar-thumb {
            background: #d0ccc0;
            border-radius: 6px;
          }
          ::-webkit-scrollbar-thumb:hover { background: #b0a898; }

          ::selection { background: rgba(139, 37, 0, 0.15); color: #2a2420; }

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
            background-color: rgba(139, 37, 0, 0.03);
          }

          *:focus-visible {
            outline: 2px solid #8b2500;
            outline-offset: 2px;
          }

          a { color: #2a4a6a; text-decoration: none; }
          a:hover { color: #8b2500; }

          /* Ensure Pressable components respond to DOM clicks (fixes Playwright/automation) */
          [role="button"] {
            -webkit-tap-highlight-color: transparent;
          }

          @media print {
            [role="tabbar"], [role="tablist"] { display: none !important; }
            body, html { background: white !important; }
            * { color: #2a2420 !important; }
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
          document.addEventListener('click', function(e) {
            var target = e.target;
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
        <meta name="theme-color" content="#f7f4ec" />
        <meta name="description" content="Petrarca — intelligent read-later app for deep reading" />
        <title>Petrarca</title>
        <link
          rel="icon"
          type="image/svg+xml"
          href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23f7f4ec'/%3E%3Ctext x='16' y='25' font-family='Georgia,serif' font-weight='700' font-size='24' fill='%238b2500' text-anchor='middle'%3EP%3C/text%3E%3C/svg%3E"
        />
        <GoogleFonts />
        <ScrollViewStyleReset />
        <PetrarcaStyles />
        <WebClickFix />
      </head>
      <body>{children}</body>
    </html>
  );
}
