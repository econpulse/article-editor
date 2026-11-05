"""
SQLAlchemy Datenbank-Verbindungsmanagement.
Optimiert für MS SQL Server (MSSQL) auf Posit Connect mit Connection-Pooling,
Pool-Pre-Ping (verhindert Verbindungsabbrüche nach Idle-Zeiten) und Unicode-Unterstützung.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from config import DATABASE_URL, DATABASE_BACKEND_LABEL

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _create_configured_engine():
    is_sqlite = DATABASE_URL.startswith("sqlite")
    if is_sqlite:
        eng = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

        return eng

    # MS SQL Server (mssql+pyodbc) Produktions-Konfiguration
    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,        # Prüft Verbindung vor jeder Transaktion (wichtig auf Posit Connect)
        pool_recycle=1800,         # Recycelt Verbindungen nach 30 Minuten
        pool_size=5,
        max_overflow=10,
        use_setinputsizes=False,   # Vermeidet pyodbc NVARCHAR(MAX)/VARBINARY(MAX) Treiber-Bugs
        future=True,
    )


engine = _create_configured_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Kontextmanager für transaktionssichere Datenbank-Operationen."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_backend_info() -> dict[str, str]:
    return {
        "label": DATABASE_BACKEND_LABEL,
        "dialect": engine.dialect.name,
    }
