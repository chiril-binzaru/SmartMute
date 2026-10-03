# Data schema

Reference for the `notification_log` Room table (`data/NotificationLog.kt`) and for
the CSV exported from it. Column names are identical in Room and in the CSV; the CSV
adds one derived column, `removal_reason_name` (see [CSV export](#csv-export)).

If you change the entity, update this file in the same commit.

## How rows are written

**One row per logged notification.** `NotificationLoggerService.onNotificationPosted`
inserts a row. Messengers re-post under the same `notification_key` for each new
message in a chat, so one chat produces many rows sharing a key.

**Not logged:**
- notifications posted by SmartMute itself
- group summaries (`FLAG_GROUP_SUMMARY`), which duplicate their children
- ongoing and foreground-service notifications (`FLAG_ONGOING_EVENT`,
  `FLAG_FOREGROUND_SERVICE`): media players, downloads, navigation, etc.
- a re-post whose key, `sender_id` and `message_text` match the latest row for that
  key while it is still open, i.e. an update with no new content
- notifications already on screen when the listener starts

**On removal.** `onNotificationRemoved` updates every row with that key whose
`removed_at` is still null. Opening a chat with three unread messages therefore closes
three rows at once, each with its own `time_to_open_sec`.

## Columns

Types are SQLite storage types. Booleans are stored as `INTEGER` 0/1. Times ending in
`_at` or named `timestamp` are Unix epoch milliseconds; `*_sec` columns are seconds.

"Filled" says when the value is written:
- **post**: when the notification arrives
- **removal**: in `onNotificationRemoved`
- **derived**: not written by the app yet; to be computed from the raw columns
  (on-device later, or in the Python pipeline)
- **dev**: debug builds only, never in production

### Identity and source

| Column | Type | Null? | Filled | Source / meaning |
|---|---|---|---|---|
| `message_id` | INTEGER | no | post | Primary key, auto-generated. Unique per row. |
| `notification_key` | TEXT | no | post | `StatusBarNotification.getKey()`. **Not unique**: reused per chat. Used to match removal events. Indexed. |
| `timestamp` | INTEGER | no | post | `sbn.postTime`, epoch ms. |
| `sender_id` | TEXT | yes | post | `Notification.EXTRA_TITLE`. In group chats this is often the group name, not the person. Indexed. |
| `app_package` | TEXT | no | post | `sbn.packageName`, e.g. `org.telegram.messenger`, `com.whatsapp`. |
| `message_text` | TEXT | yes | post | First non-null of: text of the last `MessagingStyle` message, `EXTRA_BIG_TEXT`, `EXTRA_TEXT`. Empty or null for media with no caption. |
| `time_since_last_msg_from_sender_sec` | INTEGER | yes | post | Seconds since the previous logged row with the same `app_package` + `sender_id`. Null for the first message from a sender or when `sender_id` is null. |

### Raw source data for later derivation

| Column | Type | Null? | Filled | Source / meaning |
|---|---|---|---|---|
| `raw_conversation_title` | TEXT | yes | post | `MessagingStyle.conversationTitle`. Usually set for group chats. |
| `raw_sub_text` | TEXT | yes | post | `EXTRA_SUB_TEXT`. Gmail typically shows the account address here. |
| `raw_is_group_conversation` | INTEGER | yes | post | `MessagingStyle.isGroupConversation`. Null when the notification has no MessagingStyle. |
| `raw_category` | TEXT | yes | post | `Notification.category`, e.g. `msg`, `email`, `social`. |
| `raw_template` | TEXT | yes | post | `EXTRA_TEMPLATE`, e.g. `android.app.Notification$MessagingStyle`. |
| `raw_has_picture` | INTEGER | no | post | 1 if `EXTRA_PICTURE` is set or the last MessagingStyle message has an `image/*` MIME type. |

### Removal

| Column | Type | Null? | Filled | Source / meaning |
|---|---|---|---|---|
| `removed_at` | INTEGER | yes | removal | Epoch ms when the listener saw the removal. Null while the notification is still showing. |
| `removal_reason` | INTEGER | yes | removal | `NotificationListenerService.REASON_*` code, see [below](#removal-reason-codes). Null on API < 26, where Android doesn't report a reason. |
| `time_to_open_sec` | INTEGER | yes | removal | `(removed_at - timestamp) / 1000`, **only** when `removal_reason = 1` (tapped). Null for every other reason. |

### Derived (columns exist, not filled yet)

| Column | Type | Values |
|---|---|---|
| `content_type` | TEXT | `text` / `photo` / `video` / `voice` / `file` / `sticker` / `emoji_only` / `reaction` |
| `chat_type` | TEXT | `dm` / `group` / `channel` / `broadcast` |
| `conversation_state` | TEXT | `last_msg_was_question` / `last_msg_was_answer` / `neutral` |
| `user_reaction` | TEXT | `opened_immediately` (`time_to_open_sec` ≤ 300) / `opened_later` (300 s – 24 h) / `ignored` (> 24 h or never opened) |
| `decision` | TEXT | `sound` / `silent`: what the decision engine chose. Filled once step 2 lands. |

### Dev-only feedback

Only ever written in debug builds (see "Architectural constraint" in `CLAUDE.md`).

| Column | Type | Values |
|---|---|---|
| `feedback` | TEXT | `correct` / `incorrect` / `none` |
| `corrected_decision` | TEXT | `sound` / `silent`, when `feedback = incorrect` |

## Removal reason codes

Values of `removal_reason`, from `NotificationListenerService.REASON_*` in the
android-37 SDK sources. The database stores the number; the CSV export adds the
name (without the `REASON_` prefix) as `removal_reason_name`, so new codes never require
a migration.

"Opened?" is how the value should be read for `user_reaction`.

| Code | Constant | Meaning | Opened? | Since API |
|---|---|---|---|---|
| 1 | `REASON_CLICK` | User tapped the notification | **yes** | 26 |
| 2 | `REASON_CANCEL` | User swiped it away | no | 26 |
| 3 | `REASON_CANCEL_ALL` | User tapped "Clear all" | no | 26 |
| 4 | `REASON_ERROR` | System UI failed to render it | – | 26 |
| 5 | `REASON_PACKAGE_CHANGED` | Posting app was modified (e.g. disabled) | – | 26 |
| 6 | `REASON_USER_STOPPED` | Owning user was stopped | – | 26 |
| 7 | `REASON_PACKAGE_BANNED` | User blocked the app's notifications | – | 26 |
| 8 | `REASON_APP_CANCEL` | App cancelled it, typically because the message was read inside the app | see below | 26 |
| 9 | `REASON_APP_CANCEL_ALL` | App cancelled all its notifications | see below | 26 |
| 10 | `REASON_LISTENER_CANCEL` | A notification listener dismissed it | no | 26 |
| 11 | `REASON_LISTENER_CANCEL_ALL` | A notification listener dismissed all | no | 26 |
| 12 | `REASON_GROUP_SUMMARY_CANCELED` | Its group summary was cancelled | – | 26 |
| 13 | `REASON_GROUP_OPTIMIZATION` | Invisible group member was dropped | – | 26 |
| 14 | `REASON_PACKAGE_SUSPENDED` | Device admin suspended the app | – | 26 |
| 15 | `REASON_PROFILE_TURNED_OFF` | Work profile was turned off | – | 26 |
| 16 | `REASON_UNAUTOBUNDLED` | Auto-bundled summary removed after unbundling | – | 26 |
| 17 | `REASON_CHANNEL_BANNED` | User blocked the notification channel | – | 26 |
| 18 | `REASON_SNOOZED` | User snoozed it | no | 26 |
| 19 | `REASON_TIMEOUT` | App-set timeout expired | no | 26 |
| 20 | `REASON_CHANNEL_REMOVED` | App deleted the channel | – | 31 |
| 21 | `REASON_CLEAR_DATA` | App's storage was cleared | – | 31 |
| 22 | `REASON_ASSISTANT_CANCEL` | Notification assistant cancelled it | – | 33 |
| 23 | `REASON_LOCKDOWN` | Lockdown mode entered (restored on exit) | – | 34 |
| 24 | `REASON_BUNDLE_DISMISSED` | Its bundle (e.g. Promotions) was dismissed | no | 36.1 |

"–" means the removal says nothing about the user's attention; exclude these rows
from `user_reaction` labelling or treat them as unknown.

**Codes 8 and 9 (app cancel)** usually mean the user read the chat in the app directly
(or on another device, e.g. Telegram Desktop) without tapping the notification. That is
still an "opened" signal, but `time_to_open_sec` is currently only set for code 1.
Decide how to treat 8/9 once real device data shows how often it happens.

## CSV export

**Dev builds only.** A "[dev] Export CSV" button on the main screen, shown only when
`BuildConfig.DEBUG` (`export/CsvExporter.kt`). Each tap writes a new file:

```
/sdcard/Android/data/com.github.chirilbinzaru.smartmute/files/exports/notification_log_<yyyyMMdd_HHmmss>.csv
```

Pull every export with:

```
adb pull /sdcard/Android/data/com.github.chirilbinzaru.smartmute/files/exports/ .
```

**Format.** RFC 4180:
- UTF-8, no BOM; CRLF between records
- header row first; rows ordered by `message_id`
- a field is wrapped in double quotes when it contains a comma, a double quote, CR or
  LF, and inner double quotes are doubled. `message_text` can span several lines
  inside quotes, so read it with a real CSV parser (`pandas.read_csv`, Python `csv`),
  never by splitting lines
- SQL `NULL` is an empty field, so null and empty string can't be told apart
  (pandas reads both as `NaN`)
- values are written as stored: epoch-ms times, 0/1 booleans, integer reason codes

**Columns.** Every column of `notification_log`, in table order (header taken from the
table itself, so it can't drift from the schema), followed by:

| Column | Meaning |
|---|---|
| `removal_reason_name` | Name for `removal_reason`, e.g. `CLICK`, `CANCEL`, `APP_CANCEL`; `UNKNOWN_<n>` for codes not in the table above; empty when `removal_reason` is null. |

## Device notes

To be filled in from on-device testing: whether HyperOS and each messenger actually
report the expected codes (tap → 1, swipe → 2, read in app → 8).
