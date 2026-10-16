"""First look at the data. Prints aggregates only, never message text.

    .venv/bin/python explore.py [path/to/notification_log_*.csv]

Without an argument, uses the newest export in ml/data/.
"""

import sys
from pathlib import Path

import pandas as pd

import smartmute_data as sd

DATA_DIR = Path(__file__).parent / "data"
MANUAL = DATA_DIR / "android_message_notifications_200_v3.xlsx"


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def explore_export(path: Path) -> None:
    df, calls = sd.drop_calls(sd.load_export(path, include_calls=True))
    df = df[~df["app_package"].isin(sd.NON_MESSENGER_PACKAGES)]
    now = pd.Timestamp.now(tz=sd.LOCAL_TZ)

    section(f"Export {path.name}")
    print(f"{len(df)} rows, {df['timestamp'].min():%Y-%m-%d %H:%M} → {df['timestamp'].max():%Y-%m-%d %H:%M}")
    print(f"call notifications excluded: {calls}")

    section("Rows per app")
    print(df["app_package"].value_counts().to_string())

    section("Removal reason")
    print(df["removal_reason_name"].fillna("(still showing)").value_counts().to_string())

    section("Senders per app (distinct sender_id)")
    print(df.groupby("app_package")["sender_id"].nunique().sort_values(ascending=False).to_string())

    resolved = sd.resolve_reposts(df)
    restarts = (df["removal_reason"] == sd.REASON_APP_CANCEL_ALL).sum()
    still_9 = (resolved["removal_reason"] == sd.REASON_APP_CANCEL_ALL).sum()
    section("App-restart re-posts (code 9)")
    print(f"code-9 rows: {restarts}, resolved: {restarts - still_9}, "
          f"duplicate rows dropped: {len(df) - len(resolved)}")

    section("user_reaction (opened = CLICK or APP_CANCEL)")
    reaction = sd.derive_user_reaction(resolved, now)
    print(reaction.fillna("(unknown)").value_counts().to_string())


def explore_manual(path: Path) -> None:
    df = sd.load_manual(path)
    section(f"Manual dataset {path.name}")
    print(f"{len(df)} rows, label balance: {df['decision'].value_counts().to_dict()}")

    section("Rule baseline on the manual dataset")
    predicted = sd.rule_baseline(df)
    accuracy = (predicted == df["decision"]).mean()
    print(f"accuracy {accuracy:.1%}  (CLAUDE.md reports 68.5%)")

    section("Sound rate per chat_type")
    print(df.assign(sound=df["decision"].eq("sound")).groupby("chat_type")["sound"].mean().round(2).to_string())


def main() -> None:
    export = Path(sys.argv[1]) if len(sys.argv) > 1 else sd.latest_export(DATA_DIR)
    explore_export(export)
    if MANUAL.exists():
        explore_manual(MANUAL)


if __name__ == "__main__":
    main()
