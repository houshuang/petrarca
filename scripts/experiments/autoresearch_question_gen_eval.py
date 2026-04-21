#!/usr/bin/env python3
"""
Eval harness for review question generation quality.

Generates questions for all fixtures using the current QUESTION_GEN_PROMPT_FACTUAL,
then has an LLM judge score each on three dimensions:
  - direct (1-3): Is it a direct, testable question (not oblique or wrapped in metaphor)?
  - natural (1-3): Does it sound like a knowledgeable friend, not an academic quiz?
  - specific (1-3): Is it answerable with one specific fact (name, date, event)?

Composite score = mean(direct + natural + specific) / 9, normalized to 0-1.

Usage: python autoresearch_question_gen_eval.py
Output: SCORE=X.XXXX (single line, parseable by the autoresearch loop)
"""
import json, os, sys, time
from pathlib import Path

# Load env
env_file = Path(__file__).parent.parent.parent / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent))
# TODO(session-88): migrate to claude_llm when this script gets revived
from gemini_llm import call_llm

FIXTURES = json.loads((Path(__file__).parent / 'fixtures_question_gen.json').read_text())

JUDGE_PROMPT = """You are evaluating knowledge review questions for a history app.
The goal is simple factual recall on first review: who, when, what.

Question being evaluated: "{question}"
Concept being tested: "{node_title}"
Source text: "{source_text}"

Score on three dimensions (1=poor, 2=ok, 3=good):

DIRECT: Is it a direct testable question, or does it hide the fact behind oblique framing?
- 3 = Asks plainly: "Who was Belisarius?" or "When did the Byzantines take Syracuse?"
- 2 = Mostly direct but slightly wordy
- 1 = Uses metaphor or academic framing to describe the fact ("architectural palimpsest", "successive transformations")

NATURAL: Does it sound like a knowledgeable friend would ask it, not an academic quiz?
- 3 = Conversational: "What was Dionysius I famous for?"
- 2 = Slightly formal but acceptable
- 1 = AI-sounding, stilted, over-elaborate

SPECIFIC: Is it answerable with a single specific fact (name, date, event)?
- 3 = Has a clear factual answer: a name, a year, a yes/no
- 2 = Answerable but somewhat open-ended
- 1 = Too vague — many things could be valid answers

Output JSON only: {{"direct": X, "natural": X, "specific": X, "note": "one sentence on worst issue if any"}}"""


def load_factual_prompt() -> str:
    """Extract QUESTION_GEN_PROMPT_FACTUAL from review_engine.py without importing it."""
    src = (Path(__file__).parent.parent / 'review_engine.py').read_text()
    # Find the triple-quoted string assigned to QUESTION_GEN_PROMPT_FACTUAL
    start = src.index('QUESTION_GEN_PROMPT_FACTUAL = """') + len('QUESTION_GEN_PROMPT_FACTUAL = """')
    end = src.index('"""', start)
    return src[start:end]


def generate_question(fixture: dict) -> dict:
    """Generate a question for a fixture using the current prompt from review_engine."""
    template = load_factual_prompt()
    temporal_ctx = f"Temporal hook: {fixture['temporal_hook']}" if fixture.get('temporal_hook') else ''
    prompt = template.format(
        node_title=fixture['node_title'],
        node_description=fixture.get('node_description', ''),
        source_text=fixture['source_text'][:400],
        temporal_context=temporal_ctx,
    )
    raw = call_llm(prompt, max_tokens=512, response_mime_type='application/json')
    if not raw:
        return {'question': '', 'error': 'no response'}
    try:
        text = raw.strip()
        if text.startswith('```'):
            text = '\n'.join(text.split('\n')[1:])
            text = text.rsplit('```', 1)[0]
        return json.loads(text)
    except Exception as e:
        return {'question': raw[:200], 'error': str(e)}


def judge_question(question: str, fixture: dict) -> dict:
    prompt = JUDGE_PROMPT.format(
        question=question,
        node_title=fixture['node_title'],
        source_text=fixture['source_text'][:200],
    )
    raw = call_llm(prompt, max_tokens=256, response_mime_type='application/json')
    if not raw:
        return {'direct': 1, 'natural': 1, 'specific': 1, 'note': 'no response'}
    try:
        text = raw.strip()
        if text.startswith('```'):
            text = '\n'.join(text.split('\n')[1:])
            text = text.rsplit('```', 1)[0]
        return json.loads(text)
    except Exception:
        return {'direct': 1, 'natural': 1, 'specific': 1, 'note': raw[:100]}


def run_eval(verbose: bool = False) -> float:
    total = 0.0
    results = []

    for fixture in FIXTURES:
        q_result = generate_question(fixture)
        question = q_result.get('question', '')

        if not question:
            score_obj = {'direct': 1, 'natural': 1, 'specific': 1, 'note': 'empty question'}
        else:
            score_obj = judge_question(question, fixture)

        raw_score = score_obj.get('direct', 1) + score_obj.get('natural', 1) + score_obj.get('specific', 1)
        normalized = raw_score / 9.0

        results.append({
            'id': fixture['id'],
            'node_title': fixture['node_title'],
            'question': question,
            'scores': score_obj,
            'normalized': normalized,
        })
        total += normalized

        if verbose:
            print(f"  [{fixture['id']}] {fixture['node_title'][:40]}")
            print(f"    Q: {question}")
            print(f"    Scores: D={score_obj.get('direct')} N={score_obj.get('natural')} S={score_obj.get('specific')} | {normalized:.2f} | {score_obj.get('note','')}")
            print()

        time.sleep(0.3)  # rate limit

    final_score = total / len(FIXTURES)
    return final_score, results


if __name__ == '__main__':
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    score, results = run_eval(verbose=verbose)

    # Save detailed results
    out_path = Path(__file__).parent / 'results' / 'question_gen_latest.json'
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({'score': score, 'results': results}, indent=2))

    print(f"SCORE={score:.4f}")
