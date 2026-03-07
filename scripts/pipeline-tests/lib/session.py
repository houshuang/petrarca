"""Session management: create, save, load, list, inspect."""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import SESSIONS_DIR

INDEX_PATH = SESSIONS_DIR / "sessions.json"


def _load_index() -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    try:
        return json.loads(INDEX_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        # Corrupted index — rebuild from session directories
        print(f"  Warning: sessions.json corrupted ({e}), rebuilding...", flush=True)
        return _rebuild_index()


def _rebuild_index() -> list[dict]:
    """Rebuild index by scanning session directories."""
    index = []
    if not SESSIONS_DIR.exists():
        return index
    for session_dir in SESSIONS_DIR.iterdir():
        if not session_dir.is_dir() or session_dir.name == "__pycache__":
            continue
        meta_path = session_dir / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                index.append({
                    "session_id": meta["session_id"],
                    "created": meta["created"],
                    "layer": meta["layer"],
                    "fixture": meta["fixture"],
                    "model": meta.get("model"),
                    "status": meta["status"],
                })
            except (json.JSONDecodeError, KeyError):
                continue
    _save_index(index)
    return index


def _save_index(index: list[dict]):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to temp, then rename
    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    tmp.rename(INDEX_PATH)


def create_session(layer: str, fixture: str, model: str | None = None) -> dict:
    """Create a new session and return its metadata dict."""
    session_id = uuid.uuid4().hex[:12]
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "session_id": session_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "layer": layer,
        "fixture": fixture,
        "model": model,
        "status": "running",
        "duration_ms": None,
        "token_usage": None,
    }
    (session_dir / "config.json").write_text(
        json.dumps({"layer": layer, "fixture": fixture, "model": model}, indent=2)
    )
    return metadata


def save_session(metadata: dict, output: dict | str, evaluation: dict | None = None,
                 llm_response: dict | None = None):
    """Save session results to disk and update the global index."""
    sid = metadata["session_id"]
    session_dir = SESSIONS_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save metadata
    (session_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    # Save output
    if isinstance(output, str):
        (session_dir / "output.md").write_text(output)
    else:
        (session_dir / "output.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False)
        )
        (session_dir / "output.md").write_text(_output_to_markdown(metadata, output))

    if evaluation:
        (session_dir / "evaluation.json").write_text(
            json.dumps(evaluation, indent=2, ensure_ascii=False)
        )

    if llm_response:
        (session_dir / "llm_response.json").write_text(
            json.dumps(llm_response, indent=2, ensure_ascii=False)
        )

    # Update index (atomic)
    index = _load_index()
    index = [s for s in index if s["session_id"] != sid]
    index.append({
        "session_id": sid,
        "created": metadata["created"],
        "layer": metadata["layer"],
        "fixture": metadata["fixture"],
        "model": metadata.get("model"),
        "status": metadata["status"],
    })
    _save_index(index)


def delete_session(session_id: str) -> bool:
    """Delete a session directory and remove from index."""
    session_dir = SESSIONS_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    index = _load_index()
    new_index = [s for s in index if s["session_id"] != session_id]
    if len(new_index) != len(index):
        _save_index(new_index)
        return True
    return False


def prune_sessions(keep_last: int = 10, layer: str | None = None) -> int:
    """Delete old sessions, keeping the N most recent per fixture+layer. Returns count deleted."""
    index = _load_index()
    # Group by (layer, fixture)
    groups: dict[tuple, list[dict]] = {}
    for s in index:
        if layer and s["layer"] != layer:
            continue
        key = (s["layer"], s["fixture"])
        groups.setdefault(key, []).append(s)

    to_delete = []
    for key, sessions in groups.items():
        sessions.sort(key=lambda s: s["created"], reverse=True)
        to_delete.extend(sessions[keep_last:])

    for s in to_delete:
        delete_session(s["session_id"])
    return len(to_delete)


def load_session(session_id: str) -> dict:
    """Load all session data. Returns dict with metadata, output, evaluation, etc."""
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise FileNotFoundError(f"Session {session_id} not found")

    result = {}
    for name in ["metadata", "config", "output", "evaluation", "llm_response"]:
        json_path = session_dir / f"{name}.json"
        if json_path.exists():
            try:
                result[name] = json.loads(json_path.read_text())
            except json.JSONDecodeError:
                result[name] = {"_error": f"Failed to parse {name}.json"}

    md_path = session_dir / "output.md"
    if md_path.exists():
        result["output_md"] = md_path.read_text()

    return result


def list_sessions(layer: str | None = None, last: int | None = None) -> list[dict]:
    """List sessions, optionally filtered by layer. Most recent first."""
    index = _load_index()
    if layer:
        index = [s for s in index if s["layer"] == layer]
    index.sort(key=lambda s: s["created"], reverse=True)
    if last:
        index = index[:last]
    return index


def find_sessions_for_fixture(fixture: str, layer: str | None = None) -> list[dict]:
    """Find all sessions for a given fixture name."""
    index = _load_index()
    results = [s for s in index if s["fixture"] == fixture]
    if layer:
        results = [s for s in results if s["layer"] == layer]
    results.sort(key=lambda s: s["created"], reverse=True)
    return results


def _output_to_markdown(metadata: dict, output: dict) -> str:
    """Convert structured output to human-readable markdown."""
    model_str = metadata.get("model") or "default"
    lines = [
        f"# Session {metadata['session_id']}",
        f"**Layer:** {metadata['layer']}  ",
        f"**Fixture:** {metadata['fixture']}  ",
        f"**Model:** {model_str}  ",
        f"**Created:** {metadata['created']}  ",
        "",
    ]

    if metadata["layer"] == "clean_markdown":
        lines.append("## Cleaned Output")
        lines.append("")
        text = output.get("cleaned_text", "")
        word_count = len(text.split())
        lines.append(f"Word count: {word_count}")
        lines.append("")
        # Show head and tail for full visibility (boilerplate hides at the end)
        if len(text) > 4000:
            lines.append("### First 2000 chars")
            lines.append(text[:2000])
            lines.append("")
            lines.append("### Last 1000 chars")
            lines.append(text[-1000:])
        else:
            lines.append(text)

    elif metadata["layer"] == "article_extraction":
        lines.append("## Extracted Article")
        lines.append("")
        for key in ["title", "one_line_summary", "content_type", "estimated_read_minutes"]:
            if key in output:
                lines.append(f"**{key}:** {output[key]}  ")
        lines.append("")
        if output.get("full_summary"):
            lines.append("### Summary")
            lines.append(output["full_summary"])
            lines.append("")
        if output.get("key_claims"):
            lines.append(f"### Key Claims ({len(output['key_claims'])})")
            for c in output["key_claims"]:
                lines.append(f"- {c}")
            lines.append("")
        if output.get("interest_topics"):
            lines.append(f"### Interest Topics ({len(output['interest_topics'])})")
            for t in output["interest_topics"]:
                parts = [t.get("broad", ""), t.get("specific", ""), t.get("entity", "")]
                lines.append(f"- {' > '.join(p for p in parts if p)}")
            lines.append("")
        if output.get("novelty_claims"):
            lines.append(f"### Novelty Claims ({len(output['novelty_claims'])})")
            for nc in output["novelty_claims"]:
                lines.append(f"- [{nc.get('specificity', '?')}] {nc.get('claim', '')}")
            lines.append("")
        if output.get("topics"):
            lines.append(f"### Topics")
            lines.append(", ".join(output["topics"]))
            lines.append("")
        if output.get("sections"):
            lines.append(f"### Sections ({len(output['sections'])})")
            for s in output["sections"]:
                lines.append(f"- **{s.get('heading', '')}**: {s.get('summary', '')}")
            lines.append("")

    elif metadata["layer"] == "entity_concepts":
        lines.append("## Extracted Entities")
        lines.append("")
        deduped = output.get("deduped_concepts", output.get("raw_concepts", []))
        raw = output.get("raw_concepts", [])
        lines.append(f"Raw: {len(raw)}, Deduplicated: {len(deduped)}")
        lines.append("")
        for c in deduped:
            aliases = ", ".join(c.get("aliases", []))
            alias_str = f" (aka {aliases})" if aliases else ""
            sources = ", ".join(c.get("source_article_ids", []))
            lines.append(f"- **{c.get('name', '?')}**{alias_str} [{c.get('topic', '?')}]")
            lines.append(f"  {c.get('description', '')}")
            if sources:
                lines.append(f"  Sources: {sources}")
        lines.append("")

    elif metadata["layer"] == "end_to_end":
        lines.append("## End-to-End Results")
        lines.append("")
        lines.append(f"Fetched title: {output.get('fetched_title', '?')}  ")
        lines.append(f"Fetched words: {output.get('fetched_word_count', '?')}  ")
        lines.append(f"Cleaned words: {output.get('cleaned_word_count', '?')}  ")
        lines.append("")
        if output.get("extraction"):
            ext = output["extraction"]
            lines.append(f"**Title:** {ext.get('title', '?')}  ")
            lines.append(f"**Summary:** {ext.get('one_line_summary', '?')}  ")
            lines.append(f"**Type:** {ext.get('content_type', '?')}  ")
        elif output.get("error"):
            lines.append(f"**Error:** {output['error']}")

    return "\n".join(lines)
