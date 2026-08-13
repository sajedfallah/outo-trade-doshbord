"""Central, secret-safe NEXUS configuration loading."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_config(path: str | Path | None = None, *, require_telegram: bool = False) -> dict:
    """Load non-secret JSON config and overlay local environment secrets.

    `.env` is deliberately optional and ignored by Git. Environment variables
    always win, allowing Windows/VPS service configuration without a file.
    """
    config_path = Path(path) if path else ROOT / "config.json"
    _load_dotenv(config_path.parent / ".env")
    with config_path.open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)
    token = os.getenv("NEXUS_TELEGRAM_BOT_TOKEN", "").strip()
    cfg.setdefault("telegram", {})["bot_token"] = token
    if require_telegram and not token:
        raise RuntimeError(
            "Telegram bot token is not configured. Set NEXUS_TELEGRAM_BOT_TOKEN "
            "in the environment or local .env file."
        )
    return cfg


def redacted_config(cfg: dict) -> dict:
    """Return a diagnostics-safe copy."""
    clone = json.loads(json.dumps(cfg, ensure_ascii=False, default=str))
    if "telegram" in clone:
        clone["telegram"]["bot_token"] = "***" if clone["telegram"].get("bot_token") else ""
    return clone
