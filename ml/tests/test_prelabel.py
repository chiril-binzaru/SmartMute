"""Tests for prelabel.py, against ml/testdata/notification_log_synthetic.csv (fake data only)."""

import csv
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prelabel  # noqa: E402
from smartmute_data import is_call_notification  # noqa: E402

SYNTHETIC = Path(__file__).resolve().parents[1] / "testdata" / "notification_log_synthetic.csv"


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "review" / "prelabeled.csv"


@pytest.fixture
def result(output: Path) -> list[dict]:
    assert prelabel.main(["--input", str(SYNTHETIC), "--output", str(output)]) == 0
    return read_rows(output)


def is_call(row: dict) -> bool:
    return is_call_notification(row["raw_template"], row["raw_category"], row["app_package"])


def by_text(rows: list[dict]) -> dict[str, dict]:
    return {r["message_text"]: r for r in rows}


# --- heuristics ---------------------------------------------------------------------

@pytest.mark.parametrize("text, has_picture, expected", [
    ("hello there", "0", "text"),
    ("", "1", "photo"),
    ("", "0", "file"),
    ("📷 Photo", "1", "photo"),
    ("Фото", "0", "photo"),
    ("Sticker", "0", "sticker"),
    ("🎤 Voice message", "0", "voice"),
    ("🎤 Голосовое сообщение", "0", "voice"),
    ("Mesaj vocal", "0", "voice"),
    ("Видео", "0", "video"),
    ("GIF", "0", "video"),
    ("Fișier", "0", "file"),
    ("look at this view", "1", "photo"),
    ("😂😂 👍🏽", "0", "emoji_only"),
    ("👨‍👩‍👧", "0", "emoji_only"),
    ("ok 👍", "0", "text"),
    ("Carol reacted 👍 to your message", "0", "reaction"),
    ("Ира отреагировала ❤️ на ваше сообщение", "0", "reaction"),
    ("a photo of the board, see?", "0", "text"),  # "photo" inside a sentence isn't a placeholder
])
def test_content_type(text, has_picture, expected):
    assert prelabel.derive_content_type(text, has_picture) == expected


@pytest.mark.parametrize("package, title, is_group, expected", [
    ("org.telegram.messenger", "", "0", "dm"),
    ("org.telegram.messenger", "", "1", "group"),
    ("com.whatsapp", "Family Chat", "0", "group"),
    ("com.whatsapp", "  ", "", "dm"),
    ("com.google.android.gm", "", "", "dm"),
    ("com.miui.securitycenter", "", "", "broadcast"),
])
def test_chat_type(package, title, is_group, expected):
    assert prelabel.derive_chat_type(package, title, is_group) == expected


@pytest.mark.parametrize("previous, expected", [
    (None, "neutral"),
    ("Are you coming?", "last_msg_was_question"),
    ("ок", "last_msg_was_answer"),
    ("OK!", "last_msg_was_answer"),
    ("ok, but later", "neutral"),
    ("see you tomorrow", "neutral"),
])
def test_conversation_state(previous, expected):
    assert prelabel.derive_conversation_state(previous) == expected


# --- end to end on the synthetic export ---------------------------------------------

def test_every_row_written_once(result):
    source = [r for r in read_rows(SYNTHETIC) if not is_call(r)]
    assert sorted(r["message_id"] for r in result) == sorted(r["message_id"] for r in source)


def test_call_notifications_dropped(output, capsys):
    assert prelabel.main(["--input", str(SYNTHETIC), "--output", str(output)]) == 0
    calls = sum(is_call(r) for r in read_rows(SYNTHETIC))
    assert calls == 2
    assert not any(is_call(r) for r in read_rows(output))
    assert f"call notifications dropped: {calls}" in capsys.readouterr().out


def test_columns_kept_in_order_plus_rule(result):
    with SYNTHETIC.open(encoding="utf-8") as f:
        source_header = next(csv.reader(f))
    assert list(result[0].keys()) == source_header + [prelabel.RULE_COLUMN]


def test_untouched_columns_identical(result):
    """Text with commas, quotes and newlines, and every pass-through column, round-trip exactly."""
    source = {r["message_id"]: r for r in read_rows(SYNTHETIC)}
    derived = {"content_type", "chat_type", "conversation_state", "decision", prelabel.RULE_COLUMN}
    for row in result:
        original = source[row["message_id"]]
        for column, value in original.items():
            if column not in derived:
                assert row[column] == value, column


def test_sorted_by_sender_then_time(result):
    senders = [r["sender_id"] for r in result]
    named = [s for s in senders if s]
    assert named == sorted(named)
    assert senders[-1] == ""  # rows without a sender come last
    alice = [r for r in result if r["sender_id"] == "Alice Example"]
    assert [int(r["timestamp"]) for r in alice] == sorted(int(r["timestamp"]) for r in alice)


def test_burst_keeps_message_order(result):
    bob = [r["message_text"] for r in result if r["sender_id"] == "Bob Sample"]
    assert bob == ["first of two", "second of two"]


def test_every_decision_filled(result):
    assert all(r["decision"] in ("sound", "silent") for r in result)


def test_derived_fields(result):
    rows = by_text(result)
    assert rows["ok, I'll wait at the entrance"]["conversation_state"] == "last_msg_was_question"
    assert rows['Bring the "big" bag,\nand the keys']["conversation_state"] == "last_msg_was_answer"
    assert rows["Are you coming tonight?"]["conversation_state"] == "neutral"
    assert rows["morning"]["conversation_state"] == "neutral"  # question was 7 h earlier
    assert rows["Sticker"]["chat_type"] == "group"
    assert rows["🎤 Voice message"]["chat_type"] == "group"
    assert rows["Scan complete, no threats"]["chat_type"] == "broadcast"
    assert rows["October digest, part 1\nRead more, unsubscribe"]["chat_type"] == "dm"


def test_baseline_rules(result):
    rows = by_text(result)
    assert (rows["Sticker"]["decision"], rows["Sticker"][prelabel.RULE_COLUMN]) == ("silent", "reaction_or_sticker")
    assert rows["ok, I'll wait at the entrance"]["decision"] == "sound"  # after a question
    assert rows["Фото"][prelabel.RULE_COLUMN] == "question"  # previous message "Ты где?" wins over photo
    assert (rows["look at this view"]["decision"], rows["look at this view"][prelabel.RULE_COLUMN]) == ("silent", "photo")
    assert rows["Scan complete, no threats"][prelabel.RULE_COLUMN] == "group_channel_broadcast"


def test_existing_labels_kept(result):
    row = by_text(result)["already labelled"]
    assert (row["decision"], row["content_type"], row[prelabel.RULE_COLUMN]) == ("silent", "text", "")


def test_rerun_on_output_keeps_everything(result, output, tmp_path):
    second = tmp_path / "second.csv"
    assert prelabel.main(["--input", str(output), "--output", str(second)]) == 0
    assert read_rows(second) == result


# --- safety -------------------------------------------------------------------------

def test_input_never_modified(output):
    before = hashlib.sha256(SYNTHETIC.read_bytes()).hexdigest()
    assert prelabel.main(["--input", str(SYNTHETIC), "--output", str(output)]) == 0
    assert hashlib.sha256(SYNTHETIC.read_bytes()).hexdigest() == before


def test_refuses_to_overwrite_input(tmp_path, capsys):
    copy = tmp_path / "export.csv"
    copy.write_bytes(SYNTHETIC.read_bytes())
    assert prelabel.main(["--input", str(copy), "--output", str(copy)]) == 2
    assert copy.read_bytes() == SYNTHETIC.read_bytes()
    assert "never overwritten" in capsys.readouterr().err


def test_refuses_existing_output_without_flag(output):
    output.parent.mkdir(parents=True)
    output.write_text("keep me")
    assert prelabel.main(["--input", str(SYNTHETIC), "--output", str(output)]) == 2
    assert output.read_text() == "keep me"
    assert prelabel.main(["--input", str(SYNTHETIC), "--output", str(output), "--overwrite"]) == 0


def test_missing_input(tmp_path):
    assert prelabel.main(["--input", str(tmp_path / "nope.csv"), "--output", str(tmp_path / "o.csv")]) == 2


def test_rejects_wrong_schema(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\r\n1,2\r\n", encoding="utf-8")
    assert prelabel.main(["--input", str(bad), "--output", str(tmp_path / "o.csv")]) == 2


def test_output_format_matches_export(result, output):
    raw = output.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # no BOM
    assert raw.split(b"\n", 1)[0].endswith(b"\r")  # CRLF


def test_never_prints_text_or_senders(output, capsys):
    assert prelabel.main(["--input", str(SYNTHETIC), "--output", str(output)]) == 0
    captured = capsys.readouterr()
    printed = captured.out + captured.err
    for row in read_rows(SYNTHETIC):
        for column in ("message_text", "sender_id", "raw_conversation_title", "raw_sub_text"):
            value = row[column]
            if len(value) >= 3:  # skip trivially short strings like "ok" that occur in any output
                assert value not in printed, f"{column} leaked to stdout/stderr"


def test_accepts_file_saved_by_calc(tmp_path, result, output):
    """Calc on Linux saves with LF line endings; a reviewed file must still be a valid input."""
    calc_saved = tmp_path / "calc_saved.csv"
    calc_saved.write_bytes(output.read_bytes().replace(b"\r\n", b"\n"))
    rerun = tmp_path / "rerun.csv"
    assert prelabel.main(["--input", str(calc_saved), "--output", str(rerun)]) == 0
    assert read_rows(rerun) == result


def test_reviewed_marker_survives_rerun(tmp_path, result, output):
    rows = read_rows(output)
    rows[0]["prelabel_rule"] = "reviewed"
    rows[0]["decision"] = "silent" if rows[0]["decision"] == "sound" else "sound"
    edited = tmp_path / "edited.csv"
    with edited.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    rerun = tmp_path / "rerun.csv"
    assert prelabel.main(["--input", str(edited), "--output", str(rerun)]) == 0
    first = next(r for r in read_rows(rerun) if r["message_id"] == rows[0]["message_id"])
    assert (first["prelabel_rule"], first["decision"]) == ("reviewed", rows[0]["decision"])
