# LLM Benchmark Comparison: March 2026

## Overview

This report compares the latest language models across standard benchmarks. Data collected March 1-3, 2026.

## Main Results

| Model | MMLU | HumanEval | MATH | ARC-C | HellaSwag | BBH | Avg |
|-------|------|-----------|------|-------|-----------|-----|-----|
| GPT-5 | 92.1 | 91.4 | 78.3 | 96.2 | 95.8 | 89.7 | 90.6 |
| Claude Opus 4 | 91.8 | 93.2 | 82.1 | 95.7 | 94.9 | 91.3 | 91.5 |
| Gemini Ultra 2 | 90.4 | 88.7 | 76.9 | 94.8 | 95.1 | 87.4 | 88.9 |
| DeepSeek R2 | 89.7 | 87.3 | 85.2 | 93.1 | 93.4 | 88.9 | 89.6 |
| LLaMA 4 405B | 88.2 | 85.1 | 71.4 | 92.7 | 94.2 | 84.6 | 86.0 |
| Qwen 3.5 72B | 87.9 | 84.8 | 73.2 | 91.3 | 93.1 | 83.8 | 85.7 |
| Mistral Large 3 | 86.4 | 82.9 | 68.7 | 90.8 | 92.7 | 81.2 | 83.8 |

## Cost Comparison

| Model | Input ($/1M tok) | Output ($/1M tok) | Context Window | Rate Limit |
|-------|-------------------|--------------------|----|---|
| GPT-5 | $15.00 | $60.00 | 256K | 10K RPM |
| Claude Opus 4 | $15.00 | $75.00 | 200K | 4K RPM |
| Gemini Ultra 2 | $12.50 | $50.00 | 2M | 1K RPM |
| DeepSeek R2 | $2.00 | $8.00 | 128K | Unlimited |
| LLaMA 4 405B | Free (self-host) | Free (self-host) | 128K | N/A |

## Key Takeaways

1. **Math reasoning is the new frontier** — DeepSeek R2's 85.2 on MATH is remarkable for its parameter count
2. **Cost efficiency varies wildly** — DeepSeek R2 offers 90% of GPT-5 performance at 13% of the cost
3. **Context windows keep growing** — Gemini's 2M context is useful for code analysis and long documents
4. **Open source is closing the gap** — LLaMA 4 405B is within 5% of frontier models on most benchmarks

## Methodology

All benchmarks were run using the official evaluation harness (EleutherAI lm-evaluation-harness v0.4) with default settings. Models were accessed through their official APIs. Temperature was set to 0 for all evaluations except HumanEval (temperature 0.2, pass@1).

### Limitations

- **Contamination**: We cannot fully verify that evaluation data was not in training sets
- **API variability**: Different API calls may hit different model versions
- **Task selection bias**: These benchmarks may not represent real-world usage patterns

---

*Data compiled by the AI Benchmarks Consortium. For full methodology and raw data, see our [GitHub repository](https://github.com/ai-benchmarks/2026-q1).*

*Last updated: March 3, 2026*
