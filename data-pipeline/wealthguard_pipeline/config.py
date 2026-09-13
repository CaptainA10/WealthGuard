"""Centralised configuration -- every value is read from the environment.

Cahier des charges §7: no secret (password, API key) may be hardcoded, including
in local development. This module is the *only* place that reads ``os.environ``,
so a code review only has to audit one file.

Naming convention: the PostgreSQL and Blob Storage variables use the names that
Azure App Service / Azure Functions inject automatically when a service
connector is attached (``AZURE_POSTGRESQL_*``, ``AZURE_STORAGE_*``). The same
code therefore runs unchanged against the local Docker Postgres of
``docker-compose.yml`` and against Azure Database for PostgreSQL -- only the
values differ. See ARCHITECTURE.md §"Configuration et secrets".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

# Repository root = two levels above this file (data-pipeline/wealthguard_pipeline/).
REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(RuntimeError):
    """Raised when a mandatory environment variable is missing or malformed."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Environment variable {name} is required but not set. "
            f"Copy .env.example to .env and fill it in, or export it in your shell."
        )
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Environment variable {name}={raw!r} is not an integer") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "require"}:
        return True
    if raw in {"0", "false", "no", "off", "disable"}:
        return False
    raise ConfigError(f"Environment variable {name}={raw!r} is not a boolean")


@dataclass(frozen=True)
class DatabaseConfig:
    """Connection settings for PostgreSQL (local Docker or Azure managed)."""

    host: str
    port: int
    database: str
    user: str
    password: str
    require_ssl: bool
    schema: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=_optional("AZURE_POSTGRESQL_HOST", "localhost"),
            port=_int("AZURE_POSTGRESQL_PORT", 5432),
            database=_optional("AZURE_POSTGRESQL_DATABASE", "wealthguard"),
            user=_require("AZURE_POSTGRESQL_USER"),
            password=_require("AZURE_POSTGRESQL_PASSWORD"),
            # Azure Database for PostgreSQL enforces TLS; the local container does not.
            require_ssl=_bool("AZURE_POSTGRESQL_SSL", False),
            schema=_optional("WG_DB_SCHEMA", "wealthguard"),
        )

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy URL. The password is percent-encoded, never logged."""
        auth = f"{quote_plus(self.user)}:{quote_plus(self.password)}"
        url = f"postgresql+psycopg://{auth}@{self.host}:{self.port}/{self.database}"
        if self.require_ssl:
            url += "?sslmode=require"
        return url

    def safe_repr(self) -> str:
        """Loggable description: host/db/user only, never the password."""
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.database} (ssl={self.require_ssl})"


@dataclass(frozen=True)
class QualityApiConfig:
    """Location of the Java Spring Boot quality engine."""

    base_url: str
    timeout_seconds: float
    batch_size: int
    max_retries: int

    @classmethod
    def from_env(cls) -> "QualityApiConfig":
        return cls(
            base_url=_optional("WG_QUALITY_API_URL", "http://localhost:8080").rstrip("/"),
            timeout_seconds=float(_optional("WG_QUALITY_API_TIMEOUT", "30")),
            batch_size=_int("WG_QUALITY_BATCH_SIZE", 500),
            max_retries=_int("WG_QUALITY_API_RETRIES", 3),
        )


@dataclass(frozen=True)
class StorageConfig:
    """Azure Blob Storage: source files in, generated reports out."""

    connection_string: str | None
    landing_container: str
    reports_container: str

    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(
            # Absent in local mode: the pipeline then reads/writes the local filesystem.
            connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or None,
            landing_container=_optional("WG_BLOB_LANDING_CONTAINER", "landing"),
            reports_container=_optional("WG_BLOB_REPORTS_CONTAINER", "reports"),
        )

    @property
    def enabled(self) -> bool:
        return self.connection_string is not None


@dataclass(frozen=True)
class AssistantConfig:
    """LangChain natural-language querying assistant."""

    api_key: str
    model: str
    max_rows: int
    statement_timeout_ms: int

    @classmethod
    def from_env(cls) -> "AssistantConfig":
        return cls(
            api_key=_require("ANTHROPIC_API_KEY"),
            model=_optional("WG_ASSISTANT_MODEL", "claude-sonnet-5"),
            max_rows=_int("WG_ASSISTANT_MAX_ROWS", 200),
            statement_timeout_ms=_int("WG_ASSISTANT_STATEMENT_TIMEOUT_MS", 5000),
        )


@dataclass(frozen=True)
class PathsConfig:
    """Filesystem layout used in local mode."""

    landing_dir: Path
    reference_dir: Path
    reports_dir: Path

    @classmethod
    def from_env(cls) -> "PathsConfig":
        data_root = Path(_optional("WG_DATA_ROOT", str(REPO_ROOT / "data"))).resolve()
        return cls(
            landing_dir=data_root / "seed" / "landing",
            reference_dir=data_root / "seed" / "reference",
            reports_dir=Path(_optional("WG_REPORTS_DIR", str(data_root / "reports"))).resolve(),
        )


@dataclass(frozen=True)
class Settings:
    """Aggregate of every configuration block.

    Built lazily: a command that only needs the database must not fail because
    ``ANTHROPIC_API_KEY`` is unset. Hence the ``database``/``assistant``
    properties below rather than eager construction.
    """

    @property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig.from_env()

    @property
    def quality_api(self) -> QualityApiConfig:
        return QualityApiConfig.from_env()

    @property
    def storage(self) -> StorageConfig:
        return StorageConfig.from_env()

    @property
    def assistant(self) -> AssistantConfig:
        return AssistantConfig.from_env()

    @property
    def paths(self) -> PathsConfig:
        return PathsConfig.from_env()


def load_dotenv_if_present() -> None:
    """Load ``<repo>/.env`` when python-dotenv is installed.

    Convenience for local development only. In Azure Functions the variables
    come from the Application Settings, and in GitLab CI from masked variables,
    so this is a no-op there.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return
    load_dotenv(env_file, override=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv_if_present()
    return Settings()
