"""Mask a notification_log export or review file so it can leave the PC.

    .venv/bin/python mask.py --input data/review/notification_log_X_review.csv \\
                             --output data/masked/notification_log_X_masked.csv \\
                             --mapping data/private/pseudonyms.csv

- Only the columns in ALLOWLIST are written; any other column, including ones added
  to the app later, is dropped until it's reviewed and added here.
- message_text is dropped; text_len, has_qmark and is_emoji_only are derived from it
  first. raw_sub_text is dropped (Gmail puts the account address there).
- sender_id and raw_conversation_title are replaced with pseudonyms S01, S02, ... from
  one shared mapping, so a group whose title is also its sender_id gets one pseudonym.
  notification_key (WhatsApp puts the contact's phone number in it) becomes K01, K02, ...
- The pseudonym -> original mapping is written only to --mapping. If that file exists
  it's reused and extended, so a person keeps the same pseudonym across exports.
- After writing, the output is searched for every original value that was replaced; if
  any is found the output is deleted and the script exits with code 3.
- Call notifications are dropped (pass-through rule, ml/README.md).
- Only aggregate counts are printed, never message text or sender names.

The user-assigned `role` column (if the input has one) is kept as is: it's free text,
so don't type names into it. The leak check fails if a role equals a sender's name.
"""

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd

from prelabel import is_emoji_only
from smartmute_data import drop_calls

REQUIRED_COLUMNS = ["message_id", "timestamp", "sender_id", "message_text"]

# Pseudonymized with the S namespace (names), and with the K namespace (keys).
NAME_COLUMNS = ["sender_id", "raw_conversation_title"]
KEY_COLUMNS = ["notification_key"]

# Derived from message_text before it's dropped.
TEXT_FEATURES = ["text_len", "has_qmark", "is_emoji_only"]

# Every column that may appear in the output, in output order. Columns missing from the
# input are skipped. Not listed, so dropped: message_text, raw_sub_text.
ALLOWLIST = [
    "message_id", "timestamp", "sender_id", "role", "app_package", "notification_key",
    "content_type", "chat_type", "conversation_state", *TEXT_FEATURES,
    "time_since_last_msg_from_sender_sec", "user_reaction", "time_to_open_sec",
    "decision", "prelabel_rule", "feedback", "corrected_decision",
    "raw_conversation_title", "raw_is_group_conversation", "raw_category", "raw_template",
    "raw_has_picture", "raw_message_time", "removed_at", "removal_reason",
    "removal_reason_name",
]

MAPPING_COLUMNS = ["pseudonym", "original"]
PREFIX_NAME, PREFIX_KEY = "S", "K"

# Originals made only of digits and phone punctuation, with at most this many digits
# (SMS short codes like "1234"), would match inside timestamps and ids, so they're
# checked against whole cells instead of as substrings.
SHORT_NUMBER_DIGITS = 6
_PHONE_CHARS = re.compile(r"[\d+\-\s()]+")


class LeakError(Exception):
    pass


# --- pseudonyms ---------------------------------------------------------------------

class Pseudonyms:
    """Stable original -> pseudonym assignment per prefix, loaded from and saved to --mapping."""

    def __init__(self, rows: list[dict] | None = None):
        self.by_original: dict[tuple[str, str], str] = {}
        self.next_number: dict[str, int] = {PREFIX_NAME: 1, PREFIX_KEY: 1}
        self.new = 0
        for row in rows or []:
            pseudonym, original = row["pseudonym"], row["original"]
            prefix, number = pseudonym[0], int(pseudonym[1:])
            self.by_original[(prefix, original)] = pseudonym
            self.next_number[prefix] = max(self.next_number[prefix], number + 1)

    def get(self, prefix: str, original: str) -> str:
        """Pseudonym for a value; empty stays empty."""
        if original == "":
            return ""
        key = (prefix, original)
        if key not in self.by_original:
            self.by_original[key] = f"{prefix}{self.next_number[prefix]:02d}"
            self.next_number[prefix] += 1
            self.new += 1
        return self.by_original[key]

    def originals(self) -> set[str]:
        return {original for _, original in self.by_original}

    def rows(self) -> list[dict]:
        def order(item):
            pseudonym = item[1]
            return pseudonym[0], int(pseudonym[1:])
        return [{"pseudonym": p, "original": o} for (_, o), p in sorted(self.by_original.items(), key=order)]


def read_mapping(path: Path) -> Pseudonyms:
    if not path.exists():
        return Pseudonyms()
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != MAPPING_COLUMNS:
            raise ValueError(f"{path} isn't a mapping file (expected columns {', '.join(MAPPING_COLUMNS)})")
        rows = list(reader)
    bad = [r for r in rows if not re.fullmatch(rf"[{PREFIX_NAME}{PREFIX_KEY}]\d+", r["pseudonym"])]
    if bad:
        raise ValueError(f"{path} has {len(bad)} malformed pseudonym(s)")
    return Pseudonyms(rows)


def write_mapping(pseudonyms: Pseudonyms, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MAPPING_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(pseudonyms.rows())
    os.replace(tmp, path)


# --- masking ------------------------------------------------------------------------

def mask(df: pd.DataFrame, pseudonyms: Pseudonyms) -> pd.DataFrame:
    """Returns the masked copy: allowlisted columns only, identifiers pseudonymized."""
    df = df.copy()
    text = df["message_text"]
    df["text_len"] = text.str.len().astype(str)
    df["has_qmark"] = text.str.contains("?", regex=False).astype(int).astype(str)
    df["is_emoji_only"] = text.map(is_emoji_only).astype(int).astype(str)

    # Numbered in time order, so pseudonyms don't follow the alphabetical order of names.
    order = df.assign(_ts=df["timestamp"].astype("int64"), _id=df["message_id"].astype("int64")) \
              .sort_values(["_ts", "_id"], kind="stable").index
    columns = [(c, PREFIX_NAME) for c in NAME_COLUMNS if c in df.columns] + \
              [(c, PREFIX_KEY) for c in KEY_COLUMNS if c in df.columns]
    mapped: dict[str, dict] = {column: {} for column, _ in columns}
    for i in order:
        for column, prefix in columns:
            mapped[column][i] = pseudonyms.get(prefix, df.at[i, column])
    for column, values in mapped.items():
        df[column] = pd.Series(values)

    return df[[c for c in ALLOWLIST if c in df.columns]]


def _is_short_number(value: str) -> bool:
    return bool(_PHONE_CHARS.fullmatch(value)) and sum(c.isdigit() for c in value) <= SHORT_NUMBER_DIGITS


def find_leaks(path: Path, originals: set[str]) -> dict[str, int]:
    """Searches the written file for original identifier values.

    Returns {output column (or "raw file"): number of distinct originals found there}.
    Every original is searched as a substring of every cell and of the raw file text,
    except short numbers, which must equal a whole cell to count.
    """
    raw = path.read_text(encoding="utf-8")
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, cells = rows[0], rows
    leaks: dict[str, set[str]] = {}
    for original in originals:
        if not original.strip():
            continue
        short = _is_short_number(original)
        for row in cells:
            for column, cell in zip(header, row):
                if (cell == original) if short else (original in cell):
                    leaks.setdefault(column, set()).add(original)
        if not short and original in raw:
            leaks.setdefault("raw file", set()).add(original)
    return {column: len(found) for column, found in sorted(leaks.items())}


def write_masked(df: pd.DataFrame, path: Path, originals: set[str]) -> None:
    """Writes to a temp file next to `path`, checks it for leaks, then moves it into place.

    On a leak the temp file is deleted, nothing is left at `path`, and LeakError is raised.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".masking-", suffix=".csv", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        df.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\r\n")
        leaks = find_leaks(tmp, originals)
        if leaks:
            where = ", ".join(f"{column} ({n})" for column, n in leaks.items())
            raise LeakError(f"original identifier values found in the masked output: {where}")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_input(path: Path) -> pd.DataFrame:
    """Reads every column as text, so kept values are written exactly as they were."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"input is missing columns: {', '.join(missing)}")
    for column in ("timestamp", "message_id"):
        bad = ~df[column].str.fullmatch(r"\d+")
        if bad.any():
            raise ValueError(f"{int(bad.sum())} row(s) have a non-numeric {column}")
    return df


# --- CLI ----------------------------------------------------------------------------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", required=True, type=Path, help="export or review CSV")
    parser.add_argument("--output", required=True, type=Path, help="masked CSV to write")
    parser.add_argument("--mapping", required=True, type=Path,
                        help="private pseudonym -> original CSV; reused and extended if it exists")
    parser.add_argument("--overwrite", action="store_true", help="replace --output if it already exists")
    return parser.parse_args(argv)


def _same(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and os.path.samefile(a, b))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2
    for name, a, b in [("--output", args.output, args.input), ("--mapping", args.mapping, args.input),
                       ("--mapping", args.mapping, args.output)]:
        if _same(a, b):
            print(f"error: {name} must be a different file from the other paths", file=sys.stderr)
            return 2
    if args.output.exists() and not args.overwrite:
        print(f"error: {args.output} exists; pass --overwrite to replace it", file=sys.stderr)
        return 2
    try:
        df = read_input(args.input)
        pseudonyms = read_mapping(args.mapping)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Pass-through rule: calls are excluded from the training set, so from shared copies too.
    df, calls = drop_calls(df)
    known_before = len(pseudonyms.by_original)
    masked = mask(df, pseudonyms)
    try:
        write_masked(masked, args.output, pseudonyms.originals())
    except LeakError as e:
        print("\n" + "!" * 72, file=sys.stderr)
        print(f"MASKING FAILED: {e}", file=sys.stderr)
        print("Nothing was written to --output and the mapping wasn't changed.", file=sys.stderr)
        print("!" * 72, file=sys.stderr)
        return 3
    write_mapping(pseudonyms, args.mapping)

    dropped = [c for c in df.columns if c not in masked.columns]
    print(f"rows: {len(masked)}")
    print(f"call notifications dropped: {calls}")
    print(f"columns kept: {len(masked.columns)}, dropped: {len(dropped)} ({', '.join(dropped)})")
    print(f"distinct senders: {df['sender_id'].replace('', pd.NA).nunique()}")
    print(f"pseudonyms: {known_before} already in mapping, {pseudonyms.new} new (names and keys)")
    print("role column: " + ("kept" if "role" in masked.columns else "not in input"))
    print("leak check: passed")
    print(f"\nwrote {args.output}\nmapping: {args.mapping} (private, never share it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
