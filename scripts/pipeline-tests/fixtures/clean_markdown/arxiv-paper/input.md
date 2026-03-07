# Computer Science > Software Engineering

[Submitted on 24 Feb 2026]

# Title:Codified Context: Infrastructure for AI Agents in a Complex Codebase

[View PDF](/pdf/2602.20478)

[HTML (experimental)](/html/2602.20478v1)

## Abstract

We describe our experience integrating AI coding agents into a large-scale commercial codebase. As AI-powered development tools increasingly support agentic workflows — where models independently navigate code, make decisions, and implement changes — the challenge shifts from model capability to providing the right context.

We introduce the concept of "codified context": structured, machine-readable documentation embedded in the repository to guide agents through complex projects. Our implementation centers on AGENTS.md files — hierarchical Markdown documents that provide project-specific rules, common pitfalls, and workflow patterns.

## Introduction

Modern AI coding assistants have evolved from simple autocomplete tools to autonomous agents capable of navigating repositories, understanding codebases, and implementing complex changes. However, these agents face a fundamental challenge: understanding the implicit knowledge that human developers accumulate over time.

This paper presents our approach to solving this challenge through codified context — structured documentation that bridges the gap between what an AI agent can observe and what it needs to know.

## Methodology

We developed a three-tier architecture for codified context:

1. **Repository-level context** — AGENTS.md at root with project-wide conventions
2. **Directory-level context** — AGENTS.md files in key directories with local patterns
3. **File-level context** — Inline comments targeting agent behavior

### Three-Tier Memory Architecture

The AGENTS.md format supports hierarchical context loading. When an agent navigates to a file in `src/api/handlers/`, it loads context from:
- Root AGENTS.md (coding standards, build instructions)
- src/AGENTS.md (source directory conventions)
- src/api/AGENTS.md (API-specific patterns)
- src/api/handlers/AGENTS.md (handler-specific rules)

## Results

After deploying AGENTS.md files across our monorepo:
- Agent task completion rate improved from 67% to 84%
- Code review rejection rate for agent-written code decreased by 41%
- Average agent "wander time" (time spent reading irrelevant files) decreased by 58%

## Related Work

Previous approaches to guiding AI agents include prompt engineering, fine-tuning, and retrieval-augmented generation (RAG). Our approach complements these by providing persistent, version-controlled context that evolves with the codebase.

## References

[1] Brown et al., "Language Models are Few-Shot Learners," NeurIPS 2020
[2] Chen et al., "Evaluating Large Language Models Trained on Code," 2021
[3] Vaswani et al., "Attention Is All You Need," NeurIPS 2017
[4] Anthropic, "Claude 3 Technical Report," 2024
[5] Wei et al., "Chain of Thought Prompting," NeurIPS 2022

Subjects: Software Engineering (cs.SE); Artificial Intelligence (cs.AI)
Cite as: arXiv:2602.20478 [cs.SE]

Skip to main content

Home | About | Contact | Privacy | Terms

Follow us on Twitter | Share on LinkedIn
