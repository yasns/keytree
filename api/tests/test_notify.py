import asyncio
from datetime import UTC, datetime

from app.db.models import StagedEdit
from app.notify import (
    archival_entry,
    build_mails,
    bundle_counts,
    decommission_entry,
    edit_entry,
    payload_counts,
)
from app.routers.commit import _CommitRow, _notification_entries


def test_payload_counts_reports_added_and_removed_lines():
    assert payload_counts("a\nb\n", "a\nc\nd\n") == (
        '<span style="color: #2e7d32;">+2</span> <span style="color: #c62828;">-1</span>'
    )


def test_payload_counts_is_zero_for_identical_payloads():
    assert payload_counts("a\nb\n", "a\nb\n") == (
        '<span style="color: #2e7d32;">+0</span> <span style="color: #c62828;">-0</span>'
    )


def test_payload_counts_is_empty_with_no_ancestor():
    assert payload_counts(None, "a\nb\n") == ""


def test_bundle_counts_counts_retargeted_added_and_removed_aliases():
    ancestor = {"a": 1, "b": 2, "c": 3}
    proposed = {"a": 1, "b": 9, "d": 4}  # b retargeted, c removed, d added
    assert bundle_counts(ancestor, proposed, self_key_id=99) == (
        '<span style="color: #2e7d32;">+2</span> <span style="color: #c62828;">-2</span>'
    )


def test_bundle_counts_none_sentinel_resolves_to_self_and_does_not_count_as_modified():
    ancestor = {"a": 42}
    proposed = {"a": None}  # this commit fills it with its own key, which already is 42
    assert bundle_counts(ancestor, proposed, self_key_id=42) == (
        '<span style="color: #2e7d32;">+0</span> <span style="color: #c62828;">-0</span>'
    )


def test_bundle_counts_is_empty_with_no_ancestor():
    assert bundle_counts(None, {"a": 1}, self_key_id=99) == ""


def test_edit_entry_strikes_the_base_version():
    entry = edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")
    assert entry.label_html == "ugt/board/prod/<s>v4</s> → v5"
    assert entry.detail == "New key"
    assert entry.link_text == "View changes"


def test_edit_entry_fork_has_no_base_to_strike():
    entry = edit_entry("ugt", "board", "test", None, 1, True, "fork it", "")
    assert entry.label_html == "ugt/board/test/v1"
    assert entry.detail == "Fork"
    assert entry.emoji == "\U0001f331"
    assert entry.link_text == "View key"


def test_archival_entry_strikes_when_archived():
    entry = archival_entry("ugt", "board", "old", True)
    assert entry.label_html == "<s>ugt/board/old</s>"
    assert entry.detail == "Archive mode"
    assert entry.link_text == "View mode"


def test_archival_entry_is_plain_when_unarchiving():
    entry = archival_entry("ugt", "board", "old", False)
    assert entry.label_html == "ugt/board/old"
    assert entry.detail == "Unarchive mode"


def test_decommission_entry_strikes_when_decommissioned():
    entry = decommission_entry("ugt", "board", "prod", "ugt/board/prod/v3", True)
    assert entry.label_html == "<s>ugt/board/prod/v3</s>"
    assert entry.detail == "Decommission key"
    assert entry.link_text == "View key"


def test_decommission_entry_is_plain_when_recommissioning():
    entry = decommission_entry("ugt", "board", "prod", "ugt/board/prod/v3", False)
    assert entry.label_html == "ugt/board/prod/v3"
    assert entry.detail == "Recommission key"


def test_build_mails_groups_by_subsystem_and_skips_unrecipiented_ones():
    ugt_entry = edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")
    calol1_entry = edit_entry("calol1", "board", "prod", 1, 2, False, "tune", "-0 +1")
    unmailed_entry = edit_entry("tcds", "board", "prod", 1, 2, False, "n/a", "")

    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [ugt_entry], "calol1": [calol1_entry], "tcds": [unmailed_entry]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}, "calol1": {"cms-keytree-calol1@cern.ch"}},
        {"ugt": "uGT", "calol1": "CaloL1"},
    )

    by_subject = {subject: (to, html) for to, subject, html in mails}
    assert len(mails) == 2
    assert any("uGT: 1 change by Jane Doe" in s for s in by_subject)
    assert any("CaloL1: 1 change by Jane Doe" in s for s in by_subject)
    assert not any("tcds" in s for s in by_subject)


def test_build_mails_subject_falls_back_to_slug_without_a_display_name():
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}},
        {},
    )
    _, subject, _ = mails[0]
    assert subject.startswith("[Keytree] ugt:")


def test_build_mails_author_line_falls_back_without_email():
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        None,
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}},
        {"ugt": "uGT"},
    )
    _, _, html = mails[0]
    assert "mailto:" not in html
    assert "jdoe" in html


def test_build_mails_escapes_comment_html():
    entry = edit_entry("ugt", "board", "prod", 4, 5, False, "<script>&", "-1 +2")
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [entry]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}},
        {"ugt": "uGT"},
    )
    _, _, html = mails[0]
    assert "<script>" not in html
    assert "&lt;script&gt;&amp;" in html


def test_build_mails_comment_stays_in_row_but_its_column_wraps():
    long_comment = "a rather long explanatory comment"
    entry = edit_entry("ugt", "board", "prod", 4, 5, False, long_comment, "-1 +2")
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [entry]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}},
        {"ugt": "uGT"},
    )
    _, _, html = mails[0]
    assert html.count("<tr>") == 2  # header row + one entry row, comment doesn't get its own
    assert long_comment in html
    assert 'width="240"' in html


def test_build_mails_renders_a_header_row():
    entry = edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [entry]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}},
        {"ugt": "uGT"},
    )
    _, _, html = mails[0]
    assert "<thead>" in html
    assert ">Change<" in html
    assert ">Key<" in html
    assert ">Diff<" in html
    assert ">Comment<" in html


def test_build_mails_disclaimer_names_the_subsystem_and_group():
    entry = edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [entry]},
        {"ugt": {"cms-keytree-ugt@cern.ch"}},
        {"ugt": "uGT"},
    )
    _, _, html = mails[0]
    disclaimer = html.rsplit("</table>", 1)[1]  # disclaimer sits after the table
    assert "You received this email because" in disclaimer
    assert "uGT" in disclaimer  # display name, not slug
    assert "cms-keytree-ugt@cern.ch" in disclaimer
    assert "e-group (" in disclaimer  # singular for one recipient group


def test_build_mails_disclaimer_pluralizes_multiple_groups():
    entry = edit_entry("ugt", "board", "prod", 4, 5, False, "fix", "-1 +2")
    mails = build_mails(
        "Jane Doe",
        "jdoe",
        "jdoe@cern.ch",
        datetime(2026, 9, 20, 12, 32, tzinfo=UTC),
        {"ugt": [entry]},
        {"ugt": {"cms-keytree-ugt@cern.ch", "keytree-admins@cern.ch"}},
        {"ugt": "uGT"},
    )
    _, _, html = mails[0]
    disclaimer = html.rsplit("</table>", 1)[1]
    assert "e-groups (" in disclaimer
    assert "are registered" in disclaimer
    assert "cms-keytree-ugt@cern.ch" in disclaimer
    assert "keytree-admins@cern.ch" in disclaimer


def test_notification_entries_excludes_external_edits():
    edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=1,
        base_key_id=None,
        expected_version=1,
        proposed_payload="external-value",
    )
    rows = [_CommitRow(edit, "ugt", "board", "prod", None, 10, None, 0, "external")]

    entries = asyncio.run(
        _notification_entries(
            rows,
            keys=[],
            archivals=[],
            archival_ctx={},
            decommissions=[],
            decommission_ctx={},
            session=None,
        )
    )

    assert entries == {}
