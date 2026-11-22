"""
LUKB Investment Office — Artikelrechte-, Prüfaufträge- & Admin-Dashboard-Handler (Etappe 1).
"""

from __future__ import annotations

import asyncio
import json
import logging
from shiny import Inputs, Outputs, Session, reactive, render, ui

from config import is_global_admin, normalize_user_id
from database.permissions import (
    VALID_ARTICLE_ROLES,
    check_article_permission,
    delete_user_account,
    grant_article_permission,
    list_admin_articles,
    list_article_permissions,
    list_audit_log,
    list_known_users,
    list_review_assignments,
    revoke_article_permission,
    set_global_user_role,
    set_user_active_status,
    transfer_article_ownership,
)
from server.collab import broadcast_article_list_to_all, broadcast_article_sync, enforce_article_access_revoked
from server.state import SessionState
from services.publication_service import (
    approve_article_revision,
    get_admin_publication_overview,
    get_article_revision_for_review,
    list_publication_jobs,
    poll_publication_job,
    retry_publication_job,
)
from services.renderer import render_web_html

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

    perm_refresh_tick = reactive.Value(0) if hasattr(reactive, "Value") else None
    admin_refresh_tick = reactive.Value(0) if hasattr(reactive, "Value") else None

    def _bump_perm_refresh() -> None:
        if perm_refresh_tick is not None:
            perm_refresh_tick.set(perm_refresh_tick.get() + 1)

    def _bump_admin_refresh() -> None:
        if admin_refresh_tick is not None:
            admin_refresh_tick.set(admin_refresh_tick.get() + 1)

    def _format_user_label(uid: str, display_name: str | None) -> str:
        name = (display_name or "").strip()
        if name and name.lower() != uid.lower():
            return f"{name} ({uid})"
        return uid

    def _build_known_users_datalist(users: list[dict], datalist_id: str = "lukb-known-users-datalist") -> ui.Tag:
        opts = []
        for u in users:
            if not u.get("is_active", True):
                continue
            uid = u["user_id"]
            label = _format_user_label(uid, u.get("display_name"))
            opts.append(ui.tags.option(value=uid, label=label))
        return ui.tags.datalist(*opts, id=datalist_id)

    async def _render_doc_permissions_panel() -> ui.Tag:
        aid = state.current_article_id.get()
        _ = perm_refresh_tick.get() if perm_refresh_tick is not None else 0
        if not aid:
            return ui.span()

        def _load_perm_view():
            can_read = check_article_permission(aid, state.current_user_id, "read", allow_admin_override=True)
            if not can_read:
                return None
            can_assign = check_article_permission(aid, state.current_user_id, "assign", allow_admin_override=True)
            perms = list_article_permissions(aid)
            users = list_known_users()
            return can_assign, perms, users

        data = await asyncio.to_thread(_load_perm_view)
        if data is None:
            return ui.span()
        can_assign, perms, users = data

        chips = []
        for p in perms:
            uid = p["user_id"]
            label = _format_user_label(uid, p.get("display_name"))
            role_short = {
                "owner": "Verantwortlich",
                "editor": "Editor",
                "reviewer": "Prüfer",
                "viewer": "Lesen",
            }.get(p["role"], p["role"])
            remove_btn = (
                ui.tags.button(
                    "×",
                    type="button",
                    title=f"Zugriff für {label} entziehen",
                    style="border:none;background:transparent;color:#991B1B;font-weight:700;cursor:pointer;padding:0 2px;margin-left:4px;line-height:1;",
                    onclick=f"Shiny.setInputValue('lukb_doc_perm_revoke', {{article_id: {json.dumps(aid)}, user_id: {json.dumps(uid)}, ts: Date.now()}}, {{priority:'event'}});",
                )
                if can_assign
                else ui.span()
            )
            chips.append(
                ui.span(
                    ui.span(label, style="font-weight:600;color:#002855;"),
                    ui.span(
                        role_short,
                        style="background:#E6EFF7;color:#004B87;border-radius:4px;padding:1px 5px;font-size:11px;margin-left:5px;",
                    ),
                    remove_btn,
                    style="display:inline-flex;align-items:center;background:#FFFFFF;border:1px solid #D6DEE8;border-radius:999px;padding:3px 9px;font-size:12px;",
                )
            )
        if not chips:
            chips.append(ui.span("Noch keine Zuordnungen.", style="font-size:12px;color:#5A687C;"))

        assign_bar = (
            ui.div(
                _build_known_users_datalist(users, "lukb-doc-perm-users-datalist"),
                ui.div(
                    ui.input_text(
                        "doc_perm_target_user",
                        None,
                        placeholder="Mitarbeitende hinzufügen (Alias / Connect-ID)…",
                    ),
                    style="flex:1;min-width:210px;",
                ),
                ui.div(
                    ui.input_select(
                        "doc_perm_target_role",
                        None,
                        choices={r: ROLE_LABELS[r] for r in VALID_ARTICLE_ROLES},
                        selected="editor",
                    ),
                    style="min-width:175px;",
                ),
                ui.input_action_button(
                    "btn_doc_perm_grant",
                    "+ Zuweisen",
                    class_="btn-lukb btn-lukb-primary btn-lukb-sm",
                ),
                ui.tags.script(
                    "setTimeout(function(){var el=document.getElementById('doc_perm_target_user');if(el)el.setAttribute('list','lukb-doc-perm-users-datalist');},0);"
                ),
                style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px;",
            )
            if can_assign
            else ui.div(
                "Änderungen an Berechtigungen können durch Verantwortliche (Owner) oder Admins vorgenommen werden.",
                style="font-size:11.5px;color:#5A687C;margin-top:6px;",
            )
        )

        return ui.div(
            ui.div(
                ui.tags.label("Berechtigungen & Mitarbeit (Wer darf mitarbeiten?)", class_="field-label", style="margin:0;"),
                ui.span(f"{len(perms)} Zugewiesen", style="font-size:11.5px;color:#5A687C;"),
                style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;",
            ),
            ui.div(*chips, style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;"),
            assign_bar,
            class_="field-group",
            style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:10px 12px;",
        )

    if callable(output):
        output(id="doc_permissions_panel")(render.ui(_render_doc_permissions_panel))

    @reactive.effect
    @reactive.event(input.btn_doc_perm_grant)
    async def _on_doc_perm_grant() -> None:
        aid = state.current_article_id.get()
        doc = state.current_doc.get()
        if not aid or not doc:
            return
        target = (input.doc_perm_target_user() or "").strip()
        role = (input.doc_perm_target_role() or "editor").strip()
        res = await asyncio.to_thread(grant_article_permission, aid, target, role, state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler beim Zuweisen"), type="warning", duration=5)
            return
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        _bump_perm_refresh()
        ui.notification_show(f"Zugriff für {res['user_id']} gespeichert ({role}).", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_doc_perm_revoke)
    async def _on_doc_perm_revoke() -> None:
        payload = input.lukb_doc_perm_revoke()
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
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        _bump_perm_refresh()
        _bump_perm_refresh()
        ui.notification_show(f"Zugriff für {target_uid} entzogen.", type="message", duration=3)

    async def _render_share_modal_perms() -> ui.Tag:
        aid = state.current_article_id.get()
        _ = perm_refresh_tick.get() if perm_refresh_tick is not None else 0
        if not aid:
            return ui.span()

        def _load_share_data():
            if not check_article_permission(aid, state.current_user_id, "assign", allow_admin_override=True):
                return None
            return list_article_permissions(aid), list_known_users()

        data = await asyncio.to_thread(_load_share_data)
        if data is None:
            return ui.span()
        perms, users = data

        rows = []
        for p in perms:
            uid = p["user_id"]
            user_label = _format_user_label(uid, p.get("display_name"))
            role_label = ROLE_LABELS.get(p["role"], p["role"])
            rows.append(
                ui.tags.tr(
                    ui.tags.td(user_label, style="font-weight:600;padding:6px 8px;"),
                    ui.tags.td(role_label, style="padding:6px 8px;"),
                    ui.tags.td(p.get("granted_by") or "—", style="padding:6px 8px;color:#5A687C;font-size:12px;"),
                    ui.tags.td(
                        ui.tags.button(
                            "Entziehen",
                            type="button",
                            class_="btn-lukb btn-lukb-danger btn-lukb-sm",
                            onclick=f"Shiny.setInputValue('lukb_perm_revoke', {{article_id: {json.dumps(aid)}, user_id: {json.dumps(uid)}, ts: Date.now()}}, {{priority:'event'}});",
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

        known_hints = [
            _format_user_label(u["user_id"], u.get("display_name"))
            for u in users
            if u.get("is_active", True)
        ][:10]

        return ui.div(
            _build_known_users_datalist(users, "lukb-share-users-datalist"),
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
                style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px;",
            ),
            (
                ui.p(
                    f"Bekannte Benutzer: {', '.join(known_hints)}",
                    style="font-size:11.5px;color:#5A687C;margin-top:0;margin-bottom:8px;",
                )
                if known_hints
                else ui.span()
            ),
        )

    if callable(output):
        output(id="share_modal_perms_ui")(render.ui(_render_share_modal_perms))

    def _build_share_modal(title: str) -> ui.Tag:
        return ui.modal(
            ui.div(
                ui.p(
                    f"Artikel: «{title}»",
                    style="font-weight:600;color:#002855;margin-bottom:10px;",
                ),
                ui.output_ui("share_modal_perms_ui"),
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
                    ui.tags.script(
                        "setTimeout(function(){var el=document.getElementById('share_target_user');if(el)el.setAttribute('list','lukb-share-users-datalist');},0);"
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
        _bump_perm_refresh()
        ui.modal_show(_build_share_modal(doc.metadata.title))

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
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        _bump_perm_refresh()
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
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        _bump_perm_refresh()
        doc = state.current_doc.get()
        if not (doc and doc.id == aid and state.current_user_id != normalize_user_id(target_uid)):
            ui.modal_remove()
        ui.notification_show(f"Zugriff für {target_uid} entzogen.", type="message", duration=3)

    # ------------------------------------------------------------------
    # Prüfaufträge (für Prüfberechtigte)
    # ------------------------------------------------------------------
    async def _show_review_assignments_modal() -> None:
        items = await asyncio.to_thread(list_review_assignments, state.current_user_id)
        rows = []
        for it in items:
            sub_rev_id = it.get("submitted_revision_id")
            app_rev_id = it.get("approved_revision_id")
            is_approved = bool(sub_rev_id and app_rev_id and int(sub_rev_id) == int(app_rev_id))
            if sub_rev_id:
                rev_label = f"Rev #{sub_rev_id} · {'Freigegeben' if is_approved else 'Zur Prüfung'}"
            else:
                rev_label = "Keine Einreichung"

            aid_js = json.dumps(it["id"])
            action_buttons = []
            if sub_rev_id:
                rev_id_int = int(sub_rev_id)
                action_buttons.append(
                    ui.tags.button(
                        "Revision ansehen",
                        type="button",
                        class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                        onclick=(
                            f"Shiny.setInputValue('lukb_view_review_revision', "
                            f"{{article_id: {aid_js}, revision_id: {rev_id_int}, ts: Date.now()}}, {{priority:'event'}});"
                        ),
                    )
                )
                if not is_approved:
                    action_buttons.append(
                        ui.tags.button(
                            "Diese Revision freigeben",
                            type="button",
                            class_="btn-lukb btn-lukb-success btn-lukb-sm",
                            onclick=(
                                f"Shiny.setInputValue('lukb_approve_review_revision', "
                                f"{{article_id: {aid_js}, revision_id: {rev_id_int}, ts: Date.now()}}, {{priority:'event'}});"
                            ),
                        )
                    )
            action_buttons.append(
                ui.tags.button(
                    "Öffnen",
                    type="button",
                    class_="btn-lukb btn-lukb-primary btn-lukb-sm",
                    onclick=(
                        f"Shiny.setInputValue('lukb_select_article', {{id: {aid_js}, ts: Date.now()}}, {{priority:'event'}}); "
                        "document.querySelectorAll('.modal .btn-close, .modal [data-bs-dismiss=\"modal\"]').forEach(b=>b.click());"
                    ),
                )
            )
            rows.append(
                ui.tags.tr(
                    ui.tags.td(it["title"], style="font-weight:600;padding:6px 8px;"),
                    ui.tags.td(it["status"], style="padding:6px 8px;"),
                    ui.tags.td(rev_label, style="padding:6px 8px;font-size:12px;color:#002855;"),
                    ui.tags.td(f"v{it['version']} · {it['updated_at']}", style="padding:6px 8px;color:#5A687C;font-size:12px;"),
                    ui.tags.td(ROLE_LABELS.get(it["article_role"], it["article_role"]), style="padding:6px 8px;font-size:12px;"),
                    ui.tags.td(
                        ui.div(*action_buttons, style="display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap;"),
                        style="padding:6px 8px;text-align:right;",
                    ),
                )
            )
        if not rows:
            rows.append(
                ui.tags.tr(
                    ui.tags.td("Keine zugeteilten Prüfaufträge vorhanden.", colspan="6", style="padding:12px;color:#5A687C;")
                )
            )
        ui.modal_show(
            ui.modal(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Artikel", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Status", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Einreichung", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Stand", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Rolle", style="text-align:left;padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("", style="padding:6px 8px;border-bottom:1px solid #D6DEE8;"),
                        )
                    ),
                    ui.tags.tbody(*rows),
                    style="width:100%;border-collapse:collapse;font-size:13px;",
                ),
                title="Meine Prüfaufträge",
                size="xl",
                easy_close=True,
                footer=ui.modal_button("Schliessen", class_="btn-lukb btn-lukb-ghost"),
            )
        )

    @reactive.effect
    @reactive.event(input.lukb_open_review_assignments)
    async def _on_open_review_assignments() -> None:
        if not state.is_authenticated:
            ui.notification_show("Bitte melden Sie sich mit Ihrem Connect-Konto an.", type="warning", duration=4)
            return
        await _show_review_assignments_modal()

    @reactive.effect
    @reactive.event(input.lukb_view_review_revision)
    async def _on_view_review_revision() -> None:
        if not state.is_authenticated:
            ui.notification_show("Bitte melden Sie sich mit Ihrem Connect-Konto an.", type="warning", duration=4)
            return
        payload = input.lukb_view_review_revision()
        if not isinstance(payload, dict):
            return
        aid = str(payload.get("article_id") or "").strip()
        rev_id = payload.get("revision_id")
        if not aid or not rev_id:
            return
        if not await asyncio.to_thread(state.can_access_article, aid, "review", allow_admin_override=True):
            ui.notification_show("Keine Prüfberechtigung für diesen Artikel.", type="warning", duration=5)
            return
        rev_info = await asyncio.to_thread(get_article_revision_for_review, aid, int(rev_id))
        if not rev_info:
            ui.notification_show("Eingereichte Revision konnte nicht geladen werden.", type="warning", duration=4)
            return
        preview_html = await asyncio.to_thread(render_web_html, rev_info["doc"])
        is_approved = bool(
            rev_info.get("approved_revision_id") and int(rev_info["approved_revision_id"]) == int(rev_info["revision_id"])
        )
        aid_js = json.dumps(aid)
        rev_id_int = int(rev_info["revision_id"])
        footer_items = [
            ui.tags.button(
                "Zurück zu Prüfaufträgen",
                type="button",
                class_="btn-lukb btn-lukb-ghost",
                onclick="Shiny.setInputValue('lukb_open_review_assignments', {ts: Date.now()}, {priority:'event'});",
            ),
            ui.modal_button("Schliessen", class_="btn-lukb btn-lukb-ghost"),
        ]
        if not is_approved:
            footer_items.append(
                ui.tags.button(
                    "Diese Revision freigeben",
                    type="button",
                    class_="btn-lukb btn-lukb-success",
                    onclick=(
                        f"Shiny.setInputValue('lukb_approve_review_revision', "
                        f"{{article_id: {aid_js}, revision_id: {rev_id_int}, ts: Date.now()}}, {{priority:'event'}});"
                    ),
                )
            )
        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.p(
                        f"Revision #{rev_id_int} · Eingereicht von {rev_info.get('submitted_by') or 'unbekannt'} "
                        f"am {rev_info.get('saved_at') or ''}"
                        + (" · ✅ Bereits freigegeben" if is_approved else ""),
                        style="font-size:12.5px;color:#5A687C;margin-bottom:10px;",
                    ),
                    ui.tags.iframe(
                        srcdoc=preview_html,
                        sandbox="allow-same-origin",
                        style="width:100%;height:65vh;border:1px solid #D6DEE8;border-radius:6px;background:#fff;",
                    ),
                ),
                title=f"Prüfansicht: {rev_info['title']} (Rev #{rev_id_int})",
                size="xl",
                easy_close=True,
                footer=ui.div(*footer_items, style="display:flex;gap:8px;justify-content:flex-end;width:100%;"),
            )
        )

    @reactive.effect
    @reactive.event(input.lukb_approve_review_revision)
    async def _on_approve_review_revision() -> None:
        if not state.is_authenticated:
            ui.notification_show("Bitte melden Sie sich mit Ihrem Connect-Konto an.", type="warning", duration=4)
            return
        payload = input.lukb_approve_review_revision()
        if not isinstance(payload, dict):
            return
        aid = str(payload.get("article_id") or "").strip()
        rev_id = payload.get("revision_id")
        if not aid or not rev_id:
            return
        if not await asyncio.to_thread(state.can_access_article, aid, "review", allow_admin_override=True):
            ui.notification_show("Keine Prüfberechtigung für diesen Artikel.", type="warning", duration=5)
            return
        res = await asyncio.to_thread(approve_article_revision, aid, int(rev_id), state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Freigabe fehlgeschlagen."), type="warning", duration=6)
            return
        ui.notification_show(f"✅ Revision #{rev_id} wurde freigegeben.", type="message", duration=5)
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        await _show_review_assignments_modal()

    # ------------------------------------------------------------------
    # Admin-Dashboard (Artikel & Benutzer + Publikationen & Protokoll)
    # ------------------------------------------------------------------
    # Admin-Dashboard (Modal einmal öffnen, Inhalte reaktiv per output_ui aktualisieren)
    # ------------------------------------------------------------------
    def _read_admin_article_filters() -> tuple[str, bool]:
        search_q = ""
        only_orphans = False
        try:
            if hasattr(reactive, "isolate"):
                with reactive.isolate():
                    search_q = input.admin_article_search() or ""
                    only_orphans = bool(input.admin_only_orphans())
            else:
                search_q = input.admin_article_search() or ""
                only_orphans = bool(input.admin_only_orphans())
        except Exception:
            pass
        return search_q, only_orphans

    async def _render_admin_articles_table() -> ui.Tag:
        _ = admin_refresh_tick.get() if admin_refresh_tick is not None else 0
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return ui.span()

        search_q, only_orphans = _read_admin_article_filters()
        articles = await asyncio.to_thread(list_admin_articles, search_q, only_orphans=only_orphans)

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

        return ui.div(
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
        )

    async def _render_admin_users_table() -> ui.Tag:
        _ = admin_refresh_tick.get() if admin_refresh_tick is not None else 0
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return ui.span()

        users = await asyncio.to_thread(list_known_users)
        user_rows = []
        for u in users:
            uid = u["user_id"]
            is_act = bool(u.get("is_active", True))
            can_del = bool(u.get("can_delete", False))
            alias_txt = u.get("display_name") or uid
            status_badge = (
                ui.span("Aktiv", style="color:#065F46;background:#D1FAE5;padding:2px 7px;border-radius:999px;font-size:11px;font-weight:600;")
                if is_act
                else ui.span("Deaktiviert", style="color:#991B1B;background:#FEE2E2;padding:2px 7px;border-radius:999px;font-size:11px;font-weight:600;")
            )
            toggle_btn = ui.tags.button(
                "Deaktivieren" if is_act else "Reaktivieren",
                type="button",
                class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                onclick=f"Shiny.setInputValue('lukb_admin_toggle_user_active', {{user_id: {json.dumps(uid)}, is_active: {'false' if is_act else 'true'}, ts: Date.now()}}, {{priority:'event'}});",
            )
            del_reason = (
                "Konto endgültig löschen (nur möglich ohne zugewiesene/publizierte Artikel)"
                if can_del
                else (
                    "Nicht löschbar: Benutzer hat noch publizierte Artikel auf dem Portal (bitte deaktivieren)"
                    if u.get("active_published_count", 0) > 0
                    else (
                        "Nicht löschbar: Benutzer hat noch zugewiesene Artikel (bitte deaktivieren)"
                        if u.get("assigned_article_count", 0) > 0
                        else "System-/Env-Konto kann nicht gelöscht werden"
                    )
                )
            )
            del_btn = (
                ui.tags.button(
                    "Löschen",
                    type="button",
                    class_="btn-lukb btn-lukb-danger btn-lukb-sm",
                    title=del_reason,
                    onclick=f"Shiny.setInputValue('lukb_admin_delete_user', {{user_id: {json.dumps(uid)}, ts: Date.now()}}, {{priority:'event'}});",
                )
                if can_del
                else ui.tags.button(
                    "Löschen",
                    type="button",
                    disabled="disabled",
                    class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    style="opacity:0.45;cursor:not-allowed;",
                    title=del_reason,
                )
            )
            user_rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.button(
                            uid,
                            type="button",
                            title="Klicken, um Benutzer zum Bearbeiten zu laden",
                            style="background:none;border:none;padding:0;color:#005A9C;font-weight:600;cursor:pointer;text-decoration:underline;text-align:left;",
                            onclick=f"Shiny.setInputValue('lukb_admin_select_user_for_role', {{user_id: {json.dumps(uid)}, ts: Date.now()}}, {{priority:'event'}});",
                        ),
                        style="padding:5px 8px;",
                    ),
                    ui.tags.td(alias_txt, style="padding:5px 8px;"),
                    ui.tags.td("Ja" if u["is_admin"] else "Nein", style="padding:5px 8px;"),
                    ui.tags.td("Ja" if u["can_publish"] else "Nein", style="padding:5px 8px;"),
                    ui.tags.td(status_badge, style="padding:5px 8px;"),
                    ui.tags.td(u.get("source", ""), style="padding:5px 8px;color:#5A687C;font-size:12px;"),
                    ui.tags.td(
                        ui.div(toggle_btn, del_btn, style="display:flex;gap:6px;justify-content:flex-end;"),
                        style="padding:5px 8px;text-align:right;",
                    ),
                )
            )

        return ui.div(
            _build_known_users_datalist(users, "lukb-admin-users-datalist"),
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Benutzer", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        ui.tags.th("Alias / Name", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        ui.tags.th("Admin", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        ui.tags.th("Publizieren", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        ui.tags.th("Status", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        ui.tags.th("Quelle", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        ui.tags.th("Aktionen", style="text-align:right;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                    )
                ),
                ui.tags.tbody(*user_rows),
                style="width:100%;border-collapse:collapse;font-size:12.5px;",
            ),
        )

    async def _render_admin_publications_audit() -> ui.Tag:
        _ = admin_refresh_tick.get() if admin_refresh_tick is not None else 0
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return ui.span()

        def _load_audit_and_pub():
            return (
                list_audit_log(60),
                get_admin_publication_overview(),
                list_publication_jobs(30),
            )

        audit_entries, pub_overview, pub_jobs = await asyncio.to_thread(_load_audit_and_pub)

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

        pub_rows = []
        for po in pub_overview[:30]:
            draft_badge = f"v{po['draft_version']} ({po['status']})" + (" · ⚠️ neuer Entwurf" if po["has_newer_draft"] else "")
            rev_badge = f"Rev #{po['approved_revision_id']}" if po["approved_revision_id"] else "—"
            live_badge = f"Snap #{po['live_snapshot_id']} (v{po['live_version']})" if po["live_snapshot_id"] else "Offline"
            job_badge = f"#{po['latest_job_id']} {po['latest_job_action']} ({po['latest_job_status']})" if po["latest_job_id"] else "—"
            pub_rows.append(
                ui.tags.tr(
                    ui.tags.td(po["title"], style="font-weight:600;padding:5px 8px;"),
                    ui.tags.td(draft_badge, style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(rev_badge, style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(live_badge, style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(job_badge, style="padding:5px 8px;font-size:12px;"),
                )
            )

        job_rows = []
        for jb in pub_jobs:
            action_btn = ui.span("")
            if jb["status"] in ("unknown", "deploying") and jb["connect_task_id"]:
                action_btn = ui.tags.button(
                    "Task prüfen",
                    type="button",
                    class_="btn-lukb btn-lukb-ghost btn-lukb-sm",
                    onclick=f"Shiny.setInputValue('lukb_admin_poll_job', {jb['id']}, {{priority:'event'}});",
                )
            elif jb["status"] == "failed":
                action_btn = ui.tags.button(
                    "Wiederholen",
                    type="button",
                    class_="btn-lukb btn-lukb-primary btn-lukb-sm",
                    onclick=f"Shiny.setInputValue('lukb_admin_retry_job', {jb['id']}, {{priority:'event'}});",
                )
            job_rows.append(
                ui.tags.tr(
                    ui.tags.td(f"#{jb['id']} (Versuch {jb['attempt']})", style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(f"{jb['action']} · {jb['target_channel']}", style="padding:5px 8px;font-size:12px;"),
                    ui.tags.td(jb["status"], style="padding:5px 8px;font-size:12px;font-weight:600;"),
                    ui.tags.td(jb["error_message"][:100] or "—", style="padding:5px 8px;font-size:11.5px;color:#991B1B;"),
                    ui.tags.td(action_btn, style="padding:5px 8px;text-align:right;"),
                )
            )

        return ui.div(
            ui.h6("Publikationsstand (Entwurf · Freigabe · Live)", style="margin:8px 0 6px 0;color:#002855;font-weight:600;"),
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Artikel", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Entwurf", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Freigabe", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Live-Fassung", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Jüngster Auftrag", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        )
                    ),
                    ui.tags.tbody(*pub_rows),
                    style="width:100%;border-collapse:collapse;font-size:12.5px;",
                ),
                style="max-height:170px;overflow-y:auto;border:1px solid #D6DEE8;border-radius:6px;margin-bottom:12px;",
            ),
            ui.h6("Publikationsaufträge & Fehlerdetails", style="margin:0 0 6px 0;color:#002855;font-weight:600;"),
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Auftrag", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Aktion / Ziel", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Status", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("Fehler / Hinweis", style="text-align:left;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                            ui.tags.th("", style="text-align:right;padding:5px 8px;border-bottom:1px solid #D6DEE8;"),
                        )
                    ),
                    ui.tags.tbody(*job_rows),
                    style="width:100%;border-collapse:collapse;font-size:12.5px;",
                ),
                style="max-height:160px;overflow-y:auto;border:1px solid #D6DEE8;border-radius:6px;margin-bottom:12px;",
            ),
            ui.h6("Rollen- & Zuweisungsprotokoll", style="margin:0 0 6px 0;color:#002855;font-weight:600;"),
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
                style="max-height:170px;overflow-y:auto;border:1px solid #D6DEE8;border-radius:6px;",
            ),
        )

    if callable(output):
        output(id="admin_articles_table_ui")(render.ui(_render_admin_articles_table))
        output(id="admin_users_table_ui")(render.ui(_render_admin_users_table))
        output(id="admin_publications_audit_ui")(render.ui(_render_admin_publications_audit))

    async def _show_admin_dashboard(active_tab: str = "articles") -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            ui.notification_show("Nur Administratoren haben Zugriff auf das Admin-Dashboard.", type="warning", duration=5)
            return

        _bump_admin_refresh()
        ui.modal_show(
            ui.modal(
                ui.navset_tab(
                    ui.nav_panel(
                        "Artikel und Benutzer",
                        ui.div(
                            ui.div(
                                ui.input_text("admin_article_search", "Artikel suchen", value="", placeholder="Titel, Autor, Kategorie…"),
                                ui.input_checkbox("admin_only_orphans", "Nur verwaiste Artikel anzeigen", value=False),
                                ui.input_action_button("btn_admin_refresh", "Filter anwenden", class_="btn-lukb btn-lukb-ghost btn-lukb-sm"),
                                style="display:flex;gap:12px;align-items:flex-end;margin:10px 0;",
                            ),
                            ui.output_ui("admin_articles_table_ui"),
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
                                ui.tags.script(
                                    "setTimeout(function(){var el=document.getElementById('admin_assign_user_id');if(el)el.setAttribute('list','lukb-admin-users-datalist');},0);"
                                ),
                                ui.input_action_button("btn_admin_apply_article_perm", "Zuordnung ausführen", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                                style="background:#F4F7FA;padding:10px;border-radius:6px;border:1px solid #D6DEE8;margin-bottom:12px;",
                            ),
                            ui.div(
                                ui.h6("Globale Benutzerrollen & Konten (Admin, Publizieren & Alias)", style="margin:0 0 8px 0;color:#002855;font-weight:600;"),
                                ui.div(
                                    ui.input_text("admin_role_user_id", "Benutzerkennung", placeholder="z. B. editor@lukb.ch"),
                                    ui.input_text("admin_role_display_name", "Alias / Name", placeholder="z. B. Max Muster"),
                                    ui.input_checkbox("admin_role_is_admin", "Admin-Zugriff", value=False),
                                    ui.input_checkbox("admin_role_can_publish", "Darf publizieren", value=False),
                                    ui.input_action_button("btn_admin_save_user_role", "Rolle speichern", class_="btn-lukb btn-lukb-primary btn-lukb-sm"),
                                    style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px;",
                                ),
                                ui.output_ui("admin_users_table_ui"),
                                style="background:#FFFFFF;padding:10px;border-radius:6px;border:1px solid #D6DEE8;",
                            ),
                        ),
                    ),
                    ui.nav_panel(
                        "Publikationen und Protokoll",
                        ui.output_ui("admin_publications_audit_ui"),
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
    @reactive.event(input.lukb_open_admin_dashboard)
    async def _on_open_admin_dashboard() -> None:
        await _show_admin_dashboard("articles")

    @reactive.effect
    @reactive.event(input.btn_admin_refresh)
    async def _on_refresh_admin_dashboard() -> None:
        _bump_admin_refresh()

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
        await broadcast_article_list_to_all(exclude_session_id=state.session_id)
        _bump_perm_refresh()
        await state.send_article_list(state.current_article_id.get())
        _bump_admin_refresh()
        ui.notification_show("Artikelzuordnung aktualisiert.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_admin_select_user_for_role)
    async def _on_admin_select_user_for_role() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        payload = input.lukb_admin_select_user_for_role()
        if not isinstance(payload, dict):
            return
        target_uid = normalize_user_id(str(payload.get("user_id", "")))
        if not target_uid:
            return
        users = await asyncio.to_thread(list_known_users)
        match = next((u for u in users if u["user_id"] == target_uid), None)
        if not match:
            return
        ui.update_text("admin_role_user_id", value=match["user_id"])
        ui.update_text("admin_role_display_name", value=match.get("display_name") or "")
        ui.update_checkbox("admin_role_is_admin", value=bool(match.get("is_admin")))
        ui.update_checkbox("admin_role_can_publish", value=bool(match.get("can_publish")))

    @reactive.effect
    @reactive.event(input.btn_admin_save_user_role)
    async def _on_admin_save_user_role() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        target_uid = (input.admin_role_user_id() or "").strip()
        display_name = (input.admin_role_display_name() or "").strip()
        is_adm = bool(input.admin_role_is_admin())
        can_pub = bool(input.admin_role_can_publish())
        res = await asyncio.to_thread(
            set_global_user_role,
            target_uid,
            is_admin=is_adm,
            can_publish=can_pub,
            actor_user=state.current_user_id,
            display_name=display_name,
        )
        if not res.get("success"):
            ui.notification_show(res.get("error", "Fehler beim Speichern der Rolle"), type="warning", duration=5)
            return
        _bump_perm_refresh()
        _bump_admin_refresh()
        ui.notification_show(f"Globale Rolle für {res['user_id']} gespeichert.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_admin_toggle_user_active)
    async def _on_admin_toggle_user_active() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        payload = input.lukb_admin_toggle_user_active()
        if not isinstance(payload, dict):
            return
        target_uid = str(payload.get("user_id", "")).strip()
        new_active = bool(payload.get("is_active", False))
        if not target_uid:
            return
        res = await asyncio.to_thread(
            set_user_active_status,
            target_uid,
            is_active=new_active,
            actor_user=state.current_user_id,
        )
        if not res.get("success"):
            ui.notification_show(res.get("error", "Aktion fehlgeschlagen"), type="warning", duration=5)
            return
        _bump_perm_refresh()
        _bump_admin_refresh()
        status_txt = "reaktiviert" if new_active else "deaktiviert"
        ui.notification_show(f"Benutzer {res['user_id']} {status_txt}.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_admin_delete_user)
    async def _on_admin_delete_user() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        payload = input.lukb_admin_delete_user()
        if not isinstance(payload, dict):
            return
        target_uid = str(payload.get("user_id", "")).strip()
        if not target_uid:
            return
        res = await asyncio.to_thread(delete_user_account, target_uid, state.current_user_id)
        if not res.get("success"):
            ui.notification_show(res.get("error", "Löschen nicht möglich"), type="warning", duration=5)
            return
        _bump_perm_refresh()
        _bump_admin_refresh()
        ui.notification_show(f"Benutzer {res['user_id']} gelöscht.", type="message", duration=3)

    @reactive.effect
    @reactive.event(input.lukb_admin_poll_job)
    async def _on_admin_poll_job() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        job_id = input.lukb_admin_poll_job()
        if not job_id:
            return
        res = await asyncio.to_thread(poll_publication_job, int(job_id))
        _bump_admin_refresh()
        if res.get("success"):
            ui.notification_show(f"Auftrag #{job_id} erfolgreich abgeschlossen.", type="message", duration=4)
        else:
            ui.notification_show(res.get("error", f"Auftrag #{job_id}: {res.get('state')}"), type="warning", duration=5)

    @reactive.effect
    @reactive.event(input.lukb_admin_retry_job)
    async def _on_admin_retry_job() -> None:
        if not await asyncio.to_thread(is_global_admin, state.current_user_id):
            return
        job_id = input.lukb_admin_retry_job()
        if not job_id:
            return
        res = await asyncio.to_thread(retry_publication_job, int(job_id), state.current_user_id)
        _bump_admin_refresh()
        if res.get("success"):
            ui.notification_show(f"Auftrag #{job_id} erfolgreich wiederholt.", type="message", duration=4)
        else:
            ui.notification_show(res.get("error", "Wiederholung fehlgeschlagen"), type="warning", duration=5)
