Skip to content

Navigation Menu

Toggle navigation

[Sign in](https://github.com/login)

[Sign up](https://github.com/signup)

[litellm](https://github.com/BerriAI/litellm) / [README.md](https://github.com/BerriAI/litellm/blob/main/README.md)

⭐ 18.2k   🔱 Fork 2.1k   👁 Watch 142

---

[![PyPI version](https://badge.fury.io/py/litellm.svg)](https://badge.fury.io/py/litellm)
[![Downloads](https://static.pepy.tech/badge/litellm/month)](https://pepy.tech/project/litellm)
[![GitHub stars](https://img.shields.io/github/stars/BerriAI/litellm)](https://github.com/BerriAI/litellm/stargazers)
[![Discord](https://img.shields.io/discord/1234567890)](https://discord.gg/litellm)
[![](https://dcbadge.vercel.app/api/server/litellm?compact=true&style=flat)](https://discord.gg/litellm)
[![CI](https://github.com/BerriAI/litellm/actions/workflows/ci.yml/badge.svg)](https://github.com/BerriAI/litellm/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/BerriAI/litellm/blob/main/LICENSE)

[Documentation](https://docs.litellm.ai/) | [Discord](https://discord.gg/litellm) | [Twitter](https://twitter.com/litaborhq)

---

# 🚅 LiteLLM — Call 100+ LLMs using the OpenAI format

LiteLLM manages:

- Translating inputs to the provider's `completion`, `embedding`, and `image_generation` endpoints
- Consistent output. Text responses will always be available at `['choices'][0]['message']['content']`
- Retry/fallback logic across multiple deployments (e.g. Azure/OpenAI) — [Router](https://docs.litellm.ai/docs/routing)
- Spend tracking across projects/people [Budget Manager](https://docs.litellm.ai/docs/budget_manager)

## Quick Start

```bash
pip install litellm
```

```python
from litellm import completion
import os

## set ENV variables
os.environ["OPENAI_API_KEY"] = "your-key"
os.environ["ANTHROPIC_API_KEY"] = "your-key"

messages = [{"content": "Hello, how are you?", "role": "user"}]

# openai call
response = completion(model="gpt-4o", messages=messages)

# anthropic call
response = completion(model="claude-sonnet-4-20250514", messages=messages)

# gemini call
response = completion(model="gemini/gemini-2.0-flash", messages=messages)
```

## Supported Providers

| Provider | Completion | Streaming | Async | Embedding | Image Gen |
|----------|-----------|-----------|-------|-----------|-----------|
| OpenAI | ✅ | ✅ | ✅ | ✅ | ✅ |
| Anthropic | ✅ | ✅ | ✅ | ❌ | ❌ |
| Google Gemini | ✅ | ✅ | ✅ | ✅ | ✅ |
| Azure | ✅ | ✅ | ✅ | ✅ | ✅ |
| AWS Bedrock | ✅ | ✅ | ✅ | ✅ | ❌ |
| Cohere | ✅ | ✅ | ✅ | ✅ | ❌ |
| Ollama | ✅ | ✅ | ✅ | ✅ | ❌ |
| Hugging Face | ✅ | ✅ | ✅ | ✅ | ❌ |
| Replicate | ✅ | ✅ | ✅ | ❌ | ❌ |

[See all providers →](https://docs.litellm.ai/docs/providers)

## LiteLLM Proxy Server

Use LiteLLM as a proxy server to manage multiple LLM API keys and load-balance across providers:

```bash
litellm --model gpt-4o
```

The proxy provides:
- Unified API endpoint for all providers
- Key management and rate limiting
- Usage tracking and budgets
- Caching and retry logic

## Contributing

We love contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Contributors

<a href="https://github.com/BerriAI/litellm/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=BerriAI/litellm" />
</a>

Made with [contrib.rocks](https://contrib.rocks)

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=BerriAI/litellm&type=Date)](https://star-history.com/#BerriAI/litellm&Date)

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

About

Call all LLM APIs using the OpenAI format

### Resources

⭐ Stars: 18.2k
🔱 Forks: 2.1k
👁 Watchers: 142

### Languages

Python 87.2% TypeScript 8.1% Shell 2.4% Other 2.3%

### Releases

v1.52.0 Latest on Mar 4, 2026

### Used by 4.2k

### Activity

Last commit: 2 hours ago

Footer

© 2026 GitHub, Inc.

[Terms](https://docs.github.com/site-policy/github-terms/github-terms-of-service) · [Privacy](https://docs.github.com/site-policy/privacy-policies/github-privacy-statement) · [Security](https://github.com/security) · [Status](https://www.githubstatus.com/) · [Docs](https://docs.github.com/) · [Contact](https://support.github.com/) · [Manage cookies](https://github.com/settings/cookies) · [Do not share my personal information](https://github.com/settings/cookies)
