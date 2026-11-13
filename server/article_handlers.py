"""
LUKB Investment Office — Artikel-Lifecycle- & CRUD-Handler.
Behandelt Artikel-Auswahl, Erstellung, Duplizierung, Soft-Delete, Restore und Dialog-Aktionen.
"""

from __future__ import annotations

import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from config import can_delete
from database.repository import (
    create_new_article,
    delete_article,
    duplicate_article,
    get_article,
    list_articles,
    restore_article,
)
from server.state import SessionState

logger = logging.getLogger("lukb_cms.article_handlers")


def register_article_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert alle Artikel-CRUD- und Navigations-Events an der Session."""

    # Initiales Laden beim Sitzungsstart
    @reactive.effect
    async def _init_session() -> None:
        items = list_articles()
        first_id = items[0]["id"] if items else ""
        await state.load_and_broadcast_article(first_id)

    # Filter- oder Sucheingabe in der linken Sidebar
    @reactive.effect
    @reactive.event(input.sidebar_search_query, input.sidebar_status_val)
    async def _on_sidebar_filter() -> None:
        await state.send_article_list(state.current_article_id.get())

    # Klick auf einen anderen Artikel in der Sidebar
    @reactive.effect
    @reactive.event(input.lukb_select_article)
    async def _on_select_article() -> None:
        payload = input.lukb_select_article()
        if not isinstance(payload, dict):
            return
        target_id = payload.get("id", "")
        if target_id:
            await state.load_and_broadcast_article(target_id)

    # + Neue Publikation anlegen
    @reactive.effect
    @reactive.event(input.btn_new_article)
    async def _on_new_article() -> None:
        new_doc = create_new_article(user=state.current_user)
        await state.load_and_broadcast_article(new_doc.id)
        ui.notification_show("Neue Publikation wurde angelegt.", type="message", duration=3)

    # Artikel duplizieren
    @reactive.effect
    @reactive.event(input.btn_duplicate_article)
    async def _on_duplicate_article() -> None:
        aid = state.current_article_id.get()
        if not aid:
            return
        dup_doc = duplicate_article(aid, user=state.current_user)
        if dup_doc:
            await state.load_and_broadcast_article(dup_doc.id)
            ui.notification_show("Publikation wurde dupliziert.", type="message", duration=3)

    # Artikel löschen (mit Rollenprüfung, Publiziert-Schutz & Sicherheits-Modal)
    @reactive.effect
    @reactive.event(input.btn_delete_article)
    async def _on_delete_article() -> None:
        aid = state.current_article_id.get()
        doc = state.current_doc.get()
        if not aid or not doc:
            return

        user = state.current_user
        if not can_delete(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen löschen / archivieren.",
                type="warning",
                duration=5,
            )
            return

        # Sicherheits-Bestätigungsdialog für Soft-Delete (inkl. automatischer Portal-Rücknahme falls publiziert)
        if doc.status == "published":
            ui.modal_show(
                ui.modal(
                    ui.div(
                        ui.p(
                            f"Die Publikation «{doc.metadata.title}» ist aktuell im statischen Portal online geschaltet.",
                            style="font-weight:600;color:#c0392b;font-size:14.5px;margin-bottom:8px;",
                        ),
                        ui.p(
                            "Möchten Sie diese Publikation vom statischen Portal zurückziehen und sicher in das Archiv verschieben (Soft-Delete)? "
                            "Die Publikation wird aus dem Portal entfernt und die Intranet-Links werden sauber deaktiviert.",
                            style="color:#5A687C;font-size:13px;line-height:1.5;margin-bottom:0;",
                        ),
                    ),
                    title="Publikation zurückziehen & archivieren",
                    footer=ui.div(
                        ui.modal_button("Abbrechen", class_="btn-lukb btn-lukb-ghost"),
                        ui.input_action_button(
                            "btn_confirm_delete_article",
                            "Vom Portal zurückziehen & archivieren",
                            class_="btn-lukb btn-lukb-danger",
                        ),
                        style="display:flex;gap:10px;justify-content:flex-end;width:100%;",
                    ),
                    size="m",
                    easy_close=True,
                )
            )
            return

        all_items = list_articles()
        if len(all_items) <= 1:
            ui.notification_show(
                "Der letzte verbleibende Artikel kann nicht gelöscht werden.",
                type="warning",
                duration=4,
            )
            return

        # Sicherheits-Bestätigungsdialog für Soft-Delete eines Entwurfs/Reviews
        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.p(
                        f"Möchten Sie die Publikation «{doc.metadata.title}» wirklich löschen?",
                        style="font-size:14.5px;font-weight:600;color:#002855;margin-bottom:10px;",
                    ),
                    ui.p(
                        "Der Artikel wird sicher in das Archiv verschoben (Soft-Delete) und aus der aktiven Übersicht ausgeblendet. "
                        "Er kann jederzeit von einem Administrator wiederhergestellt werden.",
                        style="font-size:13px;color:#5A687C;margin-bottom:0;line-height:1.5;",
                    ),
                ),
                title="Publikation archivieren (Soft-Delete)",
                footer=ui.div(
                    ui.modal_button("Abbrechen", class_="btn-lukb btn-lukb-ghost"),
                    ui.input_action_button(
                        "btn_confirm_delete_article",
                        "In Archiv verschieben",
                        class_="btn-lukb btn-lukb-danger",
                    ),
                    style="display:flex;gap:10px;justify-content:flex-end;width:100%;",
                ),
                size="m",
                easy_close=True,
            )
        )

    # Bestätigung des Soft-Deletes ausführen
    @reactive.effect
    @reactive.event(input.btn_confirm_delete_article)
    async def _on_confirm_delete_article() -> None:
        ui.modal_remove()
        aid = state.current_article_id.get()
        if not aid:
            return
        delete_article(aid, user=state.current_user, force=True)
        remaining = list_articles()
        next_id = remaining[0]["id"] if remaining else ""
        if next_id:
            await state.load_and_broadcast_article(next_id)
        else:
            await state.send_article_list("")
        ui.notification_show("Publikation wurde in das Archiv verschoben (Soft-Delete).", type="message", duration=4)

    # Artikel aus dem Archiv wiederherstellen (Restore)
    @reactive.effect
    @reactive.event(input.btn_restore_article)
    async def _on_restore_article() -> None:
        aid = state.current_article_id.get()
        if not aid:
            return
        user = state.current_user
        if not can_delete(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen wiederherstellen.",
                type="warning",
                duration=5,
            )
            return
        ok = restore_article(aid, user=user)
        if ok:
            await state.load_and_broadcast_article(aid)
            ui.notification_show("Publikation wurde aus dem Archiv wiederhergestellt (Status: Entwurf).", type="message", duration=4)
        else:
            ui.notification_show("Dieser Artikel ist nicht archiviert.", type="info", duration=3)

    # Aktionen direkt aus dem Publikations-Dialog (Modal: Neu, Duplizieren, Löschen)
    @reactive.effect
    @reactive.event(input.lukb_modal_article_action)
    async def _on_modal_article_action() -> None:
        payload = input.lukb_modal_article_action()
        if not isinstance(payload, dict):
            return
        action = payload.get("action", "")
        target_id = payload.get("id", "")
        if action == "create":
            new_doc = create_new_article(user=state.current_user)
            await state.load_and_broadcast_article(new_doc.id)
            ui.notification_show("Neue Publikation wurde angelegt.", type="message", duration=3)
        elif action == "duplicate" and target_id:
            dup_doc = duplicate_article(target_id, user=state.current_user)
            if dup_doc:
                await state.load_and_broadcast_article(dup_doc.id)
                ui.notification_show("Publikation wurde dupliziert.", type="message", duration=3)
        elif action == "delete" and target_id:
            user = state.current_user
            if not can_delete(user):
                ui.notification_show("Nur Administratoren oder Senior Editoren dürfen Publikationen löschen.", type="warning", duration=5)
                return
            target_doc = get_article(target_id)
            if not target_doc:
                return
            all_items = list_articles()
            if len(all_items) <= 1:
                ui.notification_show(
                    "Der letzte verbleibende Artikel kann nicht gelöscht werden.",
                    type="warning",
                    duration=4,
                )
                return
            delete_article(target_id, user=user, force=True)
            if state.current_article_id.get() == target_id:
                remaining = list_articles()
                next_id = remaining[0]["id"] if remaining else ""
                await state.load_and_broadcast_article(next_id)
            else:
                await state.send_article_list(state.current_article_id.get())
            ui.notification_show("Publikation wurde in das Archiv verschoben (Soft-Delete).", type="message", duration=3)
