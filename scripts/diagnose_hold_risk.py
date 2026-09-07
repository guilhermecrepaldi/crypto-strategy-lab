"""Run the preregistered offline M007 hold-risk diagnostic, never a model replay."""

import json

from crypto_strategy_lab.microstructure.hold_risk import run_diagnostic

if __name__ == "__main__":
    print(json.dumps(run_diagnostic(), indent=2, default=str))
