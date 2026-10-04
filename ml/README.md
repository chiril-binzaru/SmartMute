# SmartMute ML

Offline training pipeline for the sound/silent classifier (step 5 of the implementation
order in `../CLAUDE.md`). Runs on the PC; only the trained model goes to the phone.

## Setup

```
cd ml
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Needs Debian's `python3-venv` package.

## Data

Datasets live in `ml/data/`, which git ignores: they contain real messages and must
never be committed.

- `notification_log_*.csv`: exports from the dev app
  (`adb pull /sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/ data/`).
  Format and columns: `../docs/DATA_SCHEMA.md`.
- `android_message_notifications_200_v3.xlsx`: hand-labelled dataset, `decision` is the
  label. Uses friendly app names (`Telegram`) instead of package names, and has
  `content_type` / `chat_type` / `conversation_state` filled in by hand.

## Scripts

- `smartmute_data.py`: loaders for both datasets, draft `user_reaction` derivation, the
  rule baseline. Keep in sync with `docs/DATA_SCHEMA.md`.
- `explore.py`: aggregate stats on the newest export and the manual dataset. Prints no
  message text.

```
.venv/bin/python explore.py
```
