# Hold-risk diagnostic paused by owner scope change

On 2026-09-07 the owner prioritized RECOVERY_RESERVE for the unregistered M011 identity.
The published hold-risk protocol at `43ec99bb516e3f2ae9ce3900aad64ce3fdced0d0` remains
historical evidence, not a completed experiment or a reserved M011.

Verified Python PID 2932 ran `python.exe scripts/diagnose_hold_risk.py`, started at
2026-09-07 09:08:59 local time. It was stopped after command verification, with 237.19
CPU seconds consumed, while building indexes. No scientific results existed.
Status: `TERMINATED_BY_OWNER_SCOPE_CHANGE`. No checkpoint or source was deleted.

Preserved artifact identity:
`artifacts/usdcusdt/hold-risk-diagnostics/62828d021786d07696ae79d45d32d592795646089f095bc21e605c99e9c64d84/`.
It contains identity and parent event-ID audit only, no sealed causal snapshots or result.
Do not resume this paused study as part of Recovery Reserve.
