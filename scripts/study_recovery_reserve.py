"""Run the frozen 18-scenario v2 historical study, never register/promote a model."""

import json
import os
from pathlib import Path

from crypto_strategy_lab.microstructure.recovery_reserve_study import run_study

if __name__ == "__main__":
    lock_path = Path("artifacts/usdcusdt/recovery-reserve-study.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Kernel-owned advisory lock survives no crash: closing/death releases it automatically.
    # This lock is independent of M007 shadow and cannot interrupt it.
    with lock_path.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(run_study(), default=str, indent=2))
