"""Compare sessions: side-by-side evaluation tables."""

import json
from .session import load_session, find_sessions_for_fixture


def compare_sessions(id_a: str, id_b: str) -> str:
    """Compare two sessions. Returns markdown table."""
    a = load_session(id_a)
    b = load_session(id_b)
    return _build_comparison(a, b)


def compare_fixture(fixture: str, layer: str | None = None) -> str:
    """Compare the two most recent sessions for a fixture.

    If layer is not specified, infers it from the most recent session.
    """
    sessions = find_sessions_for_fixture(fixture, layer=layer)
    if not sessions:
        return f"No sessions found for fixture '{fixture}'"

    # If no layer specified, use the layer of the most recent session
    # and filter to only that layer (prevents cross-layer comparison)
    if not layer:
        inferred_layer = sessions[0]["layer"]
        sessions = [s for s in sessions if s["layer"] == inferred_layer]

    if len(sessions) < 2:
        layer_label = layer or sessions[0]["layer"]
        return (f"Need at least 2 sessions for fixture '{fixture}' "
                f"(layer={layer_label}), found {len(sessions)}")

    a = load_session(sessions[0]["session_id"])
    b = load_session(sessions[1]["session_id"])
    return _build_comparison(a, b)


def _build_comparison(a: dict, b: dict) -> str:
    meta_a = a.get("metadata", {})
    meta_b = b.get("metadata", {})
    eval_a = a.get("evaluation", {})
    eval_b = b.get("evaluation", {})

    model_a = meta_a.get("model") or "default"
    model_b = meta_b.get("model") or "default"

    lines = [
        "# Session Comparison",
        "",
        "| | Session A | Session B |",
        "|---|---|---|",
        f"| **ID** | {meta_a.get('session_id', '?')} | {meta_b.get('session_id', '?')} |",
        f"| **Layer** | {meta_a.get('layer', '?')} | {meta_b.get('layer', '?')} |",
        f"| **Fixture** | {meta_a.get('fixture', '?')} | {meta_b.get('fixture', '?')} |",
        f"| **Model** | {model_a} | {model_b} |",
        f"| **Status** | {meta_a.get('status', '?')} | {meta_b.get('status', '?')} |",
        f"| **Duration** | {meta_a.get('duration_ms', '?')}ms | {meta_b.get('duration_ms', '?')}ms |",
    ]

    # Token usage
    tok_a = meta_a.get("token_usage") or {}
    tok_b = meta_b.get("token_usage") or {}
    if tok_a or tok_b:
        lines.append(f"| **Tokens** | {tok_a.get('total_tokens', 'n/a')} | {tok_b.get('total_tokens', 'n/a')} |")

    lines.append("")

    # Warn if layers differ
    layer_a = meta_a.get("layer", "")
    layer_b = meta_b.get("layer", "")
    if layer_a != layer_b:
        lines.append(f"> **Warning:** Comparing different layers ({layer_a} vs {layer_b})")
        lines.append("")

    layer = layer_a

    if layer == "clean_markdown":
        _compare_clean(lines, eval_a, eval_b, a, b)

    elif layer in ("article_extraction", "entity_concepts"):
        _compare_scored(lines, eval_a, eval_b)

        # Show key output differences for extraction
        if layer == "article_extraction":
            _compare_extraction_content(lines, a, b)

    return "\n".join(lines)


def _compare_clean(lines: list, eval_a: dict, eval_b: dict, a: dict, b: dict):
    """Compare clean_markdown evaluations."""
    checks_a = eval_a.get("checks", {})
    checks_b = eval_b.get("checks", {})
    all_checks = sorted(set(list(checks_a.keys()) + list(checks_b.keys())))

    if all_checks:
        lines.append("## Checks")
        lines.append("")
        lines.append("| Check | A | B |")
        lines.append("|---|---|---|")
        for check in all_checks:
            va = "PASS" if checks_a.get(check) else "FAIL" if check in checks_a else "-"
            vb = "PASS" if checks_b.get(check) else "FAIL" if check in checks_b else "-"
            marker = " **" if va != vb else ""
            lines.append(f"| {check} | {va} | {vb} |{marker}")

    lines.append("")
    lines.append(f"**Result A:** {eval_a.get('summary', 'n/a')}")
    lines.append(f"**Result B:** {eval_b.get('summary', 'n/a')}")

    # Content diff: word count comparison
    out_a = a.get("output", {})
    out_b = b.get("output", {})
    text_a = out_a.get("cleaned_text", "")
    text_b = out_b.get("cleaned_text", "")
    if text_a and text_b:
        lines.append("")
        lines.append("## Content Stats")
        lines.append(f"- A: {len(text_a.split())} words, {len(text_a)} chars")
        lines.append(f"- B: {len(text_b.split())} words, {len(text_b)} chars")
        if text_a == text_b:
            lines.append("- **Identical output**")


def _compare_scored(lines: list, eval_a: dict, eval_b: dict):
    """Compare sessions that have scores (extraction, entities)."""
    scores_a = eval_a.get("scores", {})
    scores_b = eval_b.get("scores", {})

    # Check for structural evaluation too
    struct_a = eval_a.get("structure", {})
    struct_b = eval_b.get("structure", {})
    if struct_a or struct_b:
        lines.append("## Structure Checks")
        lines.append(f"- A: {struct_a.get('summary', 'n/a')}")
        lines.append(f"- B: {struct_b.get('summary', 'n/a')}")
        lines.append("")

    all_dims = sorted(set(list(scores_a.keys()) + list(scores_b.keys())))
    if all_dims:
        lines.append("## Scores")
        lines.append("")
        lines.append("| Dimension | A | B | Delta |")
        lines.append("|---|---|---|---|")
        for dim in all_dims:
            sa = scores_a.get(dim, "-")
            sb = scores_b.get(dim, "-")
            if isinstance(sa, (int, float)) and isinstance(sb, (int, float)):
                delta = sb - sa
                delta_str = f"{delta:+.1f}"
            else:
                delta_str = "-"
            lines.append(f"| {dim} | {sa} | {sb} | {delta_str} |")
        lines.append("")
        overall_a = eval_a.get("overall", "-")
        overall_b = eval_b.get("overall", "-")
        lines.append(f"**Overall A:** {overall_a}  ")
        lines.append(f"**Overall B:** {overall_b}  ")

    # Issues
    issues_a = eval_a.get("issues", [])
    issues_b = eval_b.get("issues", [])
    if issues_a or issues_b:
        lines.append("")
        lines.append("## Issues")
        if issues_a:
            lines.append(f"\n**A:** {'; '.join(issues_a)}")
        if issues_b:
            lines.append(f"\n**B:** {'; '.join(issues_b)}")


def _compare_extraction_content(lines: list, a: dict, b: dict):
    """Show key differences between two extraction outputs."""
    out_a = a.get("output", {})
    out_b = b.get("output", {})
    if not out_a or not out_b:
        return

    lines.append("")
    lines.append("## Content Comparison")
    lines.append("")

    # Titles
    ta = out_a.get("title", "?")
    tb = out_b.get("title", "?")
    if ta != tb:
        lines.append(f"**Title A:** {ta}")
        lines.append(f"**Title B:** {tb}")
        lines.append("")

    # Key claims comparison
    ca = set(out_a.get("key_claims", []))
    cb = set(out_b.get("key_claims", []))
    if ca != cb:
        only_a = ca - cb
        only_b = cb - ca
        if only_a:
            lines.append(f"**Claims only in A:** {len(only_a)}")
            for c in list(only_a)[:3]:
                lines.append(f"  - {c[:100]}")
        if only_b:
            lines.append(f"**Claims only in B:** {len(only_b)}")
            for c in list(only_b)[:3]:
                lines.append(f"  - {c[:100]}")
        lines.append("")

    # Interest topics count
    it_a = len(out_a.get("interest_topics", []))
    it_b = len(out_b.get("interest_topics", []))
    nc_a = len(out_a.get("novelty_claims", []))
    nc_b = len(out_b.get("novelty_claims", []))
    sec_a = len(out_a.get("sections", []))
    sec_b = len(out_b.get("sections", []))

    lines.append(f"| Metric | A | B |")
    lines.append(f"|---|---|---|")
    lines.append(f"| Sections | {sec_a} | {sec_b} |")
    lines.append(f"| Interest topics | {it_a} | {it_b} |")
    lines.append(f"| Novelty claims | {nc_a} | {nc_b} |")


def generate_report(layer: str | None = None) -> str:
    """Generate a summary report of all fixtures across layers."""
    from .session import list_sessions
    from .runner import list_fixtures

    layers = [layer] if layer else ["clean_markdown", "article_extraction", "entity_concepts", "end_to_end"]
    lines = ["# Pipeline Quality Report", ""]

    for ly in layers:
        fixtures = list_fixtures(ly)
        if not fixtures:
            continue

        lines.append(f"## {ly}")
        lines.append("")

        for fix in fixtures:
            sessions = find_sessions_for_fixture(fix, layer=ly)
            if not sessions:
                lines.append(f"- **{fix}**: no sessions")
                continue

            latest = sessions[0]
            sid = latest["session_id"]
            try:
                data = load_session(sid)
                ev = data.get("evaluation", {})

                if ly == "clean_markdown":
                    status = ev.get("summary", "?")
                    issue_count = len(ev.get("issues", []))
                    lines.append(f"- **{fix}**: {status} ({issue_count} issues)")
                else:
                    overall = ev.get("overall", "?")
                    struct = ev.get("structure", {})
                    struct_status = struct.get("summary", "")
                    scores = ev.get("scores", {})
                    if scores:
                        score_str = ", ".join(f"{k}={v}" for k, v in sorted(scores.items()))
                        lines.append(f"- **{fix}** [{latest.get('model', 'default')}]: overall={overall} ({score_str})")
                    elif struct_status:
                        lines.append(f"- **{fix}**: {struct_status}")
                    else:
                        lines.append(f"- **{fix}**: {latest['status']}")

                # Show issues (up to 3)
                for issue in ev.get("issues", [])[:3]:
                    lines.append(f"  - {issue}")

            except Exception as e:
                lines.append(f"- **{fix}**: error loading session ({e})")

        lines.append("")

    return "\n".join(lines)
