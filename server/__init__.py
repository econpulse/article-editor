"""
LUKB Investment Office — Server Logic Package.
Zentrale Orchestrierung aller Server-Handler, State-Management und Kollaboration.
"""

from __future__ import annotations

from shiny import Inputs, Outputs, Session

from server.article_handlers import register_article_handlers
from server.collab import (
    ACTIVE_PEERS,
    PEER_COLORS,
    broadcast_article_sync,
    broadcast_presence,
    broadcast_preview_to_coauthors,
    cleanup_peer,
    collect_article_assets_map,
    get_article_peers,
    get_peer_color,
    get_peer_user,
    is_peer_auto_preview,
    register_peer,
    set_peer_article,
    set_peer_auto_preview,
    set_peer_focus,
)
from server.downloads import register_download_handlers, slugify_filename
from server.editor_handlers import register_editor_handlers
from server.preview_handlers import register_preview_handlers
from server.state import SessionState
from server.workflow_handlers import register_workflow_handlers


def register_all_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
) -> SessionState:
    """Registriert alle Handler-Module und bindet Downloads an die Session an."""
    state = SessionState(session, input)
    register_article_handlers(input, output, session, state)
    register_editor_handlers(input, output, session, state)
    register_preview_handlers(input, output, session, state)
    register_workflow_handlers(input, output, session, state)
    register_download_handlers(output, state.current_doc.get)
    return state


__all__ = [
    "ACTIVE_PEERS",
    "PEER_COLORS",
    "SessionState",
    "broadcast_article_sync",
    "broadcast_presence",
    "broadcast_preview_to_coauthors",
    "cleanup_peer",
    "collect_article_assets_map",
    "get_article_peers",
    "get_peer_color",
    "get_peer_user",
    "is_peer_auto_preview",
    "register_all_handlers",
    "register_article_handlers",
    "register_download_handlers",
    "register_editor_handlers",
    "register_peer",
    "register_preview_handlers",
    "register_workflow_handlers",
    "set_peer_article",
    "set_peer_auto_preview",
    "set_peer_focus",
    "slugify_filename",
]
