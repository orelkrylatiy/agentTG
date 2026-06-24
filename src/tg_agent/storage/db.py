"""
Database connection and initialization.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from sqlmodel import SQLModel, create_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlmodel.pool import StaticPool
except ImportError:  # pragma: no cover
    class _Metadata:
        @staticmethod
        def create_all(_engine):
            return None

    class SQLModel:
        metadata = _Metadata()

    def create_engine(*args, **kwargs):
        return object()

    class AsyncSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class StaticPool:
        pass

from tg_agent.logging import get_logger
from tg_agent.storage.models import (
    GlobalState,
)

if TYPE_CHECKING:
    from tg_agent.config import Settings
else:
    Settings = Any

logger = get_logger(__name__)


class Database:
    """Database manager for SQLite with async support."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        default_agent_enabled: bool | None = None,
        default_chat_mode: str | None = None,
    ):
        """
        Initialize database connection.

        Args:
            database_url: SQLAlchemy database URL. Defaults to settings.
        """
        if database_url is None:
            from tg_agent.config import get_settings

            settings = get_settings()
        else:
            settings = None
        if settings is not None:
            database_url = settings.database_url

        self.database_url = database_url
        self._engine = None
        self.default_agent_enabled = (
            settings.agent_global_enabled
            if default_agent_enabled is None and settings is not None
            else bool(default_agent_enabled)
        )
        self.default_chat_mode = (
            settings.default_chat_mode
            if default_chat_mode is None and settings is not None
            else (default_chat_mode or "DRAFT")
        )

    @property
    def engine(self):
        """Get or create database engine."""
        if self._engine is None:
            # For SQLite, we need check_same_thread=False for async
            connect_args = {"check_same_thread": False}
            self._engine = create_engine(
                self.database_url,
                connect_args=connect_args,
                echo=False,
                poolclass=StaticPool,
            )
        return self._engine

    async def init_db(self) -> None:
        """Create all tables if they don't exist."""
        logger.info("Initializing database...")

        # Ensure data directory exists
        db_path = self.database_url.replace("sqlite:///", "")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Create tables
        SQLModel.metadata.create_all(self.engine)

        # Initialize default global state
        self._init_default_state()

        logger.info("Database initialized successfully")

    def _init_default_state(self) -> None:
        """Initialize default global state entries."""
        try:
            from sqlmodel import Session
        except ImportError:  # pragma: no cover
            return

        with Session(self.engine) as session:
            defaults = [
                (
                    "agent_enabled",
                    "true" if self.default_agent_enabled else "false",
                ),
                ("default_mode", self.default_chat_mode),
            ]

            for key, value in defaults:
                existing = session.get(GlobalState, key)
                if existing is None:
                    state = GlobalState(key=key, value=value)
                    session.add(state)

            session.commit()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get async database session.

        Yields:
            AsyncSession instance.
        """
        async with AsyncSession(self.engine) as session:
            yield session

    def get_sync_session(self):
        """Get sync session for operations that need it."""
        from sqlmodel import Session

        return Session(self.engine)


# Global database instance
_db_instance: Database | None = None


def get_db(
    database_url: str | None = None,
    *,
    default_agent_enabled: bool | None = None,
    default_chat_mode: str | None = None,
) -> Database:
    """Get or create global database instance."""
    global _db_instance
    if (
        _db_instance is None
        or database_url is not None
        or default_agent_enabled is not None
        or default_chat_mode is not None
    ):
        _db_instance = Database(
            database_url=database_url,
            default_agent_enabled=default_agent_enabled,
            default_chat_mode=default_chat_mode,
        )
    return _db_instance
