# Vibe Coding a Custom macOS Presentation App with Claude Code

I decided to build a custom presentation app for my talks. I'm a big fan of presentation tools that let me write slides in Markdown, but none of the existing options quite fit my workflow.

## The Setup

I used Claude Code running in my terminal. My initial prompt was something like:

> Build me a macOS presentation app. It should read a Markdown file where slides are separated by --- dividers. Each slide should render the Markdown to HTML and display it full screen.

The first version took about 20 minutes of back-and-forth. Claude Code created a SwiftUI app with a single window that could parse my Markdown and render it slide by slide.

## Adding Features Incrementally

What I love about this workflow is the incremental nature. Each feature took one or two prompts:

### Speaker Notes
I added speaker notes support by extending the Markdown format — anything after a `>>>` on a slide becomes a note visible only on the presenter display.

### Syntax Highlighting
Code blocks needed proper highlighting. Claude added highlight.js integration with a dark theme that matched my presentation style.

### Live Reload
Perhaps the most useful feature: the app watches the Markdown file and reloads whenever I save changes. This means I can edit in my favorite text editor and see results instantly.

## Lessons Learned

1. **Start simple** — The first version was deliberately minimal
2. **One feature at a time** — Each prompt added exactly one capability
3. **Trust the agent** — Claude Code made better SwiftUI decisions than I would have
4. **Version control everything** — I committed after each working feature

The total development time was about 3 hours across two sessions. The resulting app is exactly what I need — nothing more, nothing less.

## Technical Details

The app uses:
- SwiftUI for the UI layer
- swift-markdown for parsing
- WebKit for rendering slides (Markdown → HTML → WKWebView)
- FSEvents for file watching

The source code is available on my GitHub. It's about 400 lines of Swift.
