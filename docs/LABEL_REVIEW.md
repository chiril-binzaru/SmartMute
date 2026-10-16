# Reviewing labels

How to turn an export into a review file with `ml/prelabel.py`, correct the labels in
LibreOffice Calc, and save it back without breaking it. Getting the export first:
[PULLING_DATA.md](PULLING_DATA.md). Column meanings: [DATA_SCHEMA.md](DATA_SCHEMA.md).

Review files contain real messages, like the exports. Keep them under `ml/data/` (git
ignores it).

## 1. Create the review file

From `ml/`:

```
.venv/bin/python prelabel.py --input data/exports/notification_log_20261010_143000.csv \
                             --output data/review/notification_log_20261010_143000_review.csv
```

| Option | Meaning |
|---|---|
| `--input` | The export from the app. Read only, never changed. |
| `--output` | The review file to write. Must be a different file; the folder is created if needed. |
| `--overwrite` | Replace `--output` if it already exists. Without it the script refuses. |

It prints counts per value (how many `group`, `photo`, `sound`, …) and how many cells it
filled; it never prints message text or names.

What it does:
- fills **`content_type`**, **`chat_type`** and **`conversation_state`** from the raw
  columns and the message text (rules: comments in `ml/prelabel.py`)
- pre-fills **`decision`** (`sound` / `silent`) with the rule baseline from CLAUDE.md
- adds a last column **`prelabel_rule`** naming the rule that set the decision:

  | `prelabel_rule` | Rule |
  |---|---|
  | `reaction_or_sticker` | reaction or sticker → silent |
  | `question` | previous message was a question → sound |
  | `group_channel_broadcast` | group, channel or non-messenger app → silent |
  | `photo` | photo → silent |
  | `default` | none of the above → sound |

- sorts rows by `sender_id`, then by time, so each sender's messages are together and in
  order; rows without a sender come last

It only fills **empty** cells. Running it again on a reviewed file changes nothing you've
filled in, so it's safe to re-run, e.g. after a new export (see step 4).

## 2. Open it in LibreOffice Calc

```
localc data/review/notification_log_20261010_143000_review.csv
```

The **Text Import** dialog opens. See [Opening a CSV in Calc](#opening-a-csv-in-calc)
below; for reviewing, use the **review settings** (every column as Text).

## 3. Review

Work sender by sender. For each row, check **`decision`**: should this message have made
a sound? Fix it if not. If you see that a derived field is wrong (e.g. a channel marked
`dm`), fix that too; those values become model features.

Allowed values (anything else breaks training later):

| Column | Values |
|---|---|
| `decision` | `sound`, `silent` |
| `content_type` | `text`, `photo`, `video`, `voice`, `file`, `sticker`, `emoji_only`, `reaction` |
| `chat_type` | `dm`, `group`, `channel`, `broadcast` |
| `conversation_state` | `last_msg_was_question`, `last_msg_was_answer`, `neutral` |

When you've checked a row, set its **`prelabel_rule`** to **`reviewed`**, whether you
changed the decision or not. That's how reviewed rows can later be told apart from
rows the script pre-filled and nobody looked at.

Tips:
- **Data → AutoFilter** on the header row lets you show one sender, one `prelabel_rule`
  or one `chat_type` at a time.
- **View → Freeze Cells → Freeze First Row** keeps the column names visible.
- Hide columns you don't need while reviewing (select, right-click → **Hide Columns**);
  hidden columns are still saved.
- Don't sort, delete or add rows, and don't rename or reorder columns.

## 4. Save

**File → Save** (Ctrl+S). Calc asks whether to keep the format: choose **Use Text CSV
Format!**. Details: [Saving a CSV from Calc](#saving-a-csv-from-calc).

To continue later, open the same file again with the review settings. After a new
export, run `prelabel.py` with the new export as `--input` and a new `--output`; merging
earlier reviews into a new export isn't automated yet.

## Opening a CSV in Calc

Applies to both exports and review files. In the **Text Import** dialog:

**Import**
- **Character set:** Unicode (UTF-8)
- **From row:** 1 (row 1 is the column names)

**Separator Options**
- **Separated by:** tick **Comma** only (untick Tab, Semicolon, Space, Other)
- **Merge delimiters:** off
- **Trim spaces:** off (messages must stay exactly as they are)
- **String delimiter:** `"` (double quote)

**Other options** (some are missing in older versions; that's fine)
- **Format quoted field as text:** on
- **Detect special numbers:** off (otherwise `1-2` or `3/4` turn into dates)
- **Detect numbers in scientific notation:** off
- **Evaluate formulas:** off (otherwise a message starting with `=` is calculated)

**Fields** (the preview table at the bottom)
- **Review settings, for files you'll edit and save:** click the empty top-left corner of
  the preview to select all columns, then set **Column type: Text**. Every value is then
  kept and saved exactly as it was: long numbers aren't rounded, `+373…` stays a phone
  number, `=)` stays text.
- **Browse settings, for just looking:** leave columns as Standard, but set
  `sender_id`, `message_text`, `notification_key`, `raw_conversation_title` and
  `raw_sub_text` to **Text** (click a column header, Ctrl+click the others, then
  **Column type: Text**). Numbers stay numbers, so you can sort or compute with them,
  but don't save this file back over a CSV you need.

Click **OK**. Each notification is one row; a message with line breaks shows as wrapped
text inside a single cell.

Timestamps are epoch milliseconds. To read one in browse mode, in a free column:
`=A2/86400000+DATE(1970;1;1)` (replace `A2` with the timestamp cell) and format the cell
as date-time. That's UTC; add your offset (+3 h in summer, +2 h in winter).

## Saving a CSV from Calc

1. **File → Save** (Ctrl+S). In the **Keep current format** prompt, choose **Use Text
   CSV Format!**. If no options dialog follows and you want to check the settings, use
   **File → Save As…**, tick **Edit filter settings**, and save under the same name.
2. In **Export Text File**:
   - **Character set:** Unicode (UTF-8)
   - **Field delimiter:** `,`
   - **String delimiter:** `"`
   - **Save cell content as shown:** on
   - **Quote all text cells:** off
   - **Fixed column width:** off
3. **Close the file in Calc when done.** While it's open, Calc keeps a
   `.~lock.<file>#` file next to it (git ignores these).

Never save over an original export (`data/exports/…`). Review in a separate file made
by `prelabel.py`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Cyrillic or Romanian letters look garbled | Character set wasn't UTF-8. Close without saving and reopen. |
| Everything in one column | Comma wasn't ticked as the separator. |
| Rows split in the middle of a message | String delimiter wasn't `"`. Close without saving and reopen. |
| Long numbers show as `1.79E+12` | Opened with browse settings; harmless for looking, but use review settings for files you save. |
| `prelabel.py` says the output exists | Choose another `--output`, or add `--overwrite` if you mean to replace it (never use your reviewed file as `--output`). |
| `prelabel.py` says "missing columns" or "non-numeric timestamp" | The file isn't an export or review file, or was saved from Calc with browse settings and numbers got reformatted. Re-create it from the original export. |
