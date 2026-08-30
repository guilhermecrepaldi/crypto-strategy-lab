from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from stable_baselines3 import DQN, PPO
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
    def __init__(self, algorithm: Literal["PPO", "DQN"] = "PPO") -> None:
        self.algorithm = algorithm

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
                "hyperparameters": hyperparameters,
            }
        )[:20]
        model_dir = artifact_dir / model_id
        return hyperparameters, model_id, model_dir, model_dir / "model.zip"

    def _hyperparameters(self) -> dict[str, Any]:
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
