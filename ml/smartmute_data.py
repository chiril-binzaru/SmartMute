"""Loading SmartMute data: the app's CSV export and the manual 200-row dataset.

Column reference: docs/DATA_SCHEMA.md. Keep this file in sync with it.
"""

from pathlib import Path

import pandas as pd

LOCAL_TZ = "Europe/Chisinau"

# Text columns: never let pandas guess types, or "+373..." / "1-2" / "None" get mangled.
TEXT_COLUMNS = [
    "notification_key", "sender_id", "app_package", "content_type", "message_text",
    "chat_type", "conversation_state", "user_reaction", "decision", "feedback",
    "corrected_decision", "raw_conversation_title", "raw_sub_text", "raw_category",
    "raw_template", "removal_reason_name",
]

# removal_reason codes (NotificationListenerService.REASON_*); meaning per
# "user_reaction" in docs/DATA_SCHEMA.md.
REASON_APP_CANCEL_ALL = 9
REASONS_OPENED = {1, 8}               # tapped; read in the app / "Mark as read"
REASONS_DISMISSED = {2, 3, 10, 11, 18, 19, 24}  # swiped, cleared, snoozed, timed out
# Everything else (9 unless resolved, 12 group summary, system reasons) is unknown.

# A code-9 clear followed this soon by a post under the same key = app restart re-post.
REPOST_WINDOW_SEC = 10

OPENED_IMMEDIATELY_SEC = 300
IGNORED_AFTER_SEC = 24 * 3600

# Packages that aren't conversations; excluded from messenger stats.
NON_MESSENGER_PACKAGES = {"com.android.shell"}


def load_export(path: str | Path) -> pd.DataFrame:
    """Reads a notification_log_*.csv exported by the dev app."""
    df = pd.read_csv(
        path,
        encoding="utf-8",
        keep_default_na=False,
        na_values=[""],  # only an empty field is missing; "None"/"NA" stay text
        dtype={c: "string" for c in TEXT_COLUMNS},
    ).convert_dtypes()
    for col in ("timestamp", "removed_at"):
        df[col] = pd.to_datetime(df[col], unit="ms", utc=True).dt.tz_convert(LOCAL_TZ)
    return df


def load_manual(path: str | Path) -> pd.DataFrame:
    """Reads the hand-labelled 200-row dataset; `decision` is the ground-truth label."""
    df = pd.read_excel(path, dtype={"message_id": "string", "message_text": "string"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(LOCAL_TZ)
    return df


def latest_export(data_dir: str | Path) -> Path:
    exports = sorted(Path(data_dir).glob("notification_log_*.csv"))
    if not exports:
        raise FileNotFoundError(f"No notification_log_*.csv in {data_dir}")
    return exports[-1]


def resolve_reposts(df: pd.DataFrame) -> pd.DataFrame:
    """Undoes app-restart clears in data logged before schema v2.

    Viber clears all its notifications on restart (code 9) and posts the unread messages
    again. A code-9 row followed within REPOST_WINDOW_SEC by a post under the same key takes
    that post's outcome; if the post is the same message again (same sender and text), it's
    a duplicate and is dropped. From schema v2 the app reopens such rows itself.
    """
    # Messages delivered together share `timestamp`; message_id keeps their order.
    df = df.sort_values(["timestamp", "message_id"], kind="stable").copy()
    duplicates = []
    for _, group in df.groupby("notification_key", sort=False):
        rows = group.index.tolist()
        # Newest first, so a successor's outcome is final before it's inherited.
        for pos in range(len(rows) - 1, -1, -1):
            i = rows[pos]
            if not _equal(df.at[i, "removal_reason"], REASON_APP_CANCEL_ALL):
                continue
            removed_at = df.at[i, "removed_at"]
            window_end = removed_at + pd.Timedelta(seconds=REPOST_WINDOW_SEC)
            successors = [j for j in rows[pos + 1:]
                          if j not in duplicates and removed_at < df.at[j, "timestamp"] <= window_end]
            if not successors:
                continue
            j = successors[0]
            df.loc[i, ["removed_at", "removal_reason"]] = df.loc[j, ["removed_at", "removal_reason"]].values
            if (_equal(df.at[j, "sender_id"], df.at[i, "sender_id"])
                    and _equal(df.at[j, "message_text"], df.at[i, "message_text"])):
                duplicates.append(j)
    return df.drop(index=duplicates)


def _equal(a, b) -> bool:
    """== that treats two missing values as equal and never returns <NA>."""
    if pd.isna(a) or pd.isna(b):
        return pd.isna(a) and pd.isna(b)
    return a == b


def derive_user_reaction(df: pd.DataFrame, now: pd.Timestamp) -> pd.Series:
    """user_reaction from removal data, per docs/DATA_SCHEMA.md. Run resolve_reposts first.

    Returns opened_immediately / opened_later / ignored, or <NA> when it can't be told:
    still showing and younger than 24 h, or a removal that says nothing about attention.
    """
    age_sec = (now - df["timestamp"]).dt.total_seconds()
    open_sec = (df["removed_at"] - df["timestamp"]).dt.total_seconds()
    reason = df["removal_reason"]

    out = pd.Series(pd.NA, index=df.index, dtype="string")
    opened = reason.isin(REASONS_OPENED).fillna(False)
    out[opened & (open_sec <= OPENED_IMMEDIATELY_SEC)] = "opened_immediately"
    out[opened & (open_sec > OPENED_IMMEDIATELY_SEC) & (open_sec <= IGNORED_AFTER_SEC)] = "opened_later"
    out[opened & (open_sec > IGNORED_AFTER_SEC)] = "ignored"
    out[reason.isin(REASONS_DISMISSED).fillna(False)] = "ignored"
    still_showing = reason.isna() & df["removed_at"].isna()
    out[still_showing & (age_sec > IGNORED_AFTER_SEC)] = "ignored"
    return out


def rule_baseline(df: pd.DataFrame) -> pd.Series:
    """The rule-based engine from CLAUDE.md ("Experiment status"), first match wins."""
    def decide(row) -> str:
        if row["content_type"] in ("reaction", "sticker"):
            return "silent"
        if row["conversation_state"] == "last_msg_was_question":
            return "sound"
        if row["chat_type"] in ("group", "channel", "broadcast"):
            return "silent"
        if row["content_type"] == "photo":
            return "silent"
        return "sound"
    return df.apply(decide, axis=1)
