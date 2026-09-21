import difflib
import html
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from app.config import settings

_ZURICH = ZoneInfo("Europe/Zurich")


@dataclass
class Entry:
    emoji: str
    label_html: str
    detail: str
    counts: str
    comment: str
    url: str
    link_text: str


def _counts_html(added: int, removed: int) -> str:
    return (
        f'<span style="color: #2e7d32;">+{added}</span> '
        f'<span style="color: #c62828;">-{removed}</span>'
    )


def payload_counts(ancestor: str | None, proposed: str) -> str:
    """'+added -removed' lines vs the ancestor, colored; '' if no ancestor to diff against."""
    if ancestor is None:
        return ""
    removed = added = 0
    opcodes = difflib.SequenceMatcher(
        a=ancestor.splitlines(), b=proposed.splitlines(), autojunk=False
    ).get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return _counts_html(added, removed)


def bundle_counts(
    ancestor: dict[str, int] | None,
    proposed: dict[str, int | None],
    self_key_id: int,
) -> str:
    """'+added -removed' aliases vs the ancestor, colored; a retarget counts as both."""
    if ancestor is None:
        return ""
    resolved = {
        alias: (self_key_id if target is None else target) for alias, target in proposed.items()
    }
    aliases = ancestor.keys() | resolved.keys()
    removed = added = 0
    for alias in aliases:
        old, new = ancestor.get(alias), resolved.get(alias)
        if old == new:
            continue
        removed += alias in ancestor
        added += alias in resolved
    return _counts_html(added, removed)


def _escaped_path(subsystem_name: str, node_name: str, mode_name: str) -> str:
    return f"{html.escape(subsystem_name)}/{html.escape(node_name)}/{html.escape(mode_name)}"


def _url(*parts: str) -> str:
    return "/".join([settings.app_base_url, *parts])


def edit_entry(
    subsystem_name: str,
    node_name: str,
    mode_name: str,
    base_version: int | None,
    new_version: int,
    is_fork: bool,
    comment: str,
    counts: str,
) -> Entry:
    path = _escaped_path(subsystem_name, node_name, mode_name)
    if base_version is not None:
        label_html = f"{path}/<s>v{base_version}</s> → v{new_version}"
        diff = urlencode({"diff": f"{mode_name}/v{new_version}"}, quote_via=quote)
        url = f"{_url(subsystem_name, node_name, mode_name, f'v{base_version}')}?{diff}"
        link_text = "View changes"
    else:
        label_html = f"{path}/v{new_version}"
        url = _url(subsystem_name, node_name, mode_name, f"v{new_version}")
        link_text = "View key"
    return Entry(
        emoji="\U0001f331" if is_fork else "\U0001f511",  # 🌱 fork, 🔑 new version
        label_html=label_html,
        detail="Fork" if is_fork else "New key",
        counts=counts,
        comment=comment,
        url=url,
        link_text=link_text,
    )


def archival_entry(subsystem_name: str, node_name: str, mode_name: str, archived: bool) -> Entry:
    path = _escaped_path(subsystem_name, node_name, mode_name)
    return Entry(
        emoji="\U0001f4e6" if archived else "\U0001f4e4",  # 📦 archive, 📤 unarchive
        label_html=f"<s>{path}</s>" if archived else path,
        detail="Archive mode" if archived else "Unarchive mode",
        counts="",
        comment="",
        url=_url(subsystem_name, node_name, mode_name),
        link_text="View mode",
    )


def decommission_entry(
    subsystem_name: str, node_name: str, mode_name: str, label: str, decommissioned: bool
) -> Entry:
    escaped = html.escape(label)
    return Entry(
        emoji="⛔" if decommissioned else "♻️",  # ⛔ decommission, ♻️ recommission
        label_html=f"<s>{escaped}</s>" if decommissioned else escaped,
        detail="Decommission key" if decommissioned else "Recommission key",
        counts="",
        comment="",
        url=_url(label),
        link_text="View key",
    )


def _author_line(
    display_name: str, cern_login: str, email: str | None, committed_at: datetime
) -> str:
    when = committed_at.astimezone(_ZURICH).strftime("%Y-%m-%d %H:%M %Z")
    login = html.escape(cern_login)
    who = f'<a href="mailto:{html.escape(email)}">{login}</a>' if email else login
    return f"{html.escape(display_name)} ({who}) — {html.escape(when)}"


_CELL = "padding: 6px 8px; border-bottom: 1px solid #ddd;"
_HEADER_CELL = f"{_CELL} border-bottom: 2px solid #999;"


def _header_row() -> str:
    headers = ["", "Change", "Key", "Diff", "Comment", ""]
    cells = "".join(f'<th align="left" style="{_HEADER_CELL}">{h}</th>' for h in headers)
    return f"<thead><tr>{cells}</tr></thead>"


def _entry_row(entry: Entry) -> str:
    return (
        "<tr>"
        f'<td align="left" style="{_CELL}">{entry.emoji}</td>'
        f'<td align="left" style="{_CELL}">{entry.detail}</td>'
        f'<td align="left" style="{_CELL}">{entry.label_html}</td>'
        f'<td align="left" style="{_CELL}">{entry.counts}</td>'
        f'<td align="left" width="240" style="{_CELL}">{html.escape(entry.comment)}</td>'
        f'<td align="left" style="{_CELL}"><a href="{html.escape(entry.url)}">'
        f"{html.escape(entry.link_text)}</a></td>"
        "</tr>"
    )


def _disclaimer(subsystem_label: str, groups: list[str]) -> str:
    noun = "e-group" if len(groups) == 1 else "e-groups"
    verb = "is" if len(groups) == 1 else "are"
    group_list = ", ".join(html.escape(g) for g in groups)
    return (
        '<p style="color: #777; font-size: 12px; margin-top: 16px;">'
        f"You received this email because your {noun} ({group_list}) {verb} registered on a "
        f"Keytree role with write access to the {html.escape(subsystem_label)} subsystem.</p>"
    )


def _render(author_line: str, entries: list[Entry], subsystem_label: str, groups: list[str]) -> str:
    rows = "".join(_entry_row(e) for e in entries)
    return (
        f"<p>{author_line}</p>"
        f'<table cellspacing="0" width="100%" style="border-collapse: collapse;">'
        f"{_header_row()}<tbody>{rows}</tbody></table>"
        f"{_disclaimer(subsystem_label, groups)}"
    )


def build_mails(
    display_name: str,
    cern_login: str,
    email: str | None,
    committed_at: datetime,
    entries_by_subsystem: dict[str, list[Entry]],
    recipients: dict[str, set[str]],
    subsystem_display_names: dict[str, str],
) -> list[tuple[list[str], str, str]]:
    """One mail per subsystem that has both entries and at least one recipient."""
    author_line = _author_line(display_name, cern_login, email, committed_at)
    mails: list[tuple[list[str], str, str]] = []
    for subsystem, subsystem_entries in entries_by_subsystem.items():
        to = sorted(recipients.get(subsystem, set()))
        if not to:
            continue
        n = len(subsystem_entries)
        subsystem_label = subsystem_display_names.get(subsystem, subsystem)
        subject = (
            f"[Keytree] {subsystem_label}: {n} change{'' if n == 1 else 's'} by {display_name}"
        )
        mails.append((to, subject, _render(author_line, subsystem_entries, subsystem_label, to)))
    return mails
