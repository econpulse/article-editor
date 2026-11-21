"""
LUKB Investment Office — Artikelrechte-, Prüfaufträge- & Admin-Dashboard-Handler (Etappe 1).
"""

from __future__ import annotations

import asyncio
import logging
from shiny import Inputs, Outputs, Session, reactive, ui

from config import is_global_admin, normalize_user_id
from database.permissions import (
    VALID_ARTICLE_ROLES,
    check_article_permission,
    grant_article_permission,
    list_admin_articles,
    list_article_permissions,
    list_audit_log,
    list_known_users,
    list_review_assignments,
    revoke_article_permission,
    set_global_user_role,
    transfer_article_ownership,
)
from server.collab import broadcast_article_list_to_all, enforce_article_access_revoked
from server.state import SessionState

logger = logging.getLogger("lukb_cms.admin_handlers")

ROLE_LABELS = {
    "owner": "Verantwortlich (Owner)",
    "editor": "Mitarbeit (Editor)",
    "reviewer": "Prüfung (Reviewer)",
    "viewer": "Lesen (Viewer)",
}


def register_admin_handlers(
    input: Inputs,
    output: Outputs,
    session: Session,
    state: SessionState,
) -> None:
    """Registriert Handler für Artikel-Zuweisungen, Prüfaufträge und das Admin-Dashboard."""

    def _build_share_modal(article_id: str, title: str, perms: list[dict], users: list[dict]) -> ui.Tag:
        user_choices = {u["user_id"]: u["display_name"] for u in users}
        rows = []
        for p in perms:
            uid = p["user_id"]
            role_label = ROLE_LABELS.get(p["role"], p["role"])
            rows.append(
                ui.tags.tr(
                    ui.tags.td(uid, style="font-weight:600;padding:6px 8px;"),
                    ui.tags.td(role_label, style="padding:6px 8px;"),
                    ui.tags.td(p.get("granted_by") or "—", style="padding:6px 8px;color:#5A687C;font-size:12px;"),
                    ui.tags.td(
                        ui.tags.button(
                            "Entziehen",
                            type="button",
                            class_="btn-lukb btn-lukb-danger btn-lukb-sm",
                            onclick=f"Shiny.setInputValue('lukb_perm_revoke', {{article_id: '{article_id}', user_id: '{uid}', ts: Date.now()}}, {{priority:'event'}});",
                        ),
                        style="padding:6px 8px;text-align:right;",
                    ),
                )
            )
        if not rows:
            rows.append(
                ui.tags.tr(
                    ui.tags.td("Noch keine Zuordnungen vorhanden.", colspan="4", style="padding:10px;color:#5A687C;")
                )
            )

        return ui.modal(
            ui.div(
                ui.p(
                    f"Artikel: «{title}»",
                    style="font-weight:600;color:#002855;margin-bottom:10px;",
                ),
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Benutzer", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Rolle", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Zugewiesen von", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("", style="padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                        )
                    ),
                    ui.tags.tbody(*rows),
                    style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;",
                ),
                ui.div(
                    ui.h6("Benutzer hinzufügen oder Rolle ändern", style="margin:0 0 8px 0;color:#002855;font-weight:600;"),
                    ui.div(
                        ui.input_text(
                            "share_target_user",
                            "Benutzerkennung (Connect-ID)",
                            placeholder="z. B. autor.b@lukb.ch",
                        ),
                        ui.input_select(
                            "share_target_role",
                            "Artikelrolle",
                            choices={r: ROLE_LABELS[r] for r in VALID_ARTICLE_ROLES},
                            selected="editor",
                        ),
                        style="display:grid;grid-template-columns:1fr 1fr;gap:10px;",
                    ),
                    (
                        ui.p(
                            f"Bekannte Benutzer: {', '.join(sorted(user_choices.keys())[:10])}",
                            style="font-size:11.5px;color:#5A687C;margin-top:4px;",
                        )
                        if user_choices
                        else ui.span()
                    ),
                    ui.input_action_button(
                        "btn_share_grant",
                        "Berechtigung speichern",
                        class_="btn-lukb btn-lukb-primary btn-lukb-sm",
                    ),
                    style="background:#F4F7FA;padding:12px;border-radius:6px;border:1px solid #D6DEE8;",
                ),
            ),
            title="Artikel-Berechtigungen & Mitarbeit",
            size="l",
            easy_close=True,
            footer=ui.modal_button("Schliessen", class_="btn-lukb btn-lukb-ghost"),
        )

    @reactive.effect
    @reactive.event(input.lukb_open_share_modal)
    async def _on_open_share_modal() -> None:
        aid = state.current_article_id.get()
        doc = state.current_doc.get()
        if not aid or not doc:
            ui.notification_show("Kein Artikel geöffnet.", type="info", duration=3)
            return
        if not await asyncio.to_thread(
            check_article_permission, aid, state.current_user_id, "assign", allow_admin_override=True
        ):
            ui.notification_show("Nur Verantwortliche oder Administratoren dürfen Zugriffsrechte vergeben.", type="warning", duration=4)
            return
        perms = await asyncio.to_thread(list_article_permissions, aid)
        users = await asyncio.to_thread(list_known_users)
        ui.modal_show(_build_share_modal(aid, doc.metadata.title, perms, users))

    @reactive.effect
    @reactive.event(input.btn_share_grant)
    async def _on_share_grant() -> None:
        aid = state.current_article_id.get()
        doc = state.current_doc.get()
        if not aid or not doc:
            return
        target = (input.share_target_user() or "").strip()
        role = (input.share_target_role() or "editor").strip()
        res = await asyncio.to_thread(grant_article_permission, aid, target, role, state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler beim Speichern"), type="warning", duration=5)
            return
        await broadcast_article_list_to_all()
        perms = await asyncio.to_thread(list_article_permissions, aid)
        users = await asyncio.to_thread(list_known_users)
        ui.modal_show(_build_share_modal(aid, doc.metadata.title, perms, users))
        ui.notification_show(f"Zugriff für {res['user_id']} gespeichert ({role}).", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_perm_revoke)
    async def _on_perm_revoke() -> None:
        payload = input.lukb_perm_revoke()
        if not isinstance(payload, dict):
            return
        aid = str(payload.get("article_id", "")).strip()
        target_uid = str(payload.get("user_id", "")).strip()
        if not aid or not target_uid:
            return
        res = await asyncio.to_thread(revoke_article_permission, aid, target_uid, state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler beim Entziehen"), type="warning", duration=5)
            return
        await enforce_article_access_revoked(aid, target_uid)
        await broadcast_article_list_to_all()
        doc = state.current_doc.get()
        if doc and doc.id == aid and state.current_user_id != normalize_user_id(target_uid):
            perms = await asyncio.to_thread(list_article_permissions, aid)
            users = await asyncio.to_thread(list_known_users)
            ui.modal_show(_build_share_modal(aid, doc.metadata.title, perms, users))
        else:
            ui.modal_remove()
        ui.notification_show(f"Zugriff für {target_uid} entzogen.", type="message", duration=3)

    # ------------------------------------------------------------------
    # Prüfaufträge (für Prüfberechtigte)
    # ------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.lukb_open_review_assignments)
    async def _on_open_review_assignments() -> None:
        if not state.is_authenticated:
            ui.notification_show("Bitte melden Sie sich mit Ihrem Connect-Konto an.", type="warning", duration=4)
            return
        items = await asyncio.to_thread(list_review_assignments, state.current_user_id)
        rows = []
        for it in items:
            rows.append(
                ui.tags.tr(
                    ui.tags.td(it["title"], style="font-weight:600;padding:6px 8px;"),
                    ui.tags.td(it["status"], style="padding:6px 8px;"),
                    ui.tags.td(f"v{it['version']} · {it['updated_at']}", style="padding:6px 8px;color:#5A687C;font-size:12px;"),
                    ui.tags.td(ROLE_LABELS.get(it["article_role"], it["article_role"]), style="padding:6px 8px;font-size:12px;"),
                    ui.tags.td(
                        ui.tags.button(
                            "Öffnen",
                            type="button",
                            class_="btn-lukb btn-lukb-primary btn-lukb-sm",
                            onclick=f"Shiny.setInputValue('lukb_select_article', {{id: '{it['id']}', ts: Date.now()}}, {{priority:'event'}}); document.querySelectorAll('.modal .btn-close, .modal [data-bs-dismiss=\"modal\"]').forEach(b=>b.click());",
                        ),
                        style="padding:6px 8px;text-align:right;",
                    ),
                )
            )
        if not rows:
            rows.append(
                ui.tags.tr(
                    ui.tags.td("Keine zugeteilten Prüfaufträge vorhanden.", colspan="5", style="padding:12px;color:#5A687C;")
                )
            )
        ui.modal_show(
            ui.modal(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Artikel", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Status", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Stand", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Rolle", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("", style="padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                        )
                    ),
                    ui.tags.tbody(*rows),
                    style="width:100%;border-collapse:collapse;font-size:13px;",
                ),
                title="Meine Prüfaufträge",
                size="l",
                easy_close=True,
                footer=ui.modal_button("Schliessen", class_="btn-lukb btn-lukb-ghost"),
            )
        )

    # ------------------------------------------------------------------
    # Admin-Dashboard (Artikel & Benutzer + Publikationen & Protokoll)
    # ------------------------------------------------------------------
    async def _show_admin_dashboard(active_tab: str = "articles") -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            ui.notification_show("Nur Administratoren haben Zugriff auf das Admin-Dashboard.", type="warning", duration=5)
            return

        search_q = ""
        only_orphans = False
        try:
            search_q = input.admin_article_search() or ""
        except Exception:
            pass
        try:
            only_orphans = bool(input.admin_only_orphans())
        except Exception:
            pass

        articles = await asyncio.to_thread(list_admin_articles, search_q, only_orphans=only_orphans)
        users = await asyncio.to_thread(list_known_users)
        audit_entries = await asyncio.to_thread(list_audit_log, 60)

        art_rows = []
        for a in articles[:40]:
            perm_badges = ", ".join(f"{p['user_id']} ({p['role']})" for p in a["permissions"]) or "⚠️ Verwaist (keine Zuordnung)"
            art_rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.div(a["title"], style="font-weight:600;color:#002855;"),
                        ui.div(f"ID: {a['id']} · Status: {a['status']} · v{a['version']}", style="font-size:11.5px;color:#5A687C;"),
                        style="padding:6px 8px;",
                    ),
                    ui.tags.td(perm_badges, style="padding:6px 8px;font-size:12px;"),
                    ui.tags.td(
                        ui.tags.button(
                            "Verantwortung übernehmen / zuweisen",
                            type="button",
                            class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                            onclick=f"Shiny.setInputValue('lukb_admin_select_article_for_assign', '{a['id']}', {{priority:'event'}});",
                        ),
                        style="padding:6px 8px;text-align:right;",
                    ),
                )
            )
        if not art_rows:
            art_rows.append(ui.tags.tr(ui.tags.td("Keine passenden Artikel gefunden.", colspan="3", style="padding:10px;color:#5A687C;")))

        user_rows = []
        for u in users:
            user_rows.append(
                ui.tags.tr(
                    ui.tags.td(u["user_id"], style="font-weight:600;padding:5px 8px;"),
                    ui.tags.td("Ja" if u["is_admin"] else "Nein", style="padding:5px 8px;"),
                    ui.tags.td("Ja" if u["can_publish"] else "Nein", style="padding:5px 8px;"),
                    ui.tags.td(u.get("source", ""), style="padding:5px 8px;color:#5A687C;font-size:12px;"),
                )
            )

        audit_rows = []
        for log in audit_entries:
            audit_rows.append(
                ui.tags.tr(
                    ui.tags.td(log["created_at"], style="padding:5px 8px;font-size:12px;white-space:nowrap;"),
                    ui.tags.td(log["actor_user"], style="padding:5px 8px;font-size:12px;font-weight:600;"),
                    ui.tags.td(log["action"], style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(log["target_user"] or "—", style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(log["article_id"] or "—", style="padding:5px 8px;font-size:11.5px;color:#5A687C;"),
                )
            )
        if not audit_rows:
            audit_rows.append(ui.tags.tr(ui.tags.td("Noch keine Protokolleinträge.", colspan="5", style="padding:10px;color:#5A687C;")))

        ui.modal_show(
            ui.modal(
                ui.navset_tab(
                    ui.nav_panel(
                        "Artikel und Benutzer",
                        ui.div(
                            ui.div(
                                ui.input_text("admin_article_search", "Artikel suchen", value=search_q, placeholder="Titel, Autor, Kategorie…"),
                                ui.input_checkbox("admin_only_orphans", "Nur verwaiste Artikel anzeigen", value=only_orphans),
                                ui.input_action_button("btn_admin_refresh", "Filter anwenden", class_="btn-lukb btn-lukb-ghost btn-lukb-sm"),
                                style="display:flex;gap:12px;align-items:flex-end;margin:10px 0;",
                            ),
                            ui.div(
                                ui.tags.table(
                                    ui.tags.thead(
                                        ui.tags.tr(
                                            ui.tags.th("Artikel", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Zugewiesene Benutzer", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Aktion", style="text-align:right;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                                        )
                                    ),
                                    ui.tags.tbody(*art_rows),
                                    style="width:100%;border-collapse:collapse;font-size:13px;",
                                ),
                                style="max-height:220px;overflow-y:auto;border:1px solid #D6DEE8;border-radius:6px;margin-bottom:12px;",
                            ),
                            ui.div(
                                ui.h6("Artikel zuordnen / Verantwortung übertragen", style="margin:0 0 8px 0;color:#002855;font-weight:600;"),
                                ui.div(
                                    ui.input_text("admin_assign_article_id", "Artikel-ID", placeholder="Artikel-ID aus Tabelle wählen…"),
                                    ui.input_text("admin_assign_user_id", "Ziel-Benutzerkennung", placeholder="z. B. autor.a@lukb.ch"),
                                    ui.input_select(
                                        "admin_assign_role",
                                        "Aktion / Rolle",
                                        choices={
                                            "transfer_owner": "Verantwortung übertragen (Owner)",
                                            **{r: ROLE_LABELS[r] for r in VALID_ARTICLE_ROLES},
                                            "revoke": "Zugriff entziehen",
                                        },
                                    ),
                                    style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;",
                                ),
                                ui.input_action_button("btn_admin_apply_article_perm", "Zuordnung ausführen", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                                style="background:#F4F7FA;padding:10px;border-radius:6px;border:1px solid #D6DEE8;margin-bottom:12px;",
                            ),
                            ui.div(
                                ui.h6("Globale Benutzerrollen (Admin & Publizieren getrennt)", style="margin:0 0 8px 0;color:#002855;font-weight:600;"),
                                ui.div(
                                    ui.input_text("admin_role_user_id", "Benutzerkennung", placeholder="z. B. editor@lukb.ch"),
                                    ui.input_checkbox("admin_role_is_admin", "Admin-Zugriff", value=False),
                                    ui.input_checkbox("admin_role_can_publish", "Darf publizieren", value=False),
                                    ui.input_action_button("btn_admin_save_user_role", "Rolle speichern", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                                    style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px;",
                                ),
                                ui.tags.table(
                                    ui.tags.thead(
                                        ui.tags.tr(
                                            ui.tags.th("Benutzer", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Admin", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Publizieren", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Quelle", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                        )
                                    ),
                                    ui.tags.tbody(*user_rows),
                                    style="width:100%;border-collapse:collapse;font-size:12.5px;",
                                ),
                                style="background:#FFFFFF;padding:10px;border-radius:6px;border:1px solid #D6DEE8;",
                            ),
                        ),
                    ),
                    ui.nav_panel(
                        "Publikationen und Protokoll",
                        ui.div(
                            ui.p(
                                "Nachvollziehbares Protokoll aller Zuweisungs- und Rollenänderungen (Auslieferungsstatus & Wiederholung folgen in Etappe 2).",
                                style="font-size:12.5px;color:#5A687C;margin:8px 0;",
                            ),
                            ui.div(
                                ui.tags.table(
                                    ui.tags.thead(
                                        ui.tags.tr(
                                            ui.tags.th("Zeitpunkt", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Ausgeführt von", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Aktion", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Ziel-Konto", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                            ui.tags.th("Artikel-ID", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                                        )
                                    ),
                                    ui.tags.tbody(*audit_rows),
                                    style="width:100%;border-collapse:collapse;font-size:12.5px;",
                                ),
                                style="max-height:380px;overflow-y:auto;border:1px solid #D6DEE8;border-radius:6px;",
                            ),
                        ),
                    ),
                    selected="Publikationen und Protokoll" if active_tab == "audit" else "Artikel und Benutzer",
                ),
                title="Admin-Dashboard — Artikelrechte, Benutzer & Protokoll",
                size="xl",
                easy_close=True,
                footer=ui.modal_button("Schliessen", class_="btn-lukb btn-lukb-ghost"),
            )
        )

    @reactive.effect
    @reactive.event(input.lukb_open_admin_dashboard, input.btn_admin_refresh)
    async def _on_open_admin_dashboard() -> None:
        await _show_admin_dashboard("articles")

    @reactive.effect
    @reactive.event(input.lukb_admin_select_article_for_assign)
    def _on_admin_select_article() -> None:
        aid = input.lukb_admin_select_article_for_assign()
        if aid:
            ui.update_text("admin_assign_article_id", value=str(aid))

    @reactive.effect
    @reactive.event(input.btn_admin_apply_article_perm)
    async def _on_admin_apply_article_perm() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        aid = (input.admin_assign_article_id() or "").strip()
        target_uid = (input.admin_assign_user_id() or "").strip()
        action = (input.admin_assign_role() or "").strip()
        if not aid or not target_uid:
            ui.notification_show("Bitte Artikel-ID und Benutzerkennung angeben.", type="warning", duration=4)
            return
        if action == "transfer_owner":
            res = await asyncio.to_thread(transfer_article_ownership, aid, target_uid, state.current_user_id)
        elif action == "revoke":
            res = await asyncio.to_thread(revoke_article_permission, aid, target_uid, state.current_user_id)
            if res.get("success"):
                await enforce_article_access_revoked(aid, target_uid)
        else:
            res = await asyncio.to_thread(grant_article_permission, aid, target_uid, action, state.current_user_id)

        if not res.get("success"):
            ui.notification_show(res.get("error", "Aktion fehlgeschlagen"), type="warning", duration=5)
            return
        await broadcast_article_list_to_all()
        await state.send_article_list(state.current_article_id.get())
        await _show_admin_dashboard("articles")
        ui.notification_show("Artikelzuordnung aktualisiert.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.btn_admin_save_user_role)
    async def _on_admin_save_user_role() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        target_uid = (input.admin_role_user_id() or "").strip()
        is_adm = bool(input.admin_role_is_admin())
        can_pub = bool(input.admin_role_can_publish())
        res = await asyncio.to_thread(
            set_global_user_role,
            target_uid,
            is_admin=is_adm,
            can_publish=can_pub,
            actor_user=state.current_user_id,
        )
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler beim Speichern der Rolle"), type="warning", duration=5)
            return
        await _show_admin_dashboard("articles")
        ui.notification_show(f"Globale Rolle für {res['user_id']} gespeichert.", type="message", duration=3)
