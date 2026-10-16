"""Tests for mask.py, against the synthetic files in ml/testdata/ (fake data only)."""

import csv
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mask  # noqa: E402
from smartmute_data import is_call_notification  # noqa: E402

TESTDATA = Path(__file__).resolve().parents[1] / "testdata"
EXPORT = TESTDATA / "notification_log_synthetic.csv"
REVIEW = TESTDATA / "notification_log_synthetic_review.csv"


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def non_call_rows(path: Path) -> list[dict]:
    return [r for r in read_rows(path)
            if not is_call_notification(r["raw_template"], r["raw_category"], r["app_package"])]


def run(input_path: Path, tmp_path: Path, *extra: str, output: str = "masked.csv") -> int:
    return mask.main(["--input", str(input_path), "--output", str(tmp_path / output),
                      "--mapping", str(tmp_path / "private" / "mapping.csv"), *extra])


@pytest.fixture
def masked(tmp_path: Path) -> list[dict]:
    assert run(REVIEW, tmp_path) == 0
    return read_rows(tmp_path / "masked.csv")


@pytest.fixture
def mapping(masked, tmp_path: Path) -> dict[str, str]:
    return {r["pseudonym"]: r["original"] for r in read_rows(tmp_path / "private" / "mapping.csv")}


def originals_of(rows: list[dict]) -> set[str]:
    return {r[c] for r in rows for c in ("sender_id", "raw_conversation_title", "notification_key") if r[c]}


# --- columns ------------------------------------------------------------------------

def test_only_allowlisted_columns(masked):
    columns = list(masked[0].keys())
    assert set(columns) <= set(mask.ALLOWLIST)
    assert columns == [c for c in mask.ALLOWLIST if c in columns]  # allowlist order
    assert "message_text" not in columns and "raw_sub_text" not in columns


def test_unknown_columns_dropped(tmp_path):
    rows = read_rows(EXPORT)
    for row in rows:
        row["contact_phone"] = "+37300000123"
    extended = tmp_path / "extended.csv"
    with extended.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    assert run(extended, tmp_path) == 0
    out = (tmp_path / "masked.csv").read_text(encoding="utf-8")
    assert "contact_phone" not in out and "+37300000123" not in out


def test_role_kept(masked):
    source = {r["message_id"]: r for r in read_rows(REVIEW)}
    assert "role" in masked[0]
    assert [r["role"] for r in masked] == [source[r["message_id"]]["role"] for r in masked]


def test_export_without_role_works(tmp_path, capsys):
    assert run(EXPORT, tmp_path) == 0
    assert "role" not in read_rows(tmp_path / "masked.csv")[0]
    assert "role column: not in input" in capsys.readouterr().out


def test_pass_through_columns_identical(masked):
    source = {r["message_id"]: r for r in non_call_rows(REVIEW)}
    changed = set(mask.NAME_COLUMNS + mask.KEY_COLUMNS + mask.TEXT_FEATURES)
    assert sorted(r["message_id"] for r in masked) == sorted(source)
    for row in masked:
        for column, value in row.items():
            if column not in changed:
                assert value == source[row["message_id"]][column], column


# --- derived text features -----------------------------------------------------------

def test_text_features(masked):
    source = {r["message_id"]: r["message_text"] for r in read_rows(REVIEW)}
    by_text = {source[r["message_id"]]: r for r in masked}
    assert by_text["Are you coming tonight?"]["has_qmark"] == "1"
    assert by_text["ok"] == {**by_text["ok"], "has_qmark": "0", "text_len": "2", "is_emoji_only": "0"}
    assert by_text["😂😂 👍🏽"]["is_emoji_only"] == "1"
    assert by_text["ok, I'll wait at the entrance"]["is_emoji_only"] == "0"
    assert by_text[""]["text_len"] == "0" and by_text[""]["is_emoji_only"] == "0"
    assert by_text['Bring the "big" bag,\nand the keys']["text_len"] == str(len('Bring the "big" bag,\nand the keys'))
    assert by_text["Ты где?"]["text_len"] == "7"  # characters, not UTF-8 bytes


# --- pseudonyms ---------------------------------------------------------------------

def test_senders_pseudonymized_consistently(masked, mapping):
    source = {r["message_id"]: r for r in non_call_rows(REVIEW)}
    for row in masked:
        original = source[row["message_id"]]
        assert mapping.get(row["sender_id"], "") == original["sender_id"]
        assert mapping.get(row["raw_conversation_title"], "") == original["raw_conversation_title"]
        assert mapping.get(row["notification_key"], "") == original["notification_key"]
    names = {r["sender_id"] for r in masked if r["sender_id"]}
    assert all(n.startswith("S") for n in names)
    assert len(names) == len({r["sender_id"] for r in source.values() if r["sender_id"]})


def test_call_notifications_dropped(tmp_path, capsys):
    assert run(REVIEW, tmp_path) == 0
    kept = {r["message_id"] for r in read_rows(tmp_path / "masked.csv")}
    assert kept == {r["message_id"] for r in non_call_rows(REVIEW)}
    assert "call notifications dropped: 2" in capsys.readouterr().out


def test_empty_sender_stays_empty(masked):
    assert sum(r["sender_id"] == "" for r in masked) == 1


def test_title_shares_sender_namespace(masked):
    """A group whose title is also its sender_id gets one pseudonym in both columns."""
    group = [r for r in masked if r["raw_is_group_conversation"] == "1" and r["sender_id"] == r["raw_conversation_title"]]
    assert group and all(r["sender_id"].startswith("S") for r in group)
    separate = [r for r in masked if r["raw_conversation_title"] and r["sender_id"] != r["raw_conversation_title"]]
    assert separate  # "Greg Member" in "Hiking Club Demo"


def test_pseudonyms_numbered_in_time_order(masked):
    first_seen = []
    for row in sorted(masked, key=lambda r: (int(r["timestamp"]), int(r["message_id"]))):
        for value in (row["sender_id"], row["raw_conversation_title"]):
            if value and value not in first_seen:
                first_seen.append(value)
    assert first_seen == [f"S{i:02d}" for i in range(1, len(first_seen) + 1)]


def test_mapping_reused_across_runs(tmp_path, masked, mapping):
    # Second run on the export alone: same people, same pseudonyms, nothing new.
    assert run(EXPORT, tmp_path, output="second.csv") == 0
    second = read_rows(tmp_path / "second.csv")
    assert [r["sender_id"] for r in second] == [r["sender_id"] for r in masked]
    again = {r["pseudonym"]: r["original"] for r in read_rows(tmp_path / "private" / "mapping.csv")}
    assert again == mapping


def test_mapping_extended_for_new_sender(tmp_path, masked, mapping):
    rows = read_rows(REVIEW)
    rows.append({**rows[0], "message_id": "999", "sender_id": "New Person Demo"})
    newer = tmp_path / "newer.csv"
    with newer.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    assert run(newer, tmp_path, output="newer_masked.csv") == 0
    again = {r["pseudonym"]: r["original"] for r in read_rows(tmp_path / "private" / "mapping.csv")}
    assert {k: v for k, v in again.items() if k in mapping} == mapping
    new = set(again) - set(mapping)
    assert len(new) == 1 and again[new.pop()] == "New Person Demo"


# --- leak check ---------------------------------------------------------------------

def test_no_original_identifier_in_output(tmp_path, masked):
    out = (tmp_path / "masked.csv").read_text(encoding="utf-8")
    for original in originals_of(read_rows(REVIEW)):
        if not mask._is_short_number(original):
            assert original not in out
    assert "37300000099" not in out  # phone number inside the WhatsApp key


def test_short_number_sender_not_a_false_alarm(tmp_path):
    """"7444" may appear inside a timestamp by chance; only a whole cell counts as a leak."""
    path = tmp_path / "f.csv"
    path.write_text("timestamp,sender_id\r\n1791000074440,S01\r\n", encoding="utf-8")
    assert mask.find_leaks(path, {"7444"}) == {}
    path.write_text("timestamp,sender_id\r\n1791000074440,7444\r\n", encoding="utf-8")
    assert mask.find_leaks(path, {"7444"}) == {"sender_id": 1}


def test_find_leaks_sees_quoted_values(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text('a,role\r\n1,"Name ""Nick"" Demo"\r\n', encoding="utf-8")
    assert mask.find_leaks(path, {'Name "Nick" Demo'}) == {"role": 1}


def test_leak_fails_loudly_and_writes_nothing(tmp_path, monkeypatch, capsys):
    # Simulate a bad allowlist: message_text contains "Carol Demo reacted 👍 ...".
    monkeypatch.setattr(mask, "ALLOWLIST", mask.ALLOWLIST + ["message_text"])
    assert run(REVIEW, tmp_path) == 3
    err = capsys.readouterr().err
    assert "MASKING FAILED" in err and "message_text" in err
    assert not (tmp_path / "masked.csv").exists()
    assert not (tmp_path / "private" / "mapping.csv").exists()
    assert list(tmp_path.glob(".masking-*")) == []


def test_role_equal_to_a_name_is_caught(tmp_path):
    rows = read_rows(REVIEW)
    rows[0]["role"] = "Bob Sample"  # a name typed into the role column
    bad = tmp_path / "bad_role.csv"
    with bad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    assert run(bad, tmp_path) == 3
    assert not (tmp_path / "masked.csv").exists()


# --- safety -------------------------------------------------------------------------

def test_input_never_modified(tmp_path):
    before = hashlib.sha256(REVIEW.read_bytes()).hexdigest()
    assert run(REVIEW, tmp_path) == 0
    assert hashlib.sha256(REVIEW.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("which", ["output", "mapping"])
def test_refuses_to_overwrite_input(tmp_path, which):
    copy = tmp_path / "export.csv"
    copy.write_bytes(EXPORT.read_bytes())
    paths = {"output": tmp_path / "o.csv", "mapping": tmp_path / "m.csv", which: copy}
    assert mask.main(["--input", str(copy), "--output", str(paths["output"]),
                      "--mapping", str(paths["mapping"])]) == 2
    assert copy.read_bytes() == EXPORT.read_bytes()


def test_refuses_mapping_equal_to_output(tmp_path):
    same = tmp_path / "same.csv"
    assert mask.main(["--input", str(EXPORT), "--output", str(same), "--mapping", str(same)]) == 2


def test_refuses_existing_output_without_flag(tmp_path):
    (tmp_path / "masked.csv").write_text("keep me")
    assert run(REVIEW, tmp_path) == 2
    assert (tmp_path / "masked.csv").read_text() == "keep me"
    assert run(REVIEW, tmp_path, "--overwrite") == 0


def test_rejects_malformed_mapping(tmp_path):
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "mapping.csv").write_text("name,value\r\nx,y\r\n", encoding="utf-8")
    assert run(REVIEW, tmp_path) == 2


def test_rejects_wrong_schema(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\r\n1,2\r\n", encoding="utf-8")
    assert run(bad, tmp_path) == 2


def test_output_format(tmp_path, masked):
    raw = (tmp_path / "masked.csv").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.split(b"\n", 1)[0].endswith(b"\r")


def test_never_prints_text_or_identifiers(tmp_path, capsys):
    assert run(REVIEW, tmp_path) == 0
    captured = capsys.readouterr()
    printed = captured.out + captured.err
    for row in read_rows(REVIEW):
        for column in ("message_text", "sender_id", "raw_conversation_title", "raw_sub_text", "notification_key"):
            if len(row[column]) >= 3:
                assert row[column] not in printed, f"{column} leaked to stdout/stderr"
