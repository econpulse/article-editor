"""
LUKB Investment Office — Freigabe- & Portal-Workflow-Handler.
Behandelt Einreichung zur Prüfung (Review), Publikation auf das statische Portal und Zurückziehen.
"""

from __future__ import annotations

import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from config import can_publish
from database.repository import (
    publish_article_to_portal,
    save_article,
    unpublish_article_from_portal,
)
from server.state import SessionState

logger = logging.getLogger("lukb_cms.workflow_handlers")


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
        if doc.status == "published":
            ui.notification_show("Publikation ist bereits im Portal veröffentlicht.", type="info", duration=4)
            return
        doc.status = "review"
        state.current_doc.set(doc)
        save_article(
            doc,
            user=state.current_user,
            create_revision=True,
            revision_note="Zur Prüfung / Freigabe eingereicht (Status: review)",
        )
        await state.send_article_list(doc.id)
        ui.notification_show(
            "✅ Publikation zur Freigabe eingereicht (Status: In Review). Ein Senior Editor kann den Artikel nun prüfen und publizieren.",
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
        user = state.current_user
        if not can_publish(user):
            ui.notification_show(
                f"Keine Berechtigung: Benutzer '{user}' darf nicht publizieren. Bitte reichen Sie den Artikel 'Zur Prüfung' ein.",
                type="warning",
                duration=6,
            )
            return
        try:
            res = publish_article_to_portal(doc.id, user=user)
            if res.get("success"):
                doc.status = "published"
                state.current_doc.set(doc)
                await state.send_article_list(doc.id)
                count = res.get("total_published", 1)
                connect_info = res.get("connect_deploy")
                if connect_info and connect_info.get("deployed"):
                    ui.notification_show(
                        f"✅ Artikel publiziert & auf Posit Connect bereitgestellt! ({count} online)",
                        type="message",
                        duration=5,
                    )
                elif connect_info and not connect_info.get("success"):
                    ui.notification_show(
                        f"⚠️ Lokal publiziert, aber Connect-Update fehlgeschlagen: {connect_info.get('error')}",
                        type="warning",
                        duration=8,
                    )
                else:
                    ui.notification_show(
                        f"ℹ️ Lokal publiziert ({count} Artikel). Posit Connect nicht gekoppelt (CONNECT_PORTAL_GUID fehlt in Umgebungsvariablen).",
                        type="message",
                        duration=7,
                    )
            else:
                ui.notification_show(f"Publikationsfehler: {res.get('error')}", type="warning", duration=5)
        except Exception as exc:
            ui.notification_show(f"Fehler beim Publizieren: {exc}", type="error", duration=6)

    # Sicherheitsabfrage für "Vom Portal zurückziehen"
    @reactive.effect
    @reactive.event(input.lukb_unpublish_portal)
    async def _on_unpublish_portal() -> None:
        doc = state.current_doc.get()
        if not doc:
            return
        user = state.current_user
        if not can_publish(user):
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
        try:
            res = unpublish_article_from_portal(doc.id, user=state.current_user, new_status="draft")
            if res.get("success"):
                doc.status = "draft"
                state.current_doc.set(doc)
                await state.send_article_list(doc.id)
                connect_info = res.get("connect_deploy")
                if connect_info and connect_info.get("deployed"):
                    ui.notification_show(
                        "✅ Artikel vom Portal zurückgezogen & auf Posit Connect entfernt.",
                        type="message",
                        duration=5,
                    )
                elif connect_info and not connect_info.get("success"):
                    ui.notification_show(
                        f"⚠️ Lokal entfernt, aber Connect-Update fehlgeschlagen: {connect_info.get('error')}",
                        type="warning",
                        duration=8,
                    )
                else:
                    ui.notification_show(
                        "Artikel vom Portal zurückgezogen (Status auf 'Entwurf' gesetzt).",
                        type="message",
                        duration=5,
                    )
            else:
                ui.notification_show(f"Fehler: {res.get('error')}", type="warning", duration=5)
        except Exception as exc:
            ui.notification_show(f"Fehler: {exc}", type="error", duration=6)
