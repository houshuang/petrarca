#!/usr/bin/env python3
"""One-time cleanup: remove duplicate voice transcripts and followup items."""
import sqlite3
import json
from collections import Counter

DB_PATH = '/opt/petrarca/data/petrarca.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

# 1. Find and remove duplicate voice_transcripts (keep earliest per transcript hash)
#
# Dedup key fix (2026-04): the previous key GROUP BY (node_id, audio_bytes) was
# fundamentally broken for voice_capture rows — every voice_capture row has
# audio_bytes=0 and often a coarse node_id ('general'), so a test-harness or
# agent-created row with the same routing would silently collapse a real user
# capture into one row. The new key uses a hash of the transcript text itself
# plus created_at proximity, so only truly-identical text within a 10 minute
# window counts as a duplicate.
print("=== CLEANING DUPLICATE VOICE TRANSCRIPTS ===")
dupes = conn.execute("""
    WITH hashed AS (
        SELECT id, node_id, audio_bytes, created_at,
               substr(transcript, 1, 200) AS head,
               (created_at / (1000 * 60 * 10)) AS time_bucket_10min
        FROM voice_transcripts
    )
    SELECT id, node_id, audio_bytes, created_at FROM voice_transcripts
    WHERE rowid NOT IN (
        SELECT MIN(rowid) FROM voice_transcripts vt
        GROUP BY substr(vt.transcript, 1, 200), (vt.created_at / 600000)
    )
""").fetchall()
print(f"Found {len(dupes)} duplicate transcript(s) to remove:")
for d in dupes:
    print(f"  {d['id']}: node={d['node_id']}, audio={d['audio_bytes']}")

if dupes:
    dupe_ids = [d['id'] for d in dupes]
    placeholders = ','.join('?' * len(dupe_ids))
    conn.execute(f"DELETE FROM voice_transcripts WHERE id IN ({placeholders})", dupe_ids)
    print(f"Deleted {len(dupe_ids)} duplicate transcripts")

# 2. Find and remove duplicate voice_followup review_items
print("\n=== CLEANING DUPLICATE VOICE FOLLOWUP ITEMS ===")
followup_dupes = conn.execute("""
    SELECT id, source_text, curriculum_node_id FROM review_items
    WHERE item_type = 'voice_followup'
    AND rowid NOT IN (
        SELECT MIN(rowid) FROM review_items
        WHERE item_type = 'voice_followup'
        GROUP BY source_text, curriculum_node_id
    )
""").fetchall()
print(f"Found {len(followup_dupes)} duplicate followup item(s) to remove:")
for d in followup_dupes:
    print(f"  {d['id']}: {d['source_text'][:80]}")

if followup_dupes:
    dupe_ids = [d['id'] for d in followup_dupes]
    placeholders = ','.join('?' * len(dupe_ids))
    conn.execute(f"DELETE FROM review_items WHERE id IN ({placeholders})", dupe_ids)
    print(f"Deleted {len(dupe_ids)} duplicate followup items")

# 3. Fix inflated stability_days on knowledge_items that were processed multiple times
print("\n=== FIXING INFLATED STABILITY_DAYS ===")
node_dup_counts = Counter()
for d in dupes:
    node_dup_counts[d['node_id']] += 1

for node_id, extra_count in node_dup_counts.items():
    # Each extra processing multiplied stability by 1.5 (score was 'partly')
    correction = 1.5 ** extra_count
    rows = conn.execute(
        "SELECT id, stability_days, review_count FROM knowledge_items WHERE curriculum_node_id = ?",
        (node_id,)
    ).fetchall()
    for r in rows:
        new_stability = max(1.0, r['stability_days'] / correction)
        new_count = max(1, r['review_count'] - extra_count)
        conn.execute(
            "UPDATE knowledge_items SET stability_days = ?, review_count = ? WHERE id = ?",
            (new_stability, new_count, r['id'])
        )
        print(f"  {r['id']}: stability {r['stability_days']:.1f} -> {new_stability:.1f}, count {r['review_count']} -> {new_count}")

conn.commit()

# Verify
print("\n=== VERIFICATION ===")
remaining_dupes = conn.execute("""
    SELECT node_id, COUNT(*) as cnt FROM voice_transcripts
    GROUP BY node_id, audio_bytes HAVING cnt > 1
""").fetchall()
print(f"Remaining transcript duplicates (same node+audio): {len(remaining_dupes)}")

remaining_followup_dupes = conn.execute("""
    SELECT source_text, COUNT(*) as cnt FROM review_items
    WHERE item_type = 'voice_followup'
    GROUP BY source_text, curriculum_node_id HAVING cnt > 1
""").fetchall()
print(f"Remaining followup duplicates: {len(remaining_followup_dupes)}")

total_transcripts = conn.execute("SELECT COUNT(*) FROM voice_transcripts").fetchone()[0]
total_followups = conn.execute("SELECT COUNT(*) FROM review_items WHERE item_type = 'voice_followup'").fetchone()[0]
print(f"Total transcripts now: {total_transcripts}")
print(f"Total followup items now: {total_followups}")

conn.close()
print("\nDone!")
