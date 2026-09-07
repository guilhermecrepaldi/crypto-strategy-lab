"""Index immutable B10 cycle exits for same-causal-prefix productivity denominators.

This extracts existing evidence; it does not replay or identify survivor cohorts.
"""

import argparse
import gzip
import hashlib
import json
import re
from array import array
from pathlib import Path

import numpy as np

SOURCE_SHA = "2b08d28152b27000120f6c503838ff1c8ed7da12c33d34892826c41c3da98e51"
EXPECTED_COUNT = 3580880
SCALE = 4096


def cycle_objects(stream, chunk_size=1024 * 1024):
    """Stream the canonical top-level cycles array without loading the whole replay."""
    marker = re.compile(r'"cycles"\s*:\s*\[')
    buffer = ""
    while True:
        block = stream.read(chunk_size)
        if not block:
            raise ValueError("REFERENCE_CYCLES_ARRAY_MISSING")
        buffer += block
        match = marker.search(buffer)
        if match:
            buffer = buffer[match.end() :]
            break
        buffer = buffer[-64:]
    decoder = json.JSONDecoder()
    while True:
        buffer = buffer.lstrip()
        if buffer.startswith("]"):
            return
        if buffer.startswith(","):
            buffer = buffer[1:].lstrip()
        try:
            item, end = decoder.raw_decode(buffer)
        except json.JSONDecodeError:
            block = stream.read(chunk_size)
            if not block:
                raise ValueError("TRUNCATED_REFERENCE_CYCLES") from None
            buffer += block
            continue
        if not isinstance(item, dict) or "exit_event" not in item or "entry_event" not in item:
            raise ValueError("REFERENCE_CYCLE_SCHEMA_MISMATCH")
        yield item
        buffer = buffer[end:]


def count_prefix(events, *, cutoff_event=None, cutoff_us=None):
    if (cutoff_event is None) == (cutoff_us is None):
        raise ValueError("CHOOSE_EXACT_EVENT_OR_TIMESTAMP")
    if cutoff_event is not None:
        return {
            "cutoff_event": cutoff_event,
            "reference_cycles": int(np.searchsorted(events, cutoff_event, side="right")),
            "cutoff_semantics": "INCLUSIVE_CANONICAL_EVENT",
        }
    return {
        "cutoff_us": cutoff_us,
        "reference_cycles_before_timestamp": int(np.searchsorted(events, cutoff_us * SCALE)),
        "reference_cycles_through_timestamp": int(np.searchsorted(events, (cutoff_us + 1) * SCALE)),
        "cutoff_semantics": "ORDINAL_UNKNOWN; bounds, not an exact same-event denominator",
    }


def build(source, output):
    with source.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    if source_sha != SOURCE_SHA:
        raise ValueError("FROZEN_REFERENCE_SHA_MISMATCH")
    exits = array("q")
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        for cycle in cycle_objects(stream):
            event = cycle["exit_event"]
            if exits and event <= exits[-1]:
                raise ValueError("REFERENCE_EXITS_NOT_STRICTLY_ORDERED")
            exits.append(event)
    if len(exits) != EXPECTED_COUNT:
        raise ValueError("REFERENCE_CYCLE_COUNT_MISMATCH")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("REFUSE_TO_OVERWRITE_EXISTING_REFERENCE_INDEX")
    np.save(output, np.asarray(exits, dtype="<i8"), allow_pickle=False)
    with output.open("rb") as stream:
        index_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    metadata = {
        "source": str(source),
        "source_sha256": source_sha,
        "index": str(output),
        "index_sha256": index_sha,
        "count": len(exits),
        "first_exit_event": exits[0],
        "last_exit_event": exits[-1],
        "event_order_scale": SCALE,
        "semantics": "Original completed ordinary cycle exits; no survivor mapping; no rerun",
    }
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--cutoff-event", type=int)
    parser.add_argument("--cutoff-us", type=int)
    args = parser.parse_args()
    if args.source:
        print(json.dumps(build(args.source, args.index), indent=2))
    if args.cutoff_event is not None or args.cutoff_us is not None:
        print(
            json.dumps(
                count_prefix(
                    np.load(args.index, mmap_mode="r", allow_pickle=False),
                    cutoff_event=args.cutoff_event,
                    cutoff_us=args.cutoff_us,
                ),
                indent=2,
            )
        )
