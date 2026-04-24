# Periodic Fork Review

**Why it matters.** External forks of Petrarca run the code in environments I never touch: a fresh Mac, a different Python version, a self-hosted Docker setup, a laptop without Tailscale. Whatever hidden assumption my code makes about "runs on alif" surfaces there first. Fork authors also tend to write the small, defensive infrastructure fixes that I never prioritize because nothing has broken *for me* yet.

**But forks drift fast.** Petrarca ships 2–3 architectural pivots per week (Gemini → Claude, entity-first, STRUCTURAL_ONLY gating, etc.). A PR opened April 15 was already directionally stale by April 21. External contributors can't see the direction vectors — only the current state. The conflict is not textual, it's intent.

So: pull the infrastructure gifts, decline the feature/architecture contributions that fight the direction, and keep the door open for future contact.

## Cadence

Monthly triage is about right. More often is overhead for ~20 minutes of real signal; less often and forks drift past cleanly-cherry-pickable state.

## Procedure

From within the repo:

```sh
gh api repos/houshuang/petrarca/forks --jq '.[] | {owner: .owner.login, pushed_at: .pushed_at}'
```

For each fork with `pushed_at` newer than last review:

```sh
gh api "repos/houshuang/petrarca/compare/main...{OWNER}:petrarca:main" \
  --jq '{ahead_by, behind_by, total_commits, commits: [.commits[] | {sha: .sha[0:8], msg: .commit.message | split("\n")[0]}]}'
```

If `ahead_by > 0`, scan commit messages. For anything non-trivial (not a readme tweak, not a dependabot bump, not a merge), pull the file list:

```sh
gh api repos/{OWNER}/petrarca/commits/{SHA} --jq '.files[] | {filename, additions, deletions, status}'
```

Open the PR *on their fork* to read code only when the file list looks promising.

## Triage rules (developed from the April 2026 pass)

**Pull eagerly:**
- Defensive infrastructure fixes (stdlib deprecations, migration ordering, env-var overrides of hardcoded paths).
- Refactors that centralize scattered constants into one module (URLs, paths, keys).
- Tiny correctness fixes with zero architectural weight.

**Reject or carve out carefully:**
- Anything touching LLM provider choice — the project has a strong directional opinion. Read `memory/feedback_claude_only_never_gemini.md` before considering.
- Fallback paths to weaker models — the project has opinions about quality floors (Opus-only for curriculum, etc.).
- Re-enabling disabled subsystems (Feed tab, article ingestion, Readwise, etc. — see `CLAUDE.md` § Disabled Subsystems).

**Personal-fork identity must not merge:**
- `app.json` bundle ID, EAS project ID, owner.
- Their own API keys, `.env` files, deployment manifests.

**Worth a thank-you but not a merge:**
- Docker / Kubernetes deployment scaffolding for anyone who doesn't self-host.
- Local-dev bootstrap scripts if I never run locally.
- Personal marketing / one-pager / branding docs.

## Process hygiene

1. **Always cherry-pick onto fresh branches from current main** — never `git merge` a PR that is >14 days behind, even if GitHub says "no conflicts." The directional conflict will bite.
2. **Extract one concern per branch.** mmccray's April 2026 PR mixed URL refactor + `cgi` removal + DB migration + LLM backend rewrite + UX + identity changes. Four of those belong together; two were directionally wrong. Unbundling is the review.
3. **In the close comment, name what you took and why.** The contributor invested real time; attribute the pulls by PR number and explain each rejection. This is what keeps the invitation to future contribution credible.
4. **Credit them in commits.** `Co-Authored-By: <handle> <...>` in the cherry-pick commit. Let GitHub show their contribution graph the attribution.
5. **Invite continued contact.** Most external contributors only open one PR. Leaving the door open ("email me, draft PR, issue") is the lowest-cost way to convert a one-time contribution into a long-term perspective.

## Prior passes

- **2026-04-24** — First pass. Reviewed 5 forks (mmccray, Lorehouse, lukaskawerau, TJ-Frederick, noahsl-et). Closed PR #1 (superseded by Session 56) and PR #5 (mmccray's), cherry-picked to PR #7, #8, #9. Four other forks had nothing worth pulling (all personal deployment / LLM-backend rewrites / branding). Infrastructure wins: Python 3.13 `cgi` removal, `idx_shared_entities_qid` migration ordering, URL centralization. Documented by this file.
