"""Pre-label a notification_log export for manual review.

    .venv/bin/python prelabel.py --input data/exports/notification_log_X.csv \\
                                 --output data/review/notification_log_X_prelabeled.csv

Fills content_type, chat_type and conversation_state from the raw_* columns and the
message text, pre-fills `decision` with the rule baseline from CLAUDE.md, and writes a
new CSV sorted by sender_id so labels can be reviewed in batches.

- Only empty cells are filled: re-running on an already reviewed file keeps every
  correction. A `prelabel_rule` column records which baseline rule set each decision.
- The input is never modified; the output must be a different file, and an existing
  output is only replaced with --overwrite.
- Call notifications are dropped (pass-through rule, ml/README.md); only their count
  is printed.
- Only aggregate counts are printed, never message text or sender names.

All heuristics are best guesses written without access to real data (the keyword lists
below come from how Telegram / Viber / WhatsApp usually phrase media notifications in
English, Russian and Romanian). Check them on the first reviewed batch.
"""

import argparse
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

from smartmute_data import baseline_decision, drop_calls

# Columns this script reads; everything else is passed through untouched.
REQUIRED_COLUMNS = [
    "message_id", "notification_key", "timestamp", "sender_id", "app_package",
    "content_type", "message_text", "chat_type", "conversation_state", "decision",
    "raw_conversation_title", "raw_is_group_conversation", "raw_has_picture",
]
RULE_COLUMN = "prelabel_rule"

# --- chat_type ---------------------------------------------------------------------

# Apps whose notifications are conversations. Anything else (system apps, clock, wallet,
# security center, news apps) isn't a chat: it's labelled `broadcast`, i.e. one-to-many
# and not personal, which the baseline then makes silent.
MESSENGER_PACKAGES = {
    "org.telegram.messenger", "org.telegram.messenger.web", "org.thunderdog.challegram",
    "com.viber.voip",
    "com.whatsapp", "com.whatsapp.w4b",
    "com.google.android.apps.messaging", "com.samsung.android.messaging", "com.android.mms",
    "com.facebook.orca", "com.instagram.android", "org.thoughtcrime.securesms",
    "com.vkontakte.android", "com.discord", "com.microsoft.teams", "com.slack",
    "com.google.android.gm",
}


def derive_chat_type(app_package: str, conversation_title: str, is_group: str) -> str:
    """dm / group / broadcast. `channel` isn't detected (see below).

    - Not a messenger app → broadcast.
    - MessagingStyle says it's a group conversation (raw_is_group_conversation = 1) → group.
    - A conversation title is set → group: apps set MessagingStyle.conversationTitle for
      group chats and usually leave it empty for one-to-one chats.
    - Otherwise → dm. This includes email (Gmail): an email is addressed to the user;
      mailing lists and newsletters need manual correction.

    Telegram channels look exactly like one-to-one chats in a notification (the channel
    is the "sender", no group flag), so they come out as dm and need manual correction.
    """
    if app_package not in MESSENGER_PACKAGES:
        return "broadcast"
    if is_group == "1":
        return "group"
    if conversation_title.strip():
        return "group"
    return "dm"


# --- content_type ------------------------------------------------------------------

# Placeholder texts messengers show instead of media, matched against the whole message
# after emoji and punctuation are stripped and case is folded ("🎤 Voice message" →
# "voice message"). A caption sent with a photo replaces the placeholder, so captioned
# media mostly comes out as `text` (or `photo` via raw_has_picture).
MEDIA_PLACEHOLDERS = {
    "sticker": {"sticker", "стикер", "autocolant"},
    "voice": {
        "voice message", "voice note", "audio", "audio message", "voice",
        "голосовое сообщение", "голосовое", "аудиосообщение", "аудио",
        "mesaj vocal", "mesaj audio", "notă vocală",
    },
    "video": {
        "video", "video message", "gif", "видео", "видеосообщение", "gif-анимация",
        "mesaj video", "videoclip",
    },
    "photo": {
        "photo", "photo message", "picture", "image",
        "фото", "фотография", "изображение",
        "fotografie", "poză", "imagine",
    },
    "file": {"file", "document", "файл", "документ", "fișier"},
}

# Reactions arrive as a sentence about the message ("Alice reacted 👍 to your message"),
# so they're found anywhere in the text.
REACTION_PATTERN = re.compile(
    r"reacted|liked your message|отреагировал|отреагировала|поставил[аи]? реакцию|"
    r"a reacționat|a reactionat",
    re.IGNORECASE,
)

# Characters that make up emoji besides the pictographs themselves (category So).
_EMOJI_JOINERS = {"‍", "️", "︎", "⃣"}


def _is_emoji(char: str) -> bool:
    # So = symbol other (most emoji), Sk = modifier symbol (skin tones).
    return unicodedata.category(char) in ("So", "Sk") or char in _EMOJI_JOINERS


def is_emoji_only(text: str) -> bool:
    """Non-empty and nothing but emoji and spaces: '😂😂 👍🏽' yes, 'ok 👍' no."""
    return bool(text.strip()) and all(_is_emoji(c) or c.isspace() for c in text)


def _core_words(text: str) -> str:
    """Letters, digits and single spaces only, case-folded: '🎤 Voice message!' → 'voice message'."""
    kept = "".join(c if c.isalnum() or c.isspace() or c == "-" else " " for c in text)
    return " ".join(kept.split()).casefold()


def derive_content_type(text: str, has_picture: str) -> str:
    """text / photo / video / voice / file / sticker / emoji_only / reaction.

    In order, first match wins:
    1. No text: photo if raw_has_picture, else file (media without caption whose kind
       can't be told).
    2. A reaction sentence → reaction.
    3. The whole message is a known media placeholder → that media type.
    4. raw_has_picture → photo (picture with a caption).
    5. Only emoji (and spaces) → emoji_only.
    6. Otherwise → text.
    """
    if not text.strip():
        return "photo" if has_picture == "1" else "file"
    if REACTION_PATTERN.search(text):
        return "reaction"
    core = _core_words(text)
    for content_type, placeholders in MEDIA_PLACEHOLDERS.items():
        if core in placeholders:
            return content_type
    if has_picture == "1":
        return "photo"
    if is_emoji_only(text):
        return "emoji_only"
    return "text"


# --- conversation_state -----------------------------------------------------------

# Two messages further apart than this belong to different conversations.
CONVERSATION_GAP_SEC = 6 * 3600

# Short replies that close a question ("ok", "да", "nu"). Matched against the whole
# previous message, so "ok, but why?" doesn't count (and has a "?" anyway).
ANSWER_WORDS = {
    "ok", "okay", "k", "yes", "no", "yep", "nope", "sure", "fine", "thanks", "thank you",
    "ок", "окей", "да", "нет", "ага", "угу", "хорошо", "ладно", "спасибо", "конечно",
    "da", "nu", "bine", "mersi", "sigur", "desigur",
}


def derive_conversation_state(previous_text: str | None) -> str:
    """last_msg_was_question / last_msg_was_answer / neutral, from the previous message.

    `previous_text` is the previous logged message in the same conversation (same app and
    sender_id) within CONVERSATION_GAP_SEC, or None if there isn't one.

    - Previous message contains "?" → last_msg_was_question.
    - Previous message is just a short answer word ("ok", "да") → last_msg_was_answer.
    - Otherwise, or no previous message → neutral.

    Limitation: the app logs only incoming messages, never the user's own, so "previous
    message" means the other side's previous message; a question the user asked isn't
    visible here.
    """
    if previous_text is None:
        return "neutral"
    if "?" in previous_text:
        return "last_msg_was_question"
    if _core_words(previous_text) in ANSWER_WORDS:
        return "last_msg_was_answer"
    return "neutral"


def previous_texts(df: pd.DataFrame) -> pd.Series:
    """For each row, the text of the previous message in its conversation, or None.

    A conversation is app_package + sender_id (or notification_key when sender_id is
    empty), ordered by timestamp, then message_id for messages delivered together.
    """
    conversation = df["app_package"] + "\x1f" + df["sender_id"].where(df["sender_id"] != "",
                                                                       "key:" + df["notification_key"])
    order = df.assign(_conv=conversation, _ts=df["timestamp"].astype("int64"),
                      _id=df["message_id"].astype("int64")).sort_values(["_conv", "_ts", "_id"], kind="stable")
    prev_text = order.groupby("_conv")["message_text"].shift(1)
    prev_ts = order.groupby("_conv")["_ts"].shift(1)
    too_old = (order["_ts"] - prev_ts) > CONVERSATION_GAP_SEC * 1000
    prev_text = prev_text.where(~too_old)
    return prev_text.reindex(df.index).astype(object).where(lambda s: s.notna(), None)


# --- pipeline ---------------------------------------------------------------------

def prelabel(df: pd.DataFrame) -> tuple[pd.DataFrame, Counter]:
    """Fills empty derived cells and empty decisions. Returns (sorted copy, counts)."""
    df = df.copy()
    counts: Counter = Counter()

    def fill(column: str, derived: pd.Series) -> None:
        empty = df[column] == ""
        counts[f"{column}: filled"] += int(empty.sum())
        counts[f"{column}: kept existing"] += int((~empty).sum())
        df.loc[empty, column] = derived[empty]

    fill("chat_type", df.apply(lambda r: derive_chat_type(
        r["app_package"], r["raw_conversation_title"], r["raw_is_group_conversation"]), axis=1))
    fill("content_type", df.apply(lambda r: derive_content_type(
        r["message_text"], r["raw_has_picture"]), axis=1))
    fill("conversation_state", previous_texts(df).map(derive_conversation_state))

    decisions = df.apply(lambda r: baseline_decision(
        r["content_type"], r["conversation_state"], r["chat_type"]), axis=1)
    if RULE_COLUMN not in df.columns:
        df[RULE_COLUMN] = ""
    empty = df["decision"] == ""
    counts["decision: filled"] = int(empty.sum())
    counts["decision: kept existing"] = int((~empty).sum())
    df.loc[empty, "decision"] = decisions[empty].map(lambda d: d[0])
    df.loc[empty, RULE_COLUMN] = decisions[empty].map(lambda d: d[1])

    # Batches by sender for review; rows without a sender last; time order within a sender.
    df = df.assign(_no_sender=df["sender_id"] == "", _ts=df["timestamp"].astype("int64"),
                   _id=df["message_id"].astype("int64"))
    df = df.sort_values(["_no_sender", "sender_id", "app_package", "_ts", "_id"], kind="stable")
    return df.drop(columns=["_no_sender", "_ts", "_id"]), counts


def read_export(path: Path) -> pd.DataFrame:
    """Reads every column as text, so values are written back exactly as exported."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"input is missing columns: {', '.join(missing)}")
    for column in ("timestamp", "message_id"):
        bad = ~df[column].str.fullmatch(r"\d+")
        if bad.any():
            raise ValueError(f"{int(bad.sum())} row(s) have a non-numeric {column}")
    return df


def write_review(df: pd.DataFrame, path: Path) -> None:
    """Same format as the app's export: UTF-8 without BOM, CRLF, RFC 4180 quoting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n")


def print_summary(df: pd.DataFrame, counts: Counter) -> None:
    """Aggregate counts only: category labels, never message text or senders."""
    print(f"rows: {len(df)}")
    for column in ("chat_type", "content_type", "conversation_state", "decision", RULE_COLUMN):
        values = df[column].replace("", "(empty)").value_counts()
        print(f"\n{column}: " + ", ".join(f"{k}={v}" for k, v in values.items()))
    print()
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", required=True, type=Path, help="notification_log_*.csv exported by the dev app")
    parser.add_argument("--output", required=True, type=Path, help="review CSV to write (must differ from --input)")
    parser.add_argument("--overwrite", action="store_true", help="replace --output if it already exists")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2
    if args.output.resolve() == args.input.resolve() or (
            args.output.exists() and os.path.samefile(args.output, args.input)):
        print("error: --output is the input file; the original export is never overwritten", file=sys.stderr)
        return 2
    if args.output.exists() and not args.overwrite:
        print(f"error: {args.output} exists; pass --overwrite to replace it", file=sys.stderr)
        return 2
    try:
        df = read_export(args.input)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Pass-through rule: calls are never decided on, so they don't belong in a review file.
    df, calls = drop_calls(df)
    result, counts = prelabel(df)
    write_review(result, args.output)
    print(f"call notifications dropped: {calls}")
    print_summary(result, counts)
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
