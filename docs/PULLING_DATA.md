# Pulling logged data from the phone

How to get the notification log from the **SmartMute Dev** app onto the PC as a CSV,
ready for `ml/`. Format of the file: [DATA_SCHEMA.md](DATA_SCHEMA.md#csv-export).

The exported files contain real messages. They go into `ml/data/`, which git ignores;
never copy them anywhere else in the repo, and don't upload them to online services.

## 1. Connect the phone

1. USB debugging must be on (**Settings → Additional settings → Developer options →
   USB debugging**). It stays on once set.
2. Plug in the cable. If the phone asks **"Allow USB debugging?"**, tap **Allow**.
3. Check that the PC sees it:

   ```
   adb devices
   ```

   You should get one line ending in `device`, e.g. `8ad3af11	device`.

## 2. Export on the phone

Open **SmartMute Dev** and tap **Export CSV**. The screen shows the file name, e.g.
`notification_log_20261010_143000.csv`, and a divider line with that name appears in
the log list.

Every tap writes a new, complete file (all rows, not just new ones), so the newest file
is all you need.

## 3. Pull to the PC

From the project folder:

```
adb pull /sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/ ml/data/
```

This copies every export on the phone into `ml/data/exports/`. To pull just one file:

```
adb pull /sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/notification_log_20261010_143000.csv ml/data/
```

The app's Export message shows the same folder as `/storage/emulated/0/Android/...`:
`/sdcard` is a shortcut to `/storage/emulated/0`, so either path works.

To see which exports are on the phone:

```
adb shell ls -l /sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/
```

## 4. Check it

```
cd ml
.venv/bin/python explore.py
```

It uses the newest `notification_log_*.csv` anywhere under `ml/data/` and prints row
counts per app, removal reasons and `user_reaction` totals, but no message text. To
check a specific file, pass its path: `.venv/bin/python explore.py data/exports/<file>.csv`.

To look at rows by eye, open the CSV in LibreOffice Calc (`localc <file>`) with the
settings in [LABEL_REVIEW.md → Opening a CSV in Calc](LABEL_REVIEW.md#opening-a-csv-in-calc).

Next step, preparing the data for labelling: [LABEL_REVIEW.md](LABEL_REVIEW.md).

## Optional: clean up the phone

Old exports can be deleted from the phone after pulling them:

```
adb shell rm /sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/notification_log_20261003_100523.csv
```

Its divider line in the log list disappears with it. The logged rows themselves stay in
the app's database.

## Troubleshooting

| Problem | Fix |
|---|---|
| `adb devices` lists nothing | Try another cable or USB port, and set USB mode to **File transfer** in the phone's notification. |
| Device shows `unauthorized` | Unlock the phone and tap **Allow** on the USB debugging prompt. If none appears: Developer options → **Revoke USB debugging authorizations**, then replug. |
| `adb: command not found` | Use the full path: `~/Android/Sdk/platform-tools/adb`. |
| `does not exist` on pull | No export yet (tap Export CSV first), or a typo in the path: it's `smartmute.dev`, the dev app. |
| No new rows since the last export | HyperOS may have stopped the listener. Check that SmartMute Dev has Autostart on and Battery saver → No restrictions; then turn its notification access off and on (Settings search: "Notification access"). |
