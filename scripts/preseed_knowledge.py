#!/usr/bin/env python3
"""Pre-seed the knowledge model from Readwise reading history.

Reads items the user has meaningfully engaged with (reading_progress > 0.3),
extracts keywords from titles and summaries, matches against concept topics,
and outputs preseed-concepts.json for the app to load on fresh install.
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

READWISE_PATH = Path.home() / "src/otak/data/readwise_reader.json"
CONCEPTS_PATH = Path(__file__).parent.parent / "app/data/concepts.json"
OUTPUT_PATH = Path(__file__).parent.parent / "app/data/preseed-concepts.json"

MIN_READING_PROGRESS = 0.3


STOP_WORDS = {
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was',
    'were', 'been', 'being', 'have', 'has', 'had', 'not', 'but', 'its',
    'they', 'their', 'you', 'your', 'can', 'will', 'more', 'most',
    'about', 'into', 'over', 'also', 'just', 'how', 'what', 'when',
    'where', 'which', 'who', 'why', 'than', 'then', 'some', 'all',
    'new', 'one', 'two',
}


def tokenize(text: str) -> set[str]:
    """Extract lowercase tokens from text, splitting on non-alpha chars."""
    return {
        w for w in re.split(r'[^a-zA-Z]+', text.lower())
        if len(w) > 2 and w not in STOP_WORDS
    }


def topic_to_keywords(topic: str) -> set[str]:
    """Convert a hyphenated topic like 'classical-philology' to keyword set."""
    return {
        w for w in topic.split('-')
        if len(w) > 2 and w not in STOP_WORDS
    }


def build_topic_keyword_index(concepts: list[dict]) -> dict[str, set[str]]:
    """Map each unique topic to its keyword set."""
    topics = {}
    for c in concepts:
        t = c['topic']
        if t not in topics:
            topics[t] = topic_to_keywords(t)
    return topics


def extract_item_keywords(item: dict) -> set[str]:
    """Extract keywords from a Readwise item's title and summary."""
    parts = []
    if item.get('title'):
        parts.append(item['title'])
    if item.get('summary'):
        parts.append(item['summary'])
    if item.get('site_name'):
        parts.append(item['site_name'])
    return tokenize(' '.join(parts))


def main():
    # Load data
    with open(READWISE_PATH) as f:
        readwise_items = json.load(f)
    with open(CONCEPTS_PATH) as f:
        concepts = json.load(f)

    print(f"Loaded {len(readwise_items)} Readwise items, {len(concepts)} concepts")

    # Filter to engaged items
    engaged = [
        item for item in readwise_items
        if (item.get('reading_progress') or 0) > MIN_READING_PROGRESS
    ]
    print(f"Engaged items (reading_progress > {MIN_READING_PROGRESS}): {len(engaged)}")

    # Build topic keyword index
    topic_keywords = build_topic_keyword_index(concepts)
    print(f"Unique topics: {len(topic_keywords)}")

    # For each engaged item, find which topics match
    topic_match_counts: Counter[str] = Counter()
    for item in engaged:
        item_kw = extract_item_keywords(item)
        for topic, topic_kw in topic_keywords.items():
            if len(topic_kw) == 0:
                continue
            overlap = topic_kw & item_kw
            if len(topic_kw) == 1:
                # Single-keyword topics: require the word to appear
                if overlap:
                    topic_match_counts[topic] += 1
            else:
                # Multi-keyword topics: require ALL keywords to appear
                # (these are already short — e.g. "classical philology" is 2 words)
                if len(overlap) == len(topic_kw):
                    topic_match_counts[topic] += 1

    print(f"\nTopics matched (at least 1 engaged item):")
    for topic, count in topic_match_counts.most_common():
        print(f"  {topic}: {count} items")

    # Mark concepts as "encountered" if their topic was matched by engaged reading
    matched_topics = set(topic_match_counts.keys())
    preseed = []
    for c in concepts:
        if c['topic'] in matched_topics:
            preseed.append({
                "concept_id": c['id'],
                "state": "encountered",
                "match_count": topic_match_counts[c['topic']],
            })

    print(f"\nTotal concepts to preseed: {len(preseed)} / {len(concepts)}")

    # Write output
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(preseed, f, indent=2)
    print(f"Written to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
