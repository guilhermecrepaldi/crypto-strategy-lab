# Windows: setup and daily `day-run`

This guide schedules an offline research campaign. It does not create a hypothesis or model
identity, call an LLM, open a browser, access a private account, or enable TESTNET/LIVE. The
runner is deliberately fail-closed: it only starts a pre-registered campaign and lets
`crypto-lab day-run` validate `CURRENT_STATE`, the frozen model identity, and the one-shot status.

## Fresh-machine setup

Open PowerShell and install Git and `uv` with WinGet:

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
```

Open a new PowerShell window, then install the Python version pinned by `.python-version`, clone
to a stable local path, and create the locked environment:

```powershell
uv python install 3.12
git clone --branch main --single-branch https://github.com/guilhermecrepaldi/crypto-strategy-lab.git C:\dev\crypto-strategy-lab
Set-Location C:\dev\crypto-strategy-lab
if ((git branch --show-current).Trim() -ne "main") { throw "Expected the main branch" }
uv sync --locked --all-groups
git --version
uv --version
uv run python --version
```

GPU acceleration is optional and is never an execution or accounting backend. If an NVIDIA driver
is already available and CUDA 13.x is suitable for the machine, install the optional extra and
check CuPy. If either step fails, retain the CPU environment and record the failure; CPU remains
the canonical backend.

```powershell
nvidia-smi
uv sync --locked --all-groups --extra gpu
uv run python -c "import cupy as cp; print('devices', cp.cuda.runtime.getDeviceCount())"
```

Run the normal local checks before any campaign. Keep a failure as evidence rather than changing
the command or relaxing an invariant. In particular, check the current research state for any
known baseline limitation before treating a full-project `mypy` result as a new regression.

```powershell
uv run pytest -m "not integration"
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run crypto-lab simulate-fixture --no-persist
```

## Prepare the day before enabling it

The scheduled task captures the date in **UTC** once, not local Windows time. It refuses to invoke
the CLI if that UTC date rolls over during preflight. Before the planned UTC date exists, create
and review all of these files under `campaigns/YYYY-MM-DD/`:

- `STRATEGY.md`
- `model_spec.json`
- `job.yaml`

Do not pre-create `RUN_STATUS.json`: `day-run` owns that evidence. A missing campaign or any
missing input makes `scripts/run-day.ps1` exit non-zero. A campaign which conflicts with
`docs/research/CURRENT_STATE.md`, is not approved, or has already been consumed must likewise be
rejected by `day-run`; neither PowerShell script attempts a retry or creates a substitute model.

## Frozen campaign contract

`campaigns/2026-10-14/` is a reviewed **draft**, not a command to enable: its M036 spec and the
authoritative state deliberately leave execution unauthorized. Do not run it merely to test the
scheduler, because the runner will preserve a `PREFLIGHT_REJECTED` status as evidence. Use the
offline test suite to validate installation instead.

Before an owner authorizes any copied campaign, freeze all of the following together:

- `STRATEGY.md` SHA-256 and the canonical `job.yaml` contract SHA-256 in `model_spec.json`;
- model-spec SHA-256 in `job.yaml`; `current_state_binding.next_campaign_model_hash` remains the
  literal `MODEL_SPEC_SHA256` to avoid a self-referential contract, while the authoritative
  `CURRENT_STATE.md` head records the final real spec hash;
- exactly matching authorized status and UTC window token in `job.yaml` and `CURRENT_STATE.md`;
- local tape SHA-256, manifest SHA-256, hash-bound source files, L2 snapshot/delta continuity,
  bounded L2 coverage (`max_l2_update_age_seconds`) at opening, between updates and at cutoff,
  and individual-trade binding with contiguous native IDs. Feed gaps, free-form risk halts and
  external cancellation lists are rejected because this v1 runner has no frozen causal policy for
  them. Each manifest source is a local
  `crypto-lab-day-raw-events-v1` normalized projection with `venue`, `symbol`, and parsed events;
  its L2 and individual-trade roles must reconstruct the tape event-for-event, not merely describe
  it in metadata;
- a hash-bound, `PROVEN_HISTORICAL` fee record and rule record for `BINANCE_SPOT/USDCUSDT`, each
  valid throughout the full UTC window and backed by local source bytes. The fee record binds the
  tier/context and side fee semantics; the rule record binds LIMIT_MAKER/GTC/post-only plus the
  price, lot, and notional filters. The legacy S0 adapter permits an authorized run only if the
  historical price tick and lot step are both equal to its one `step_size`. Each backing source is
  a hash-bound `IMMUTABLE_CAPTURE` using `crypto-lab-day-venue-evidence-capture-v1`; its
  `record_payload` must reproduce the fee or rule record byte-for-value (except the source list),
  so unrelated bytes cannot be labeled as fee/rule evidence; and
- the reviewed `main` commit recorded in the spec, with a clean runner source tree.

The runner rejects an output directory that already contains evidence, enforces strictly positive
**modeled** net exit edge in every fee scenario, and preserves a technical failure after the claim
as a failed one-shot run. It maps the existing S0 engine's legacy `usdc` cash field to quote
`USDT` and `fdusd` inventory field to base `USDC`; reports expose that mapping explicitly. A
terminal mark also requires a continuous, non-crossed L2 reconstruction no older than the
pre-registered `terminal_mark_max_age_seconds` at each frozen UTC cutoff. Any fee sweep not equal
to the proven historical rate must be pre-registered in the fee record and is reported as a
counterfactual sensitivity rather than an observed exchange fee. If a job uses multiple windows,
they must be exactly contiguous: the runner rejects a gap because the passive engine cannot carry
a modeled order or inventory state through an unobserved interval.

### Evidence limit of the current engine

`causal_cpu` is intentionally constrained to
`COUNTERFACTUAL_L2_QUEUE_ENVELOPE`. It replays the frozen event order and requires observed L2
depth at an order price, but the tape does not yet prove capture-arrival clock, historical private
latency, own time priority, order ACK, or a venue fill receipt. Consequently `SUMMARY.json`,
`AUDIT.json`, scenario evidence, and `RUN_STATUS.json` can report technical checks only and end in
`INCONCLUSIVE`; they never emit economic `PASS` or a physical-fill claim. Zero latency is a frozen
counterfactual assumption, not a historical measurement.

To support a future physical/economic evidence class, use a separately reviewed adapter built on
`ObservedL2Execution(clock_mode="CAPTURE_ARRIVAL")`, with hash-bound raw capture order, native
time precision/bounds, L2 coverage and the venue's own order/ACK/fill receipts. Do not reinterpret
the present `causal_cpu` artifacts as satisfying those requirements.

For a reviewed campaign, a manual invocation uses the exact same wrapper as Task Scheduler:

```powershell
Set-Location C:\dev\crypto-strategy-lab
$uvExe = (Get-Command uv -CommandType Application -ErrorAction Stop).Path
$gitExe = (Get-Command git -CommandType Application -ErrorAction Stop).Path
powershell.exe -NoProfile -File .\scripts\run-day.ps1 `
  -RepoRoot (Get-Location).Path -UvExe $uvExe -GitExe $gitExe -CampaignDate 2026-10-14
```

The wrapper runs the following command from the repository root and appends both output streams to
`campaigns/YYYY-MM-DD/runner.log`:

```powershell
uv run --locked --no-sync crypto-lab day-run --campaign campaigns/YYYY-MM-DD
```

`--locked --no-sync` is intentional: the scheduled task cannot resolve packages, update the lock,
or silently repair a missing environment. It also preflights that the local checkout is exactly on
`main` and records its local `HEAD`; a detached checkout or another branch is rejected. Re-run the
setup sync manually after an approved source or dependency update. The scripts do not bypass
PowerShell execution policy; if a managed Windows policy blocks a checked-out local script, resolve
that policy with the machine administrator rather than weakening it in the task definition.

## Register the task

The registration script uses absolute `uv.exe` and `git.exe` paths, requires the local checkout to
be on `main`, and sets the repository root as the Task Scheduler working directory. It creates a
task in the **disabled** state by default. Choose a local Windows time only after ensuring the
corresponding UTC campaign directory will have been frozen beforehand.

```powershell
Set-Location C:\dev\crypto-strategy-lab
powershell.exe -NoProfile -File .\scripts\register-day-run-task.ps1 `
  -At "06:15" -ExecutionTimeLimitMinutes 360
```

The task is named `CryptoStrategyLab-DayRun`. Verify its definition and leave it disabled until the
required campaign and authorization exist:

```powershell
Get-ScheduledTask -TaskName CryptoStrategyLab-DayRun | Format-List TaskName,State,Actions,Triggers
Get-ScheduledTaskInfo -TaskName CryptoStrategyLab-DayRun
```

Enable it explicitly only after that review:

```powershell
Enable-ScheduledTask -TaskName CryptoStrategyLab-DayRun
```

Re-running the registration script is idempotent and disables the task again unless `-Enable` is
passed. It refuses to replace a task that is currently running. The task uses `IgnoreNew` for
overlapping triggers and deliberately has no automatic retry or catch-up run: a duplicate or
late one-shot campaign needs review, not another invocation. Its explicit default time limit is
360 minutes; choose a larger bounded value before enabling only when the frozen protocol requires
it. A timeout may leave a preserved `RUN_STATUS.json` requiring review, never an automatic rerun.

The default logon type is `S4U`: it can run while the chosen Windows user is logged out without
putting a password in a script, task argument, or repository. S4U is deliberately local-only: it
cannot use network resources or encrypted user files. Pre-sync `uv` and stage all tapes/artifacts
locally before enabling it; a job that requires a download must fail instead of silently changing
its data source. If a signed-in session is explicitly preferred, register the task with
`-LogonType Interactive`; that is the only alternative supplied by this script.

```powershell
powershell.exe -NoProfile -File .\scripts\register-day-run-task.ps1 `
  -At "06:15" -LogonType Interactive -ExecutionTimeLimitMinutes 360
```

After a run, inspect the task result and the campaign-local log:

```powershell
Get-ScheduledTaskInfo -TaskName CryptoStrategyLab-DayRun
Get-Content .\campaigns\YYYY-MM-DD\runner.log -Tail 200
```
