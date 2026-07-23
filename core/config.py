"""Configurazione centralizzata di GamesTracker.

Carica le variabili da ``config/.env`` (via python-dotenv) e le espone
tramite un oggetto ``Settings`` tipizzato con default sensati.

Principio: l'import di questo modulo NON deve mai fallire per una key
mancante. Le API key delle sorgenti sono opzionali a livello di config;
la validazione avviene solo quando una sorgente che le richiede viene
effettivamente usata, tramite ``require_*()``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# --- Percorsi di progetto -------------------------------------------------
# core/config.py -> core/ -> radice progetto
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_DIR: Path = PROJECT_ROOT / "config"
DATA_DIR: Path = PROJECT_ROOT / "data"
ENV_FILE: Path = CONFIG_DIR / ".env"

# DB SQLite di default dentro data/
DEFAULT_DB_URL = f"sqlite:///{(DATA_DIR / 'gamestracker.db').as_posix()}"


def _get_bool(name: str, default: bool) -> bool:
    """Legge una variabile d'ambiente booleana (1/true/yes/on)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    """Legge un float dall'ambiente, tornando al default se non valido."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    """Legge un int dall'ambiente, tornando al default se non valido."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str) -> str:
    """Legge una stringa dall'ambiente; una variabile presente ma vuota
    (es. ``DB_URL=``) torna al default invece di restituire stringa vuota."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw


class MissingConfigError(RuntimeError):
    """Sollevata quando una sorgente richiede una key non configurata."""


@dataclass
class Settings:
    """Impostazioni applicative caricate dall'ambiente.

    Le API key sono opzionali (stringa vuota se assenti). Usa i metodi
    ``require_*`` prima di chiamare una sorgente che le richiede.
    """

    # Database
    db_url: str = DEFAULT_DB_URL

    # Lingua UI/report di default (it | en)
    app_lang: str = "it"

    # Analisi
    quality_score_threshold: float = 40.0

    # Collector / scheduler (ore)
    discovery_interval_hours: int = 6

    # HTTP
    http_user_agent: str = "GamesTracker/0.1 (+https://github.com/gamestracker)"

    # --- API keys (opzionali finche' non servono) ---
    steam_web_api_key: str = ""
    youtube_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = ""

    # Percorsi utili esposti come campi (non da .env)
    project_root: Path = field(default=PROJECT_ROOT)
    data_dir: Path = field(default=DATA_DIR)

    # --- Validatori on-demand -------------------------------------------
    def require_steam_web_api_key(self) -> str:
        """Ritorna la Steam Web API key o solleva ``MissingConfigError``."""
        if not self.steam_web_api_key:
            raise MissingConfigError(
                "STEAM_WEB_API_KEY non configurata in config/.env"
            )
        return self.steam_web_api_key

    def require_youtube_api_key(self) -> str:
        """Ritorna la YouTube Data API key o solleva ``MissingConfigError``."""
        if not self.youtube_api_key:
            raise MissingConfigError(
                "YOUTUBE_API_KEY non configurata in config/.env"
            )
        return self.youtube_api_key

    def require_reddit_credentials(self) -> tuple[str, str, str]:
        """Ritorna (client_id, client_secret, user_agent) per Reddit/PRAW.

        Solleva ``MissingConfigError`` se una delle tre manca.
        """
        missing = [
            name
            for name, val in (
                ("REDDIT_CLIENT_ID", self.reddit_client_id),
                ("REDDIT_CLIENT_SECRET", self.reddit_client_secret),
                ("REDDIT_USER_AGENT", self.reddit_user_agent),
            )
            if not val
        ]
        if missing:
            raise MissingConfigError(
                "Credenziali Reddit mancanti in config/.env: "
                + ", ".join(missing)
            )
        return (
            self.reddit_client_id,
            self.reddit_client_secret,
            self.reddit_user_agent,
        )


def load_settings(env_file: Path | str | None = None) -> Settings:
    """Carica le impostazioni dall'ambiente e da ``config/.env``.

    Le variabili gia' presenti nell'ambiente hanno precedenza sul file
    (``override=False``), utile per test e deployment. Non fallisce mai
    se il file .env non esiste.
    """
    path = Path(env_file) if env_file is not None else ENV_FILE
    if path.exists():
        load_dotenv(path, override=False)

    return Settings(
        db_url=_get_str("DB_URL", DEFAULT_DB_URL),
        app_lang=_get_str("APP_LANG", "it"),
        quality_score_threshold=_get_float("QUALITY_SCORE_THRESHOLD", 40.0),
        discovery_interval_hours=_get_int("DISCOVERY_INTERVAL_HOURS", 6),
        http_user_agent=os.getenv(
            "HTTP_USER_AGENT",
            "GamesTracker/0.1 (+https://github.com/gamestracker)",
        ),
        steam_web_api_key=os.getenv("STEAM_WEB_API_KEY", ""),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
        reddit_client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        reddit_user_agent=os.getenv("REDDIT_USER_AGENT", ""),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Restituisce l'istanza singleton di ``Settings`` (cache-ata)."""
    return load_settings()
