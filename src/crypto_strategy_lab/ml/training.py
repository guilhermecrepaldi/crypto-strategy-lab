from __future__ import annotations

import base64
import hashlib
import json
import pickle
import random
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import torch
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_checker import check_env

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.ml.environment import CryptoRotationEnv


@dataclass(frozen=True)
class TrainingArtifact:
    algorithm: str
    seed: int
    total_timesteps: int
    checkpoint_path: Path
    checkpoint_hash: str
    model_id: str
    dataset_hash: str
    hyperparameters: dict[str, Any]
    model: Any
    reused: bool = False


class RLTrainer(Protocol):
    def train(
        self,
        env: CryptoRotationEnv,
        *,
        total_timesteps: int,
        seed: int,
        artifact_dir: Path,
    ) -> TrainingArtifact: ...


class StableBaselinesTrainer:
    def __init__(
        self,
        algorithm: Literal["PPO", "DQN"] = "PPO",
        *,
        profile: Literal["smoke", "controlled"] = "smoke",
    ) -> None:
        self.algorithm = algorithm
        self.profile = profile

    def train(
        self,
        env: CryptoRotationEnv,
        *,
        total_timesteps: int,
        seed: int,
        artifact_dir: Path,
    ) -> TrainingArtifact:
        if total_timesteps <= 0:
            raise ValueError("total_timesteps must be positive")
        check_env(env, warn=True, skip_render_check=True)
        hyperparameters, model_id, model_dir, checkpoint = self._identity(
            env, total_timesteps, seed, artifact_dir
        )
        metadata = model_dir / "metadata.json"
        if checkpoint.exists() and metadata.exists():
            model = self._load(checkpoint, env)
            return TrainingArtifact(
                self.algorithm,
                seed,
                total_timesteps,
                checkpoint,
                _sha256(checkpoint),
                model_id,
                env.dataset_hash,
                hyperparameters,
                model,
                reused=True,
            )
        model_dir.mkdir(parents=True, exist_ok=False)
        model = self._build(env, seed, hyperparameters)
        model.learn(total_timesteps=total_timesteps, progress_bar=False)
        model.save(checkpoint)
        checkpoint_hash = _sha256(checkpoint)
        metadata.write_text(
            json.dumps(
                {
                    "model_id": model_id,
                    "algorithm": self.algorithm,
                    "seed": seed,
                    "total_timesteps": total_timesteps,
                    "dataset_hash": env.dataset_hash,
                    "partition": env.partition.model_dump(mode="json"),
                    "environment": env.configuration_manifest(),
                    "hyperparameters": hyperparameters,
                    "checkpoint_hash": checkpoint_hash,
                    "status": "TRAINED",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingArtifact(
            self.algorithm,
            seed,
            total_timesteps,
            checkpoint,
            checkpoint_hash,
            model_id,
            env.dataset_hash,
            hyperparameters,
            model,
        )

    def load_existing(
        self,
        env: CryptoRotationEnv,
        *,
        total_timesteps: int,
        seed: int,
        artifact_dir: Path,
    ) -> TrainingArtifact:
        hyperparameters, model_id, _model_dir, checkpoint = self._identity(
            env, total_timesteps, seed, artifact_dir
        )
        metadata = checkpoint.parent / "metadata.json"
        if not checkpoint.exists() or not metadata.exists():
            raise FileNotFoundError(
                f"checkpoint {model_id} does not exist; run rl-train with the same configuration"
            )
        return TrainingArtifact(
            self.algorithm,
            seed,
            total_timesteps,
            checkpoint,
            _sha256(checkpoint),
            model_id,
            env.dataset_hash,
            hyperparameters,
            self._load(checkpoint, env),
            reused=True,
        )

    def _identity(
        self,
        env: CryptoRotationEnv,
        total_timesteps: int,
        seed: int,
        artifact_dir: Path,
    ) -> tuple[dict[str, Any], str, Path, Path]:
        if total_timesteps <= 0:
            raise ValueError("total_timesteps must be positive")
        hyperparameters = self._hyperparameters()
        model_id = canonical_hash(
            {
                "algorithm": self.algorithm,
                "seed": seed,
                "total_timesteps": total_timesteps,
                "dataset_hash": env.dataset_hash,
                "partition": env.partition.model_dump(mode="json"),
                "environment": env.configuration_manifest(),
                "hyperparameters": hyperparameters,
            }
        )[:20]
        model_dir = artifact_dir / model_id
        return hyperparameters, model_id, model_dir, model_dir / "model.zip"

    def _hyperparameters(self) -> dict[str, Any]:
        if self.profile == "controlled":
            if self.algorithm == "PPO":
                return {
                    "learning_rate": 0.0003,
                    "n_steps": 500,
                    "batch_size": 100,
                    "n_epochs": 5,
                    "gamma": 0.99,
                    "gae_lambda": 0.95,
                    "ent_coef": 0.001,
                }
            return {
                "learning_rate": 0.0001,
                "buffer_size": 100_000,
                "learning_starts": 1_000,
                "batch_size": 64,
                "train_freq": 4,
                "gradient_steps": 1,
                "target_update_interval": 1_000,
                "exploration_fraction": 0.20,
                "exploration_final_eps": 0.05,
            }
        if self.algorithm == "PPO":
            return {
                "learning_rate": 0.0003,
                "n_steps": 8,
                "batch_size": 8,
                "n_epochs": 2,
                "gamma": 0.99,
            }
        return {
            "learning_rate": 0.0001,
            "buffer_size": 256,
            "learning_starts": 8,
            "batch_size": 8,
            "train_freq": 1,
            "gradient_steps": 1,
        }

    def _build(self, env: CryptoRotationEnv, seed: int, hyperparameters: dict[str, Any]) -> Any:
        algorithm = PPO if self.algorithm == "PPO" else DQN
        return algorithm(
            "MlpPolicy",
            env,
            seed=seed,
            verbose=0,
            device="cpu",
            policy_kwargs={"net_arch": [32, 32]},
            **hyperparameters,
        )

    def _load(self, path: Path, env: CryptoRotationEnv) -> Any:
        algorithm = PPO if self.algorithm == "PPO" else DQN
        return algorithm.load(path, env=env, device="cpu")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class CurriculumStage:
    name: str
    duration_days: int
    starts_at_step: int


CONTROLLED_CURRICULUM = (
    CurriculumStage("STAGE_1_EXECUTION", 30, 0),
    CurriculumStage("STAGE_2_TRENDS", 60, 25_000),
    CurriculumStage("STAGE_3_STABILITY", 90, 60_000),
)


@dataclass(frozen=True)
class ControlledTrainingResult:
    run_id: str
    configuration_hash: str
    algorithm: str
    seed: int
    requested_timesteps: int
    completed_timesteps: int
    status: str
    artifact_dir: Path
    latest_checkpoint: Path
    checkpoint_hash: str
    elapsed_seconds: float
    steps_per_second: float
    peak_python_memory_mb: float
    resumed: bool
    checkpoint_records: list[dict[str, Any]]
    training_metrics: list[dict[str, Any]]
    internal_evaluations: list[dict[str, Any]]
    model: Any


class TrainingTelemetryCallback(BaseCallback):
    def __init__(self, *, deadline: float | None = None) -> None:
        super().__init__(verbose=0)
        self.deadline = deadline
        self.action_counts = [0, 0, 0, 0, 0]
        self.ruin_count = 0
        self.episode_count = 0
        self.turnover = Decimal("0")
        self.costs = Decimal("0")
        self.reward_total = 0.0
        self.reward_count = 0
        self.metrics: list[dict[str, Any]] = []

    def _on_step(self) -> bool:
        actions = np.asarray(self.locals.get("actions", []), dtype=np.int64).reshape(-1)
        for action in actions:
            if 0 <= int(action) < 5:
                self.action_counts[int(action)] += 1
        infos = self.locals.get("infos", [])
        dones = np.asarray(self.locals.get("dones", []), dtype=bool).reshape(-1)
        rewards = np.asarray(self.locals.get("rewards", []), dtype=np.float64).reshape(-1)
        self.reward_total += float(np.sum(rewards))
        self.reward_count += int(rewards.size)
        for index, info in enumerate(infos):
            self.turnover += Decimal(str(info.get("turnover", "0")))
            self.costs += Decimal(str(info.get("costs_usdt", "0")))
            if index < len(dones) and dones[index]:
                self.episode_count += 1
                self.ruin_count += info.get("termination_reason") == "RUIN"
        if self.n_calls % 1_000 == 0:
            logger_values = getattr(self.model.logger, "name_to_value", {})
            self.metrics.append(
                {
                    "step": int(self.model.num_timesteps),
                    "reward_mean": (
                        self.reward_total / self.reward_count if self.reward_count else None
                    ),
                    "episode_length_mean": _number(logger_values.get("rollout/ep_len_mean")),
                    "entropy_loss": _number(logger_values.get("train/entropy_loss")),
                    "value_loss": _number(logger_values.get("train/value_loss")),
                    "policy_loss": _number(logger_values.get("train/policy_gradient_loss")),
                    "td_loss": _number(logger_values.get("train/loss")),
                    "epsilon": _number(logger_values.get("rollout/exploration_rate")),
                    "action_counts": self.action_counts.copy(),
                    "turnover": str(self.turnover),
                    "costs_usdt": str(self.costs),
                    "episodes": self.episode_count,
                    "ruins": self.ruin_count,
                }
            )
        return self.deadline is None or time.monotonic() < self.deadline


class ResumableCurriculumTrainer:
    """Canonical long-running trainer with deterministic local checkpoints."""

    def __init__(self, algorithm: Literal["PPO", "DQN"]) -> None:
        self.algorithm = algorithm
        self.base = StableBaselinesTrainer(algorithm, profile="controlled")

    def train_to_target(
        self,
        *,
        env_factory: Callable[[int], CryptoRotationEnv],
        internal_evaluator: Callable[[Any, int], dict[str, Any] | None],
        dataset_hash: str,
        feature_manifest: dict[str, Any],
        controls_manifest: dict[str, Any],
        seed: int,
        target_timesteps: int,
        artifact_root: Path,
        checkpoint_interval: int = 10_000,
        max_seconds: int | None = None,
    ) -> ControlledTrainingResult:
        if target_timesteps <= 0 or checkpoint_interval <= 0:
            raise ValueError("training target and checkpoint interval must be positive")
        hyperparameters = self.base._hyperparameters()
        identity = {
            "schema_version": "controlled-training-v1",
            "algorithm": self.algorithm,
            "seed": seed,
            "dataset_hash": dataset_hash,
            "features": feature_manifest,
            "controls": controls_manifest,
            "hyperparameters": hyperparameters,
            "curriculum": [item.__dict__ for item in CONTROLLED_CURRICULUM],
        }
        configuration_hash = canonical_hash(identity)
        run_id = configuration_hash[:20]
        run_dir = artifact_root / run_id
        state_path = run_dir / "training-state.json"
        latest_path = run_dir / "latest.zip"
        run_dir.mkdir(parents=True, exist_ok=True)
        state = _load_state(state_path)
        state.setdefault("configuration_hash", configuration_hash)
        completed = int(state.get("completed_timesteps", 0))
        resumed = completed > 0
        if completed >= target_timesteps and latest_path.exists():
            view, selected_path = _target_view(state, target_timesteps, latest_path)
            env = env_factory(_stage_for_step(target_timesteps - 1).duration_days)
            model = self.base._load(selected_path, env)
            return _controlled_result(
                view,
                model=model,
                run_dir=run_dir,
                latest_path=selected_path,
                resumed=True,
            )

        stage = _stage_for_step(completed)
        env = env_factory(stage.duration_days)
        check_env(env, warn=True, skip_render_check=True)
        if latest_path.exists() and state:
            model = self.base._load(latest_path, env)
            replay_path = run_dir / "replay-buffer.pkl"
            if self.algorithm == "DQN" and replay_path.exists():
                model.load_replay_buffer(replay_path)
            _restore_rng(state.get("rng_state", {}), env)
        else:
            model = self.base._build(env, seed, hyperparameters)
            state = {
                **identity,
                "run_id": run_id,
                "configuration_hash": configuration_hash,
                "status": "RUNNING",
                "completed_timesteps": 0,
                "elapsed_seconds": 0.0,
                "peak_python_memory_mb": 0.0,
                "checkpoint_records": [],
                "training_metrics": [],
                "internal_evaluations": [],
            }
        started = time.monotonic()
        prior_elapsed = float(state.get("elapsed_seconds", 0.0))
        tracemalloc.start()
        while completed < target_timesteps:
            elapsed_now = time.monotonic() - started
            if max_seconds is not None and elapsed_now >= max_seconds:
                break
            stage = _stage_for_step(completed)
            stage_end = _next_stage_boundary(completed, target_timesteps)
            next_checkpoint = min(
                ((completed // checkpoint_interval) + 1) * checkpoint_interval,
                target_timesteps,
                stage_end,
            )
            env = env_factory(stage.duration_days)
            model.set_env(env)
            callback = TrainingTelemetryCallback(
                deadline=started + max_seconds if max_seconds is not None else None
            )
            chunk = next_checkpoint - completed
            model.learn(
                total_timesteps=chunk,
                reset_num_timesteps=False,
                progress_bar=False,
                callback=callback,
            )
            completed = int(model.num_timesteps)
            model.save(latest_path)
            if self.algorithm == "DQN":
                model.save_replay_buffer(run_dir / "replay-buffer.pkl")
            checkpoint_path = run_dir / f"checkpoint-{completed:09d}.zip"
            model.save(checkpoint_path)
            checkpoint_hash = _sha256(checkpoint_path)
            evaluation = internal_evaluator(model, completed) if completed <= 60_000 else None
            state["checkpoint_records"].append(
                {
                    "step": completed,
                    "stage": stage.name,
                    "duration_days": stage.duration_days,
                    "path": str(checkpoint_path),
                    "sha256": checkpoint_hash,
                    "internal_train_evaluation": evaluation is not None,
                    "elapsed_seconds": prior_elapsed + time.monotonic() - started,
                    "peak_python_memory_mb": tracemalloc.get_traced_memory()[1] / 1024 / 1024,
                }
            )
            state["training_metrics"].extend(callback.metrics)
            if evaluation is not None:
                state["internal_evaluations"].append(evaluation)
            _save_progress(
                state,
                state_path=state_path,
                env=env,
                completed=completed,
                target=target_timesteps,
                elapsed=prior_elapsed + time.monotonic() - started,
                peak_mb=tracemalloc.get_traced_memory()[1] / 1024 / 1024,
                latest_path=latest_path,
            )
        peak_mb = tracemalloc.get_traced_memory()[1] / 1024 / 1024
        tracemalloc.stop()
        elapsed = prior_elapsed + time.monotonic() - started
        state["status"] = "COMPLETED" if completed >= target_timesteps else "TIME_LIMIT"
        _save_progress(
            state,
            state_path=state_path,
            env=env,
            completed=completed,
            target=target_timesteps,
            elapsed=elapsed,
            peak_mb=peak_mb,
            latest_path=latest_path,
        )
        return _controlled_result(
            state, model=model, run_dir=run_dir, latest_path=latest_path, resumed=resumed
        )


def _stage_for_step(step: int) -> CurriculumStage:
    return next(stage for stage in reversed(CONTROLLED_CURRICULUM) if step >= stage.starts_at_step)


def _next_stage_boundary(step: int, target: int) -> int:
    boundaries = [
        item.starts_at_step for item in CONTROLLED_CURRICULUM if item.starts_at_step > step
    ]
    return min([target, *boundaries])


def _save_progress(
    state: dict[str, Any],
    *,
    state_path: Path,
    env: CryptoRotationEnv,
    completed: int,
    target: int,
    elapsed: float,
    peak_mb: float,
    latest_path: Path,
) -> None:
    state.update(
        {
            "completed_timesteps": completed,
            "requested_timesteps": target,
            "elapsed_seconds": elapsed,
            "steps_per_second": completed / elapsed if elapsed else 0.0,
            "peak_python_memory_mb": max(float(state.get("peak_python_memory_mb", 0)), peak_mb),
            "latest_checkpoint": str(latest_path),
            "latest_checkpoint_hash": _sha256(latest_path),
            "rng_state": _capture_rng(env),
            "updated_at": datetime.now().astimezone().isoformat(),
        }
    )
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def _controlled_result(
    state: dict[str, Any],
    *,
    model: Any,
    run_dir: Path,
    latest_path: Path,
    resumed: bool,
) -> ControlledTrainingResult:
    return ControlledTrainingResult(
        run_id=str(state["run_id"]),
        configuration_hash=str(state["configuration_hash"]),
        algorithm=str(state["algorithm"]),
        seed=int(state["seed"]),
        requested_timesteps=int(state["requested_timesteps"]),
        completed_timesteps=int(state["completed_timesteps"]),
        status=str(state["status"]),
        artifact_dir=run_dir,
        latest_checkpoint=latest_path,
        checkpoint_hash=str(state["latest_checkpoint_hash"]),
        elapsed_seconds=float(state["elapsed_seconds"]),
        steps_per_second=float(state["steps_per_second"]),
        peak_python_memory_mb=float(state["peak_python_memory_mb"]),
        resumed=resumed,
        checkpoint_records=list(state["checkpoint_records"]),
        training_metrics=list(state["training_metrics"]),
        internal_evaluations=list(state["internal_evaluations"]),
        model=model,
    )


def _target_view(
    state: dict[str, Any], target: int, default_checkpoint: Path
) -> tuple[dict[str, Any], Path]:
    if int(state.get("completed_timesteps", 0)) == target:
        return state, default_checkpoint
    records = [item for item in state.get("checkpoint_records", []) if int(item["step"]) <= target]
    exact = next((item for item in reversed(records) if int(item["step"]) == target), None)
    if exact is None:
        return state, default_checkpoint
    elapsed = float(
        exact.get(
            "elapsed_seconds",
            float(state.get("elapsed_seconds", 0))
            * target
            / max(int(state.get("completed_timesteps", target)), 1),
        )
    )
    view = {
        **state,
        "requested_timesteps": target,
        "completed_timesteps": target,
        "status": "COMPLETED",
        "latest_checkpoint": str(exact["path"]),
        "latest_checkpoint_hash": str(exact["sha256"]),
        "checkpoint_records": records,
        "elapsed_seconds": elapsed,
        "steps_per_second": target / elapsed if elapsed else 0.0,
        "peak_python_memory_mb": float(
            exact.get("peak_python_memory_mb", state.get("peak_python_memory_mb", 0))
        ),
        "training_metrics": [
            item for item in state.get("training_metrics", []) if int(item["step"]) <= target
        ],
        "internal_evaluations": [
            item
            for item in state.get("internal_evaluations", [])
            if int(item["checkpoint_step"]) <= target
        ],
    }
    return view, Path(str(exact["path"]))


def _capture_rng(env: CryptoRotationEnv) -> dict[str, str]:
    values = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "environment": env.np_random.bit_generator.state,
    }
    return {
        key: base64.b64encode(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)).decode()
        for key, value in values.items()
    }


def _restore_rng(payload: dict[str, str], env: CryptoRotationEnv) -> None:
    if not payload:
        return
    values = {key: pickle.loads(base64.b64decode(value)) for key, value in payload.items()}
    random.setstate(values["python"])
    np.random.set_state(values["numpy"])
    torch.set_rng_state(values["torch"])
    env.np_random.bit_generator.state = values["environment"]


def _load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    array = np.asarray(value)
    return float(array.reshape(-1)[0])
