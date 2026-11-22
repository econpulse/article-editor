"""
LUKB Investment Office — Freigabe- & Portal-Workflow-Handler.
Behandelt Einreichung zur Prüfung (Review), Publikation auf das statische Portal und Zurückziehen.
"""

from __future__ import annotations

import asyncio
import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from config import can_publish
from database.repository import get_published_sync_status
from server.collab import broadcast_article_list_to_all, broadcast_article_sync
from server.state import SessionState
from services.publication_service import (
    execute_publish_job,
    execute_unpublish_job,
    submit_article_for_review,
)

logger = logging.getLogger("lukb_cms.workflow_handlers")


def _notify_connect_deploy_result(
    connect_info: dict | None,
    deployed_msg: str,
    local_msg: str,
    local_duration: int = 7,
) -> None:
    if connect_info and connect_info.get("deployed"):
        ui.notification_show(deployed_msg, type="message", duration=5)
    elif connect_info and not connect_info.get("success"):
        ui.notification_show(
            f"⚠️ Lokal aktualisiert, aber Connect-Update fehlgeschlagen: {connect_info.get('error')}",
            type="warning",
            duration=8,
        )
    else:
        ui.notification_show(local_msg, type="message", duration=local_duration)


def register_workflow_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert alle Freigabe- und Portal-Publikations-Events an der Session."""

    # Freigabe-Workflow: Zur Prüfung einreichen (Autor -> Review)
    @reactive.effect
    @reactive.event(input.lukb_submit_review)
    async def _on_submit_review() -> None:
        doc = state.current_doc.get()
        if not doc:
            return
        if not await asyncio.to_thread(state.can_access_article, doc.id, "edit"):
            ui.notification_show("Keine Bearbeitungsberechtigung für diesen Artikel.", type="warning", duration=5)
            return
        if doc.status == "published":
            ui.notification_show("Publikation ist bereits im Portal veröffentlicht.", type="info", duration=4)
            return
        sub_res = await asyncio.to_thread(submit_article_for_review, doc.id, state.current_user_id)
        if not sub_res.get("success"):
            ui.notification_show(sub_res.get("error", "Fehler bei Einreichung"), type="warning", duration=5)
            return
        updated_doc = sub_res["doc"]
        state.current_doc.set(updated_doc)
        await state.send_article_list(updated_doc.id)
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        await broadcast_article_sync(
            article_id=updated_doc.id,
            doc=updated_doc,
            sender_session_id=state.session_id,
            author_name=state.current_user,
            include_sender=True,
        )
        ui.notification_show(
            f"✅ Revision #{sub_res['revision_id']} zur Freigabe eingereicht (Status: In Review).",
            type="message",
            duration=6,
        )

    # Statisches Content-Portal: Publizieren (mit Rollenprüfung)
    @reactive.effect
    @reactive.event(input.lukb_publish_portal)
    async def _on_publish_portal() -> None:
        doc = state.current_doc.get()
        if not doc:
            return
        if not await asyncio.to_thread(state.can_access_article, doc.id, "edit"):
            ui.notification_show("Keine Bearbeitungsberechtigung für diesen Artikel.", type="warning", duration=5)
            return
        user = state.current_user
        if not can_publish(user) or not await asyncio.to_thread(
            state.can_access_article, doc.id, "read", allow_admin_override=True
        ):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf nicht publizieren. Bitte reichen Sie den Artikel 'Zur Prüfung' ein.",
                type="warning",
                duration=6,
            )
            return
        try:
            res = await asyncio.to_thread(execute_publish_job, doc.id, state.current_user_id)
            if res.get("success"):
                doc.status = "published"
                state.current_doc.set(doc)
                pub_sync = await asyncio.to_thread(get_published_sync_status, doc.id)
                await state.send_article_list(doc.id)
                await broadcast_article_list_to_all(exclude_session_id=state.session_id)
                await broadcast_article_sync(
                    article_id=doc.id,
                    doc=doc,
                    sender_session_id=state.session_id,
                    author_name=user,
                    include_sender=True,
                    publish_sync=pub_sync,
                )
                count = res.get("total_published", 1)
                _notify_connect_deploy_result(
                    res.get("connect_deploy"),
                    deployed_msg=f"✅ Artikel publiziert & auf Posit Connect bereitgestellt! ({count} online)",
                    local_msg=f"ℹ️ Lokal publiziert ({count} Artikel). Posit Connect nicht gekoppelt (CONNECT_PORTAL_GUID fehlt in Umgebungsvariablen).",
                )
            else:
                ui.notification_show(f"Publikationsfehler: {res.get('error')}", type="warning", duration=7)
        except Exception as exc:
            ui.notification_show(f"Fehler beim Publizieren: {exc}", type="error", duration=6)

    # Sicherheitsabfrage für "Vom Portal zurückziehen"
    @reactive.effect
    @reactive.event(input.lukb_unpublish_portal)
    async def _on_unpublish_portal() -> None:
        doc = state.current_doc.get()
        if not doc:
            return
        if not await asyncio.to_thread(state.can_access_article, doc.id, "edit"):
            ui.notification_show("Keine Bearbeitungsberechtigung für diesen Artikel.", type="warning", duration=5)
            return
        user = state.current_user
        if not can_publish(user) or not await asyncio.to_thread(
            state.can_access_article, doc.id, "read", allow_admin_override=True
        ):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen vom Portal zurückziehen.",
                type="warning",
                duration=6,
            )
            return
        if doc.status != "published":
            ui.notification_show("Dieser Artikel ist aktuell nicht im Portal publiziert.", type="info", duration=4)
            return

        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.p(
                        f"Möchten Sie die Publikation «{doc.metadata.title}» wirklich vom statischen Intranet-Portal entfernen?",
                        style="font-size:14.5px;font-weight:600;color:#002855;margin-bottom:10px;",
                    ),
                    ui.p(
                        "Das Dokument und das zugehörige PDF sind danach für Mitarbeitende im Intranet nicht mehr abrufbar. "
                        "Der Arbeitsstatus im CMS wird wieder auf 'Entwurf' zurückgesetzt. Ihre Texte und Daten bleiben dabei vollständig erhalten.",
                        style="font-size:13px;color:#5A687C;margin-bottom:0;line-height:1.5;",
                    ),
                ),
                title="Publikation vom Portal zurückziehen",
                footer=ui.div(
                    ui.modal_button("Abbrechen", class_="btn-lukb btn-lukb-ghost"),
                    ui.input_action_button(
                        "btn_confirm_unpublish",
                        "Vom Portal zurückziehen",
                        class_="btn-lukb btn-lukb-danger",
                    ),
                    style="display:flex;gap:10px;justify-content:flex-end;width:100%;",
                ),
                size="m",
                easy_close=True,
            )
        )

    # Bestätigung des Zurückziehens ausführen
    @reactive.effect
    @reactive.event(input.btn_confirm_unpublish)
    async def _on_confirm_unpublish() -> None:
        ui.modal_remove()
        doc = state.current_doc.get()
        if not doc:
            return
        if not await asyncio.to_thread(state.can_access_article, doc.id, "edit"):
            ui.notification_show("Keine Bearbeitungsberechtigung für diesen Artikel.", type="warning", duration=5)
            return
        user = state.current_user
        if not can_publish(user) or not await asyncio.to_thread(
            state.can_access_article, doc.id, "read", allow_admin_override=True
        ):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf keine Publikationen vom Portal zurückziehen.",
                type="warning",
                duration=6,
            )
            return
        try:
            res = await asyncio.to_thread(
                execute_unpublish_job,
                doc.id,
                state.current_user_id,
                new_status="draft",
            )
            if res.get("success"):
                doc.status = "draft"
                state.current_doc.set(doc)
                pub_sync = await asyncio.to_thread(get_published_sync_status, doc.id)
                await state.send_article_list(doc.id)
                await broadcast_article_list_to_all(exclude_session_id=state.session_id)
                await broadcast_article_sync(
                    article_id=doc.id,
                    doc=doc,
                    sender_session_id=state.session_id,
                    author_name=user,
                    include_sender=True,
                    publish_sync=pub_sync,
                )
                _notify_connect_deploy_result(
                    res.get("connect_deploy"),
                    deployed_msg="✅ Artikel vom Portal zurückgezogen & auf Posit Connect entfernt.",
                    local_msg="Artikel vom Portal zurückgezogen (Status auf 'Entwurf' gesetzt).",
                    local_duration=5,
                )
            else:
                ui.notification_show(f"Rückzug fehlgeschlagen: {res.get('error')}", type="warning", duration=7)
        except Exception as exc:
            ui.notification_show(f"Fehler: {exc}", type="error", duration=6)
