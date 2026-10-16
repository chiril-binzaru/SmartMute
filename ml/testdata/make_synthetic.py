"""Writes notification_log_synthetic.csv: fake rows in the exact format of the app's export.

    .venv/bin/python testdata/make_synthetic.py

Every name and message here is invented. Each row exists to exercise one heuristic in
prelabel.py; the comment next to it says which.
"""

import csv
from pathlib import Path

OUT = Path(__file__).parent / "notification_log_synthetic.csv"
# The same rows as a reviewed file: prelabel_rule and a user-assigned `role` column added.
OUT_REVIEW = Path(__file__).parent / "notification_log_synthetic_review.csv"

# Column order of notification_log (schema v2) plus the export's removal_reason_name.
COLUMNS = [
    "message_id", "notification_key", "timestamp", "sender_id", "app_package", "content_type",
    "message_text", "chat_type", "time_since_last_msg_from_sender_sec", "conversation_state",
    "user_reaction", "time_to_open_sec", "decision", "feedback", "corrected_decision",
    "raw_conversation_title", "raw_sub_text", "raw_is_group_conversation", "raw_category",
    "raw_template", "raw_has_picture", "removed_at", "removal_reason", "raw_message_time",
    "removal_reason_name",
]

TG, VIBER, WA, GMAIL, SMS = ("org.telegram.messenger", "com.viber.voip", "com.whatsapp",
                             "com.google.android.gm", "com.google.android.apps.messaging")
MSG_STYLE = "android.app.Notification$MessagingStyle"
T0 = 1_791_000_000_000  # epoch ms, an arbitrary day in October 2026
MIN = 60_000
HOUR = 60 * MIN

WA_KEY = "0|com.whatsapp|1|37300000099@s.whatsapp.net|10099"

# role column of the review file, per sender; others stay empty.
ROLES = {"Alice Example": "friend", "Bob Sample": "friend", "Тест Тестович": "family",
         "Study Group Demo": "study", "Ion Fictiv": "work"}

REASON_NAMES = {1: "CLICK", 2: "CANCEL", 8: "APP_CANCEL", 9: "APP_CANCEL_ALL"}

# (minute offset, sender, package, text, extra fields)
ROWS = [
    # Telegram DM: question, then a reply → second row's state is last_msg_was_question.
    (0, "Alice Example", TG, "Are you coming tonight?", {}),
    (2, "Alice Example", TG, "ok, I'll wait at the entrance", {}),
    # Answer word → next state last_msg_was_answer; text with comma, quotes, newline.
    (3, "Alice Example", TG, "ok", {}),
    (4, "Alice Example", TG, 'Bring the "big" bag,\nand the keys', {}),
    # Burst: two messages delivered in one notification share the timestamp.
    (10, "Bob Sample", TG, "first of two", {"raw_message_time": "+0"}),
    (10, "Bob Sample", TG, "second of two", {"raw_message_time": "+1"}),
    # Telegram group via the group flag; media placeholders with emoji prefix.
    (20, "Study Group Demo", TG, "📷 Photo",
     {"raw_conversation_title": "Study Group Demo", "raw_is_group_conversation": "1", "raw_has_picture": "1"}),
    (21, "Study Group Demo", TG, "Sticker",
     {"raw_conversation_title": "Study Group Demo", "raw_is_group_conversation": "1"}),
    # WhatsApp group detected only by the conversation title.
    (30, "Family Chat Demo", WA, "dinner at 7?", {"raw_conversation_title": "Family Chat Demo"}),
    (31, "Family Chat Demo", WA, "🎤 Voice message", {"raw_conversation_title": "Family Chat Demo"}),
    # Group where the title differs from the sender (masking: both get pseudonyms).
    (32, "Greg Member", TG, "who's bringing the tent?",
     {"raw_conversation_title": "Hiking Club Demo", "raw_is_group_conversation": "1"}),
    # Viber DM in Russian: placeholders and a question.
    (40, "Тест Тестович", VIBER, "Ты где?", {}),
    (41, "Тест Тестович", VIBER, "Фото", {"raw_has_picture": "1"}),
    (42, "Тест Тестович", VIBER, "🎤 Голосовое сообщение", {}),
    (43, "Тест Тестович", VIBER, "Видео", {}),
    # Romanian placeholders.
    (50, "Ion Fictiv", VIBER, "Mesaj vocal", {}),
    (51, "Ion Fictiv", VIBER, "Fișier", {}),
    # Emoji only (with skin tone and ZWJ sequence), and a reaction sentence.
    (60, "Carol Demo", TG, "😂😂 👍🏽", {}),
    (61, "Carol Demo", TG, "👨‍👩‍👧", {}),
    (62, "Carol Demo", TG, "Carol Demo reacted 👍 to your message", {}),
    # Picture with a caption → photo; media with no text and no picture → file.
    # WhatsApp puts the contact's phone number in the key's tag (masking: key pseudonymized).
    (70, "Dan Placeholder", WA, "look at this view", {"raw_has_picture": "1", "notification_key": WA_KEY}),
    (71, "Dan Placeholder", WA, "", {"notification_key": WA_KEY}),
    # Gmail: email category → dm; multi-line text with commas.
    (80, "Newsletter Fake", GMAIL, "October digest, part 1\nRead more, unsubscribe",
     {"raw_category": "email", "raw_sub_text": "user@example.invalid", "raw_template": "", "raw_message_time": ""}),
    # SMS app, plain text.
    (90, "+37300000000", SMS, "Your code is 0000", {}),
    # SMS short code as sender (masking: matched as a whole cell, not inside timestamps).
    (91, "7444", SMS, "Your balance is low", {}),
    # Not a messenger → broadcast.
    (100, "Security scan", "com.miui.securitycenter", "Scan complete, no threats",
     {"raw_template": "", "raw_message_time": ""}),
    # Call notifications (pass-through rule): a Telegram call in CallStyle, and a dialer
    # missed call. prelabel.py and mask.py must drop both.
    (105, "Alice Example", TG, "Incoming call", {"raw_template": "android.app.Notification$CallStyle",
                                                 "raw_category": "call", "raw_message_time": ""}),
    (106, "Mom Demo", "com.google.android.dialer", "Missed call",
     {"raw_template": "", "raw_category": "missed_call", "raw_message_time": ""}),
    # No sender at all.
    (110, "", "com.android.deskclock", "Alarm", {"raw_template": "", "raw_message_time": ""}),
    # Already reviewed row: its decision and content_type must be kept.
    (120, "Reviewed Person", TG, "already labelled", {"content_type": "text", "decision": "silent"}),
    # Question more than 6 h before the next message → that next message is neutral.
    (200, "Eve Gap", TG, "still there?", {}),
    (200 + 7 * 60, "Eve Gap", TG, "morning", {}),
]


def build_rows() -> list[dict]:
    rows = []
    last_from_sender: dict[tuple, int] = {}
    chat_ids: dict[tuple, int] = {}  # stable notification id per chat, like a real app's
    for i, (minute, sender, package, text, extra) in enumerate(ROWS, start=1):
        ts = T0 + minute * MIN
        removed = ts + (i % 7 + 1) * MIN
        reason = (1, 2, 8, 9)[i % 4]
        chat_id = chat_ids.setdefault((package, sender), len(chat_ids) + 1)
        key = f"0|{package}|{chat_id}|null|10{chat_id:03d}"
        since = last_from_sender.get((package, sender))
        last_from_sender[(package, sender)] = ts
        row = {c: "" for c in COLUMNS}
        row.update({
            "message_id": str(i),
            "notification_key": key,
            "timestamp": str(ts),
            "sender_id": sender,
            "app_package": package,
            "message_text": text,
            "time_since_last_msg_from_sender_sec": "" if since is None else str((ts - since) // 1000),
            "time_to_open_sec": str((removed - ts) // 1000) if reason in (1, 8) else "",
            "raw_is_group_conversation": "0",
            "raw_category": "msg",
            "raw_template": MSG_STYLE,
            "raw_has_picture": "0",
            "removed_at": str(removed),
            "removal_reason": str(reason),
            "removal_reason_name": REASON_NAMES[reason],
            "raw_message_time": str(ts - 1500),
        })
        for column, value in extra.items():
            if column == "raw_message_time" and value.startswith("+"):
                value = str(ts - 1500 + int(value[1:]) * 400)
            row[column] = value
        rows.append(row)
    return rows


def write(path: Path, rows: list[dict]) -> None:
    # Same format as the app's export: UTF-8 without BOM, CRLF, RFC 4180 minimal quoting.
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> None:
    rows = build_rows()
    write(OUT, rows)
    reviewed = [{**row, "prelabel_rule": "reviewed", "role": ROLES.get(row["sender_id"], "")} for row in rows]
    write(OUT_REVIEW, reviewed)


if __name__ == "__main__":
    main()
