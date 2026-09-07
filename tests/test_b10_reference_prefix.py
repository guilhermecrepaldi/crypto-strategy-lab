import io
import json
import runpy
from pathlib import Path

import numpy as np
import pytest

MODULE = runpy.run_path(str(Path(__file__).parents[1] / "scripts/index_b10_reference_prefix.py"))


def test_stream_cycle_exits_across_chunk_boundaries():
    cycles = [
        {"entry_event": 1, "exit_event": 409600},
        {"entry_event": 409601, "exit_event": 409602},
    ]
    source = json.dumps({"selection_changes": ["padding" * 100], "cycles": cycles, "tail": 0})
    assert list(MODULE["cycle_objects"](io.StringIO(source), chunk_size=7)) == cycles
    with pytest.raises(ValueError, match="TRUNCATED"):
        list(MODULE["cycle_objects"](io.StringIO(source[:-20]), chunk_size=7))


def test_same_timestamp_ordinal_is_inclusive_not_whole_timestamp():
    events = np.array([409599, 409600, 409602, 413696], dtype=np.int64)
    result = MODULE["count_prefix"](events, cutoff_event=409600)
    assert result["reference_cycles"] == 2
    result = MODULE["count_prefix"](events, cutoff_us=100)
    assert result["reference_cycles_before_timestamp"] == 1
    assert result["reference_cycles_through_timestamp"] == 3
