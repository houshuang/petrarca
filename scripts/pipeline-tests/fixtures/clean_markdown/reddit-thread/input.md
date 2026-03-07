Reddit - Pair programming with Claude Code changed how I think about software

r/programming

Posted by u/throwaway_dev_42 • 2 days ago

🏅 Gold 🥈 Silver ×3 💎 Platinum

# Pair programming with Claude Code changed how I think about software

I've been a senior engineer for 12 years. Last month I started using Claude Code seriously (not just for toy projects) and I need to talk about what happened.

**TLDR**: Claude Code is not a replacement for thinking. It's an amplifier for thinking. And it exposed how much of my "engineering" was actually just typing.

## The Setup

I was tasked with migrating our payment service from a monolith to microservices. Classic senior engineer project — involves understanding the whole system, making architectural decisions, handling edge cases, etc.

I decided to try doing it with Claude Code as my pair programmer.

## What Surprised Me

### 1. The 80/20 Split Was Real

About 80% of the actual code I was writing — the service scaffolding, the database migrations, the API endpoints, the tests — was "known patterns." I'd done it dozens of times. Claude Code handled this instantly.

The remaining 20% — the architectural decisions, the edge case handling around idempotency in payment processing, the retry logic for distributed transactions — that was where my 12 years of experience actually mattered.

### 2. It Found Bugs I Would Have Shipped

In the payment reconciliation service, Claude Code flagged a race condition in my original design. Two concurrent requests could both read the same balance, compute independently, and write conflicting results.

I would have caught this eventually — probably in production, probably at 3am, probably on a holiday weekend. Claude caught it during code review of its own output.

### 3. It Made Me Better at Communicating Intent

The better I got at describing what I wanted (and WHY), the better the output. This skill — precisely communicating intent and constraints — transfers directly to human collaboration.

### 4. My Estimation Changed

The migration I estimated at 6-8 weeks took 2 weeks. Not because the AI is magic, but because:
- Less time on boilerplate
- Fewer silly bugs
- Faster exploration of approaches
- More time spent on the hard problems

## The Uncomfortable Truth

If 80% of what a "senior engineer" does can be automated, what does that mean for the profession? I think it means:

1. **Architecture and design become more important** — the "thinking" part gets amplified
2. **Code review skills become critical** — you need to evaluate AI output effectively
3. **Communication skills matter more** — writing good prompts IS writing good specs
4. **Domain knowledge is the moat** — understanding payment processing edge cases can't be prompted

## What I Actually Do Now

My day looks completely different:
- Morning: review what Claude worked on overnight (background agents)
- Design sessions: I sketch architectures, Claude implements them
- Code review: I review AI output the same way I'd review a junior's code
- Edge cases: I write the tricky bits myself, or I pair with Claude in real-time

## Conclusion

I'm more productive than I've ever been, and I'm doing more interesting work than I've ever done. The boring parts are gone. What's left is the good stuff.

---

Edit: RIP my inbox. Some common responses:

Edit 2: To the people saying "wait until the bubble pops" — I've heard this about every major technology shift. Sometimes the skeptics are right. This time I don't think they are.

Edit 3: I'm not affiliated with Anthropic in any way. I use other tools too (Copilot, Cursor). Claude Code just happens to be what clicked for me.

---

⬆ 4,832  ⬇

💬 892 Comments     🔄 Share     ⭐ Save     🏆 Award     •••

Sort by: Best ▾

---

**u/senior_swe_mgr** · 1d · 🏅

This resonates hard. I lead a team of 8 engineers and I've noticed the same pattern. The engineers who are thriving with AI tools are the ones who were always strong at system design and communication. The ones struggling are the ones who relied on knowing syntax and patterns by heart.

⬆ 1,203  ⬇  💬 Reply    ⭐ Award    •••

> **u/throwaway_dev_42** OP · 1d
> Exactly. The skill that mattered was always "understanding the problem." We just confused "knowing how to type the solution" with "knowing the solution."
>
> ⬆ 567  ⬇  💬 Reply    ⭐ Award    •••

**u/contrarian_take** · 1d

Cool story. Now do it without internet access when Claude is down. These tools are a crutch and when they go away (or get too expensive) you'll have forgotten how to code.

⬆ -234  ⬇  💬 Reply    ⭐ Award    •••

> **u/throwaway_dev_42** OP · 23h
> Do you also refuse to use an IDE because you might forget how to code in Notepad?
>
> ⬆ 2,891  ⬇  💬 Reply    🏅 ×2    ⭐ Award    •••

**u/ml_researcher_phd** · 22h

Good post. One thing I'd add: the "AI makes you better at communicating intent" observation matches what we see in research. There's a paper from MIT showing that engineers who improve at prompt engineering also improve at writing technical specifications, design documents, and code reviews. The skills are deeply linked.

⬆ 445  ⬇  💬 Reply    ⭐ Award    •••

---

View remaining 887 comments →

---

Related Posts:
- Claude Code vs Cursor vs Copilot: Which is best in 2026? (r/programming, 2.1k upvotes)
- I replaced my entire QA team with AI and here's what happened (r/cscareerquestions, 891 upvotes)
- Ask HN: Has AI actually made you more productive? (r/programming, 5.4k upvotes)

---

Reddit, Inc. © 2026. All rights reserved.

[User Agreement](https://reddit.com/policies/user-agreement) | [Privacy Policy](https://reddit.com/policies/privacy-policy) | [Content Policy](https://reddit.com/policies/content-policy)

Get the Reddit app

[Download on the App Store](https://apps.apple.com) | [Get it on Google Play](https://play.google.com)

Reddit app • Reddit coins • Reddit premium • About • Careers • Press
