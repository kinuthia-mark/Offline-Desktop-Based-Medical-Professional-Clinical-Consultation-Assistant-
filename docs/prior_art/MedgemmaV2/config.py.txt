"""Runtime configuration, read from environment variables (see README for the full table)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    whisper_model_path: str
    whisper_device: str
    whisper_compute_type: str
    llm_host: str
    llm_model: str
    llm_timeout_s: int
    inbox: Path
    outbox: Path
    injection_policy: str  # "quarantine" (default) or "flag"
    require_airgap: bool
    max_audio_seconds: int
    poll_interval_s: float
    use_nemo: bool
    nemo_config_dir: str

    @classmethod
    def from_env(cls) -> Settings:
        policy = os.getenv("AEGIS_INJECTION_POLICY", "quarantine").strip().lower()
        if policy not in {"quarantine", "flag"}:
            raise ValueError("AEGIS_INJECTION_POLICY must be 'quarantine' or 'flag'")
        return cls(
            whisper_model_path=os.getenv("AEGIS_WHISPER_MODEL_PATH", "/models/whisper-small"),
            whisper_device=os.getenv("AEGIS_WHISPER_DEVICE", "cpu"),
            whisper_compute_type=os.getenv("AEGIS_WHISPER_COMPUTE_TYPE", "int8"),
            llm_host=os.getenv("AEGIS_LLM_HOST", "http://127.0.0.1:11434"),
            llm_model=os.getenv("AEGIS_LLM_MODEL", "medgemma"),
            llm_timeout_s=int(os.getenv("AEGIS_LLM_TIMEOUT_S", "300")),
            inbox=Path(os.getenv("AEGIS_INBOX", "/data/inbox")),
            outbox=Path(os.getenv("AEGIS_OUTBOX", "/data/outbox")),
            injection_policy=policy,
            require_airgap=_bool("AEGIS_REQUIRE_AIRGAP", True),
            max_audio_seconds=int(os.getenv("AEGIS_MAX_AUDIO_SECONDS", "3600")),
            poll_interval_s=float(os.getenv("AEGIS_POLL_INTERVAL_S", "2")),
            use_nemo=_bool("AEGIS_USE_NEMO", False),
            nemo_config_dir=os.getenv("AEGIS_NEMO_CONFIG_DIR", "/app/config/guardrails"),
        )
