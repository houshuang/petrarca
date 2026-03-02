# User Requirements — Interview Round 3

## Interest Domains (broad)
- History, literature, classical philology
- Educational research
- Policy (green party — see ../mdg project)
- Technology (AI, Claude Code, etc.)
- Should NOT over-optimize for any one domain

## Otak Status Correction
- **The knowledge graph in otak is a "failed experiment"** — do not rely on it
- Being iterated on elsewhere
- BUT the **scripts are useful**: Twitter bookmark fetcher, Readwise fetcher, LLM providers
- Use otak as a code/pattern library, not as a running system

## First Experiment: Twitter Bookmarks → Claude Code Report
Concrete first step:
1. Update Twitter bookmarks (fetch recent ones)
2. Filter to last few weeks about Claude Code
3. Process: which are duplicative, which are high signal
4. Generate summaries / consolidated report with expandable subsections
5. This helps with the Friday presentation prep

## Voice Notes → Deep Research
- Main use case is "deeper research" not specific fact lookup
- Example: wrestling with a question while reading → agent goes and finds relevant perspectives
- Background agent on Hetzner VM

## Cost Preferences
- **Claude Code Max plan = free** — prefer this over API calls
- Has access to 3 providers but wants to minimize API spend
- Same pattern as ../alif: use `claude -p` wrapper for LLM work
- This means processing should use Claude Code subagents where possible

## Iteration Approach
- Small chunks, iterate fast
- Don't over-plan, prototype quickly
- User is comfortable with rough/ugly prototypes that demonstrate the concept
