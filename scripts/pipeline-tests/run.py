#!/usr/bin/env python3
"""Pipeline testing framework CLI.

Usage:
    python3 scripts/pipeline-tests/run.py clean --fixture arxiv-paper
    python3 scripts/pipeline-tests/run.py clean --all
    python3 scripts/pipeline-tests/run.py extract --fixture arxiv-paper --model gemini/gemini-2.0-flash
    python3 scripts/pipeline-tests/run.py list [--layer X] [--last N]
    python3 scripts/pipeline-tests/run.py inspect <session_id> [--full]
    python3 scripts/pipeline-tests/run.py evaluate <session_id>
    python3 scripts/pipeline-tests/run.py compare <id_a> <id_b>
    python3 scripts/pipeline-tests/run.py compare --fixture arxiv-paper
    python3 scripts/pipeline-tests/run.py report [--layer LAYER]
    python3 scripts/pipeline-tests/run.py prune [--keep N]
    python3 scripts/pipeline-tests/run.py fixture-list [--layer LAYER]
    python3 scripts/pipeline-tests/run.py fixture-create --url URL --name NAME --layer clean_markdown
    python3 scripts/pipeline-tests/run.py fixture-from-article --article-id ID --name NAME
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure we can import lib/
sys.path.insert(0, str(Path(__file__).parent))

from lib import FIXTURES_DIR, SESSIONS_DIR, SCRIPTS_DIR, PROJECT_DIR
from lib.session import (
    list_sessions, load_session, save_session, delete_session, prune_sessions,
)
from lib.runner import (
    run_clean_markdown, run_article_extraction, run_entity_concepts,
    run_atomic_claims, run_end_to_end, list_fixtures, load_fixture,
)
from lib.compare import compare_sessions, compare_fixture, generate_report


def cmd_clean(args):
    """Run clean_markdown tests."""
    fixtures = list_fixtures("clean_markdown") if args.all else [args.fixture]
    if not fixtures:
        print("No clean_markdown fixtures found.", file=sys.stderr)
        return 1

    results = []
    for name in fixtures:
        print(f"\n{'='*60}")
        print(f"  clean_markdown: {name}")
        print(f"{'='*60}")
        try:
            result = run_clean_markdown(name)
            ev = result.get("evaluation", {})
            status = ev.get("summary", "?")
            print(f"  {status}")
            for issue in ev.get("issues", []):
                print(f"    - {issue}")
            print(f"  Session: {result['session_id']} ({result.get('duration_ms', '?')}ms)")
            results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            results.append({"fixture": name, "error": str(e)})

    passed = sum(1 for r in results if r.get("evaluation", {}).get("pass"))
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{len(results)} passed")
    print(f"{'='*60}")
    return 0 if passed == len(results) else 1


def cmd_extract(args):
    """Run article extraction tests."""
    fixtures = list_fixtures("article_extraction") if args.all else [args.fixture]
    models = args.model or [None]
    if not fixtures:
        print("No article_extraction fixtures found.", file=sys.stderr)
        return 1

    results = []
    for name in fixtures:
        for model in models:
            model_label = model or "default"
            print(f"\n{'='*60}")
            print(f"  article_extraction: {name} [{model_label}]")
            print(f"{'='*60}")
            try:
                result = run_article_extraction(name, model=model)
                if result.get("status") == "completed":
                    output = result.get("output", {})
                    ev = result.get("evaluation", {})
                    struct_summary = ev.get("summary", "")
                    print(f"  OK: {output.get('content_type', '?')}, "
                          f"{len(output.get('sections', []))} sections, "
                          f"{len(output.get('interest_topics', []))} interest_topics")
                    print(f"  Title: {output.get('title', '?')}")
                    print(f"  Summary: {output.get('one_line_summary', '?')}")
                    if struct_summary:
                        print(f"  Structure: {struct_summary}")
                    for issue in ev.get("issues", [])[:5]:
                        print(f"    - {issue}")
                else:
                    print(f"  {result.get('status', 'error')}: {result.get('error', '?')}")
                tok = result.get("token_usage") or {}
                print(f"  Session: {result['session_id']} ({result.get('duration_ms', '?')}ms, "
                      f"{tok.get('total_tokens', '?')} tokens)")
                results.append(result)
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                results.append({"fixture": name, "model": model, "error": str(e)})

    completed = sum(1 for r in results if r.get("status") == "completed")
    print(f"\n  Results: {completed}/{len(results)} completed")
    return 0 if completed == len(results) else 1


def cmd_claims(args):
    """Run atomic claims extraction tests."""
    fixtures = list_fixtures("atomic_claims") if args.all else [args.fixture]
    models = args.model or [None]
    if not fixtures:
        print("No atomic_claims fixtures found.", file=sys.stderr)
        return 1

    results = []
    for name in fixtures:
        for model in models:
            model_label = model or "default"
            print(f"\n{'='*60}")
            print(f"  atomic_claims: {name} [{model_label}]")
            print(f"{'='*60}")
            try:
                result = run_atomic_claims(name, model=model)
                if result.get("status") == "completed":
                    output = result.get("output", {})
                    ev = result.get("evaluation", {})
                    claims = output.get("claims", [])
                    struct_summary = ev.get("summary", "")
                    type_dist = ev.get("type_distribution", {})
                    print(f"  OK: {len(claims)} claims extracted")
                    if type_dist:
                        dist_str = ", ".join(f"{k}:{v}" for k, v in sorted(type_dist.items()))
                        print(f"  Types: {dist_str}")
                    if struct_summary:
                        print(f"  Structure: {struct_summary}")
                    for issue in ev.get("issues", [])[:5]:
                        print(f"    - {issue}")
                else:
                    print(f"  {result.get('status', 'error')}: {result.get('error', '?')}")
                tok = result.get("token_usage") or {}
                print(f"  Session: {result['session_id']} ({result.get('duration_ms', '?')}ms, "
                      f"{tok.get('total_tokens', '?')} tokens)")
                results.append(result)
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                results.append({"fixture": name, "model": model, "error": str(e)})

    completed = sum(1 for r in results if r.get("status") == "completed")
    print(f"\n{'='*60}")
    print(f"  Results: {completed}/{len(results)} completed")
    print(f"{'='*60}")
    return 0 if completed == len(results) else 1


def cmd_entities(args):
    """Run entity concept extraction tests."""
    fixtures = list_fixtures("entity_concepts") if args.all else [args.fixture]
    models = args.model or [None]
    if not fixtures:
        print("No entity_concepts fixtures found.", file=sys.stderr)
        return 1

    results = []
    for name in fixtures:
        for model in models:
            print(f"\n{'='*60}")
            print(f"  entity_concepts: {name} [{model or 'default'}]")
            print(f"{'='*60}")
            try:
                result = run_entity_concepts(name, model=model)
                if result.get("status") == "completed":
                    output = result.get("output", {})
                    raw = output.get("raw_concepts", [])
                    deduped = output.get("deduped_concepts", [])
                    print(f"  OK: {len(raw)} raw → {len(deduped)} deduped concepts")
                else:
                    print(f"  {result.get('status')}: {result.get('error', '?')}")
                tok = result.get("token_usage") or {}
                print(f"  Session: {result['session_id']} ({result.get('duration_ms', '?')}ms, "
                      f"{tok.get('total_tokens', '?')} tokens)")
                results.append(result)
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                results.append({"fixture": name, "model": model, "error": str(e)})

    completed = sum(1 for r in results if r.get("status") == "completed")
    print(f"\n  Results: {completed}/{len(results)} completed")
    return 0 if completed == len(results) else 1


def cmd_e2e(args):
    """Run end-to-end tests."""
    fixtures = list_fixtures("end_to_end") if args.all else [args.fixture]
    models = args.model or [None]
    if not fixtures:
        print("No end_to_end fixtures found.", file=sys.stderr)
        return 1

    results = []
    for name in fixtures:
        for model in models:
            print(f"\n  end_to_end: {name} [{model or 'default'}]")
            try:
                result = run_end_to_end(name, model=model)
                print(f"  Status: {result.get('status')}")
                print(f"  Session: {result['session_id']}")
                results.append(result)
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                results.append({"fixture": name, "error": str(e)})

    completed = sum(1 for r in results if r.get("status") == "completed")
    print(f"\n  Results: {completed}/{len(results)} completed")
    return 0 if completed == len(results) else 1


def cmd_list(args):
    """List sessions."""
    sessions = list_sessions(layer=args.layer, last=args.last)
    if not sessions:
        print("No sessions found.")
        return 0

    print(f"\n{'ID':<14} {'Layer':<22} {'Fixture':<22} {'Model':<30} {'Status':<12}")
    print("-" * 100)
    for s in sessions:
        print(f"{s['session_id']:<14} {s['layer']:<22} {s['fixture']:<22} "
              f"{(s.get('model') or 'default'):<30} {s['status']:<12}")
    print(f"\n{len(sessions)} sessions")
    return 0


def cmd_inspect(args):
    """Inspect a session."""
    try:
        data = load_session(args.session_id)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.full:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        meta = data.get("metadata", {})
        model_str = meta.get("model") or "default"
        print(f"\nSession: {meta.get('session_id')}")
        print(f"Layer: {meta.get('layer')}")
        print(f"Fixture: {meta.get('fixture')}")
        print(f"Model: {model_str}")
        print(f"Status: {meta.get('status')}")
        print(f"Duration: {meta.get('duration_ms')}ms")
        tok = meta.get("token_usage") or {}
        if tok:
            print(f"Tokens: {tok.get('total_tokens', '?')} "
                  f"(prompt: {tok.get('prompt_tokens', '?')}, "
                  f"completion: {tok.get('completion_tokens', '?')})")

        ev = data.get("evaluation", {})
        if ev:
            print(f"\n--- Evaluation ---")
            # Structure checks (embedded in extraction evaluations)
            struct = ev.get("structure", {})
            if struct:
                print(f"  Structure: {struct.get('summary', '?')}")
                for issue in struct.get("issues", [])[:5]:
                    print(f"    - {issue}")

            if "checks" in ev:
                for check, passed in ev["checks"].items():
                    print(f"  {'PASS' if passed else 'FAIL'}: {check}")
                print(f"  {ev.get('summary', '')}")
            if "scores" in ev:
                for dim, score in ev["scores"].items():
                    print(f"  {dim}: {score}/5")
                print(f"  Overall: {ev.get('overall', '?')}")
            for issue in ev.get("issues", []):
                print(f"  ! {issue}")

        if data.get("output_md"):
            print(f"\n--- Output ---")
            md = data["output_md"]
            if args.tail:
                # Show last N chars
                print(f"... (showing last {args.tail} chars)")
                print(md[-args.tail:])
            else:
                print(md[:4000])
                if len(md) > 4000:
                    print(f"\n... ({len(md)} chars total, use --full or --tail N)")

    return 0


def cmd_evaluate(args):
    """Run LLM-as-judge evaluation on a completed session."""
    try:
        data = load_session(args.session_id)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    meta = data.get("metadata", {})
    layer = meta.get("layer", "")
    judge_model = args.model or "gemini/gemini-2.0-flash"

    if layer == "clean_markdown":
        print("clean_markdown sessions are auto-evaluated (deterministic). Use 'inspect' to view.")
        return 0

    elif layer == "article_extraction":
        from lib.evaluator import evaluate_article_extraction
        fixture = load_fixture("article_extraction", meta["fixture"])
        output = data.get("output", {})
        print(f"Running LLM-as-judge on session {args.session_id} (judge: {judge_model})...")
        evaluation = evaluate_article_extraction(
            fixture["input_text"], fixture["metadata"].get("title", ""),
            output, judge_model=judge_model,
        )
        save_session(meta, output, evaluation)
        _print_evaluation(evaluation)
        return 0

    elif layer == "atomic_claims":
        from lib.evaluator import evaluate_atomic_claims
        fixture = load_fixture("atomic_claims", meta["fixture"])
        output = data.get("output", {})
        claims = output.get("claims", [])
        print(f"Running LLM-as-judge on session {args.session_id} (judge: {judge_model})...")
        evaluation = evaluate_atomic_claims(
            fixture["input_text"], fixture["metadata"].get("title", ""),
            claims, metadata=fixture.get("metadata"), judge_model=judge_model,
        )
        save_session(meta, output, evaluation)
        _print_evaluation(evaluation)
        return 0

    elif layer == "entity_concepts":
        from lib.evaluator import build_entity_judge_prompt
        from lib.runner import call_llm_instrumented
        from extract_entity_concepts import parse_json_response

        fixture = load_fixture("entity_concepts", meta["fixture"])
        output = data.get("output", {})
        entities = output.get("deduped_concepts", output.get("raw_concepts", []))
        prompt = build_entity_judge_prompt(fixture["articles"], entities)
        print(f"Running LLM-as-judge on session {args.session_id} (judge: {judge_model})...")
        result = call_llm_instrumented(prompt, model=judge_model)
        if result.get("response"):
            evaluation = parse_json_response(result["response"])
            if evaluation and isinstance(evaluation, dict):
                save_session(meta, output, evaluation)
                _print_evaluation(evaluation)
                return 0
        print("Evaluation failed.", file=sys.stderr)
        return 1

    elif layer == "end_to_end":
        # Re-run both clean and extraction evaluations
        output = data.get("output", {})
        if output.get("extraction"):
            from lib.evaluator import evaluate_article_extraction
            fixture_content = output.get("cleaned_text", "")
            fixture_title = output.get("fetched_title", "")
            print(f"Running LLM-as-judge on session {args.session_id} (judge: {judge_model})...")
            evaluation = evaluate_article_extraction(
                fixture_content, fixture_title,
                output["extraction"], judge_model=judge_model,
            )
            save_session(meta, output, evaluation)
            _print_evaluation(evaluation)
            return 0
        else:
            print("No extraction output to evaluate.", file=sys.stderr)
            return 1

    else:
        print(f"Evaluation not supported for layer '{layer}'", file=sys.stderr)
        return 1


def _print_evaluation(evaluation: dict):
    """Pretty-print evaluation results."""
    struct = evaluation.get("structure", {})
    if struct:
        print(f"\nStructure: {struct.get('summary', '?')}")
        for issue in struct.get("issues", [])[:5]:
            print(f"  - {issue}")

    scores = evaluation.get("scores", {})
    if scores:
        print(f"\nScores:")
        for dim, score in sorted(scores.items()):
            print(f"  {dim}: {score}/5")
        print(f"  Overall: {evaluation.get('overall', '?')}")

    for issue in evaluation.get("issues", []):
        print(f"  ! {issue}")


def cmd_compare(args):
    """Compare two sessions or latest sessions for a fixture."""
    if args.fixture:
        result = compare_fixture(args.fixture, layer=args.layer)
    elif args.id_a and args.id_b:
        result = compare_sessions(args.id_a, args.id_b)
    else:
        print("Provide --fixture or two session IDs", file=sys.stderr)
        return 1
    print(result)
    return 0


def cmd_report(args):
    """Generate pipeline quality report."""
    print(generate_report(layer=args.layer))
    return 0


def cmd_prune(args):
    """Delete old sessions, keeping N most recent per fixture+layer."""
    keep = args.keep or 5
    deleted = prune_sessions(keep_last=keep, layer=args.layer)
    print(f"Deleted {deleted} old sessions (kept last {keep} per fixture+layer)")
    return 0


def cmd_delete(args):
    """Delete a specific session."""
    if delete_session(args.session_id):
        print(f"Deleted session {args.session_id}")
    else:
        print(f"Session {args.session_id} not found", file=sys.stderr)
        return 1
    return 0


def cmd_fixture_list(args):
    """List available fixtures."""
    layers = [args.layer] if args.layer else ["clean_markdown", "article_extraction", "atomic_claims", "entity_concepts", "end_to_end"]
    for layer in layers:
        fixtures = list_fixtures(layer)
        if fixtures:
            print(f"\n{layer}:")
            for f in fixtures:
                meta_path = FIXTURES_DIR / layer / f / "metadata.json"
                meta = ""
                if meta_path.exists():
                    try:
                        m = json.loads(meta_path.read_text())
                        meta = f" — {m.get('title', m.get('description', ''))}"
                    except json.JSONDecodeError:
                        meta = " — (corrupt metadata)"
                print(f"  {f}{meta}")
    return 0


def cmd_fixture_create(args):
    """Create a fixture from a URL."""
    from build_articles import fetch_article

    print(f"Fetching {args.url}...")
    fetched = fetch_article(args.url)
    if not fetched:
        print("Failed to fetch article.", file=sys.stderr)
        return 1

    fixture_dir = FIXTURES_DIR / args.layer / args.name
    fixture_dir.mkdir(parents=True, exist_ok=True)

    if args.layer == "clean_markdown":
        import requests
        try:
            resp = requests.get(args.url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Petrarca/1.0)"
            })
            resp.raise_for_status()
            (fixture_dir / "input.html").write_text(resp.text)
        except Exception as e:
            # Fallback: save the trafilatura-extracted text
            print(f"  Warning: Could not fetch raw HTML ({e}), saving extracted text instead")
            (fixture_dir / "input.md").write_text(fetched["text"])
    else:
        from build_articles import clean_markdown
        cleaned = clean_markdown(fetched["text"])
        (fixture_dir / "input.md").write_text(cleaned)

    metadata = {
        "title": fetched.get("title", args.name),
        "url": args.url,
        "hostname": fetched.get("hostname", ""),
        "word_count": fetched.get("word_count", 0),
        "created": datetime.now().isoformat(),
    }
    (fixture_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print(f"Created fixture: {fixture_dir}")
    print(f"  Title: {metadata['title']}")
    print(f"  Words: {metadata['word_count']}")
    return 0


def cmd_fixture_from_article(args):
    """Create a fixture from an existing article in articles.json."""
    articles_path = PROJECT_DIR / "data" / "articles.json"
    if not articles_path.exists():
        print(f"articles.json not found at {articles_path}", file=sys.stderr)
        return 1

    articles = json.loads(articles_path.read_text())
    article = next((a for a in articles if a["id"] == args.article_id), None)
    if not article:
        print(f"Article {args.article_id} not found. Available:", file=sys.stderr)
        for a in articles[:15]:
            print(f"  {a['id']}: {a.get('title', '?')[:60]}", file=sys.stderr)
        if len(articles) > 15:
            print(f"  ... and {len(articles) - 15} more", file=sys.stderr)
        return 1

    name = args.name or args.article_id

    # Create article_extraction fixture
    fixture_dir = FIXTURES_DIR / "article_extraction" / name
    fixture_dir.mkdir(parents=True, exist_ok=True)

    content = article.get("content_markdown", "")
    (fixture_dir / "input.md").write_text(content)
    metadata = {
        "title": article.get("title", ""),
        "url": article.get("source_url", ""),
        "hostname": article.get("hostname", ""),
        "word_count": article.get("word_count", len(content.split())),
        "article_id": article["id"],
    }
    (fixture_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print(f"Created fixture: {fixture_dir}")
    print(f"  Title: {metadata['title']}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Petrarca pipeline testing framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # clean
    p = sub.add_parser("clean", help="Run clean_markdown tests")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixture", help="Fixture name")
    g.add_argument("--all", action="store_true", help="Run all fixtures")

    # extract
    p = sub.add_parser("extract", help="Run article extraction tests")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixture", help="Fixture name")
    g.add_argument("--all", action="store_true", help="Run all fixtures")
    p.add_argument("--model", action="append", help="Model(s) to test (repeatable)")

    # claims
    p = sub.add_parser("claims", help="Run atomic claims extraction tests")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixture", help="Fixture name")
    g.add_argument("--all", action="store_true", help="Run all fixtures")
    p.add_argument("--model", action="append", help="Model(s) to test (repeatable)")

    # entities
    p = sub.add_parser("entities", help="Run entity concept extraction tests")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixture", help="Fixture name")
    g.add_argument("--all", action="store_true", help="Run all fixtures")
    p.add_argument("--model", action="append", help="Model(s) to test")

    # e2e
    p = sub.add_parser("e2e", help="Run end-to-end tests")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixture", help="Fixture name")
    g.add_argument("--all", action="store_true", help="Run all fixtures")
    p.add_argument("--model", action="append", help="Model(s) to test")

    # list
    p = sub.add_parser("list", help="List sessions")
    p.add_argument("--layer", help="Filter by layer")
    p.add_argument("--last", type=int, help="Show last N sessions")

    # inspect
    p = sub.add_parser("inspect", help="Inspect a session")
    p.add_argument("session_id", help="Session ID")
    p.add_argument("--full", action="store_true", help="Show full JSON output")
    p.add_argument("--tail", type=int, help="Show last N chars of output")

    # evaluate
    p = sub.add_parser("evaluate", help="Run LLM-as-judge on a session")
    p.add_argument("session_id", help="Session ID")
    p.add_argument("--model", help="Judge model (default: gemini-2.0-flash)")

    # compare
    p = sub.add_parser("compare", help="Compare sessions")
    p.add_argument("id_a", nargs="?", help="First session ID")
    p.add_argument("id_b", nargs="?", help="Second session ID")
    p.add_argument("--fixture", help="Compare latest sessions for this fixture")
    p.add_argument("--layer", help="Filter by layer (with --fixture)")

    # report
    p = sub.add_parser("report", help="Generate pipeline quality report")
    p.add_argument("--layer", help="Filter by layer")

    # prune
    p = sub.add_parser("prune", help="Delete old sessions")
    p.add_argument("--keep", type=int, default=5, help="Keep last N per fixture+layer (default: 5)")
    p.add_argument("--layer", help="Only prune this layer")

    # delete
    p = sub.add_parser("delete", help="Delete a specific session")
    p.add_argument("session_id", help="Session ID to delete")

    # fixture-list
    p = sub.add_parser("fixture-list", help="List fixtures")
    p.add_argument("--layer", help="Filter by layer")

    # fixture-create
    p = sub.add_parser("fixture-create", help="Create fixture from URL")
    p.add_argument("--url", required=True, help="URL to fetch")
    p.add_argument("--name", required=True, help="Fixture name")
    p.add_argument("--layer", required=True, choices=["clean_markdown", "article_extraction"])

    # fixture-from-article
    p = sub.add_parser("fixture-from-article", help="Create fixture from articles.json")
    p.add_argument("--article-id", required=True, help="Article ID")
    p.add_argument("--name", help="Fixture name (default: article ID)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "clean": cmd_clean,
        "extract": cmd_extract,
        "claims": cmd_claims,
        "entities": cmd_entities,
        "e2e": cmd_e2e,
        "list": cmd_list,
        "inspect": cmd_inspect,
        "evaluate": cmd_evaluate,
        "compare": cmd_compare,
        "report": cmd_report,
        "prune": cmd_prune,
        "delete": cmd_delete,
        "fixture-list": cmd_fixture_list,
        "fixture-create": cmd_fixture_create,
        "fixture-from-article": cmd_fixture_from_article,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
