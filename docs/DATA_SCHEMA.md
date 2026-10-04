# Data schema

Reference for the `notification_log` Room table (`data/NotificationLog.kt`) and for
the CSV exported from it. Column names are identical in Room and in the CSV; the CSV
adds one derived column, `removal_reason_name` (see [CSV export](#csv-export)).

If you change the entity, update this file in the same commit.

## How rows are written

**One row per incoming message.** Messengers keep all unread messages of a chat in one
`MessagingStyle` notification and re-post it under the same `notification_key` as
messages arrive. `NotificationLoggerService.onNotificationPosted` logs one row for each
message in it that's newer (by `raw_message_time`) than the newest already logged for
that key, or has the same time but a text not yet logged at that time (Telegram stamps
messages to the second). Several messages delivered at once become several rows. Notifications
without MessagingStyle (Gmail, system apps) get one row each.

Schema v1 (before 2026-10-04) logged only the last message of each post, so a burst of
messages delivered together became a single row.

**Not logged:**
- notifications posted by SmartMute itself
- group summaries (`FLAG_GROUP_SUMMARY`), which duplicate their children
- ongoing and foreground-service notifications (`FLAG_ONGOING_EVENT`,
  `FLAG_FOREGROUND_SERVICE`): media players, downloads, navigation, etc.
- the user's own messages in a MessagingStyle notification (null sender), e.g. after an
  inline reply
- a MessagingStyle re-post with no new message; for other notifications, a re-post
  whose key, `sender_id` and `message_text` match the latest row for that key while it
  is still open
- notifications already on screen when the listener starts

**On removal.** `onNotificationRemoved` updates every row with that key whose
`removed_at` is still null. Opening a chat with three unread messages therefore closes
three rows at once, each with its own `time_to_open_sec`.

**On app restart.** Viber clears all its notifications when its process restarts (code
9) and then posts the unread messages again. When a re-posted notification contains a
message whose row was closed with code 9, that row is reopened (`removed_at`,
`removal_reason`, `time_to_open_sec` reset to null), so it gets the outcome of the
re-posted notification. Data from schema v1 is fixed up offline instead
(`resolve_reposts` in `ml/smartmute_data.py`).

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
| `timestamp` | INTEGER | no | post | `sbn.postTime`, epoch ms: when the notification arrived. Messages delivered in one notification share it; order them by `message_id` (or `raw_message_time`). |
| `sender_id` | TEXT | yes | post | `Notification.EXTRA_TITLE`. In group chats this is often the group name, not the person. Indexed. |
| `app_package` | TEXT | no | post | `sbn.packageName`, e.g. `org.telegram.messenger`, `com.whatsapp`. |
| `message_text` | TEXT | yes | post | Text of this row's `MessagingStyle` message; for other notifications `EXTRA_BIG_TEXT`, else `EXTRA_TEXT`. Empty or null for media with no caption. |
| `time_since_last_msg_from_sender_sec` | INTEGER | yes | post | Seconds since the previous logged row with the same `app_package` + `sender_id`; for the 2nd+ message of a burst delivered in one notification, seconds since the previous message in it (by `raw_message_time`). Null for the first message from a sender or when `sender_id` is null. |

### Raw source data for later derivation

| Column | Type | Null? | Filled | Source / meaning |
|---|---|---|---|---|
| `raw_conversation_title` | TEXT | yes | post | `MessagingStyle.conversationTitle`. Usually set for group chats. |
| `raw_sub_text` | TEXT | yes | post | `EXTRA_SUB_TEXT`. Gmail typically shows the account address here. |
| `raw_is_group_conversation` | INTEGER | yes | post | `MessagingStyle.isGroupConversation`. Null when the notification has no MessagingStyle. |
| `raw_category` | TEXT | yes | post | `Notification.category`, e.g. `msg`, `email`, `social`. |
| `raw_template` | TEXT | yes | post | `EXTRA_TEMPLATE`, e.g. `android.app.Notification$MessagingStyle`. |
| `raw_has_picture` | INTEGER | no | post | 1 if `EXTRA_PICTURE` is set or this row's MessagingStyle message has an `image/*` MIME type. |
| `raw_message_time` | INTEGER | yes | post | `MessagingStyle.Message` timestamp, epoch ms: identifies the message within the notification. Null for non-MessagingStyle notifications and for all rows logged by schema v1. Last column of the table (added by migration). |

### Removal

| Column | Type | Null? | Filled | Source / meaning |
|---|---|---|---|---|
| `removed_at` | INTEGER | yes | removal | Epoch ms when the listener saw the removal. Null while the notification is still showing. |
| `removal_reason` | INTEGER | yes | removal | `NotificationListenerService.REASON_*` code, see [below](#removal-reason-codes). Null on API < 26, where Android doesn't report a reason. |
| `time_to_open_sec` | INTEGER | yes | removal | `(removed_at - timestamp) / 1000` when the removal counts as opened (`removal_reason` 1 or 8, see [user_reaction](#user_reaction)). Null for every other reason. Rows logged by schema v1 only have it for code 1; compute it from `removed_at` instead. |

### Derived (columns exist, not filled yet)

| Column | Type | Values |
|---|---|---|
| `content_type` | TEXT | `text` / `photo` / `video` / `voice` / `file` / `sticker` / `emoji_only` / `reaction` |
| `chat_type` | TEXT | `dm` / `group` / `channel` / `broadcast` |
| `conversation_state` | TEXT | `last_msg_was_question` / `last_msg_was_answer` / `neutral` |
| `user_reaction` | TEXT | `opened_immediately` / `opened_later` / `ignored`; see [user_reaction](#user_reaction). Derived offline for now (`derive_user_reaction` in `ml/smartmute_data.py`). |
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

"Opened?" is how the value is read for [`user_reaction`](#user_reaction).

| Code | Constant | Meaning | Opened? | Since API |
|---|---|---|---|---|
| 1 | `REASON_CLICK` | User tapped the notification | **yes** | 26 |
| 2 | `REASON_CANCEL` | User swiped it away | no | 26 |
| 3 | `REASON_CANCEL_ALL` | User tapped "Clear all" | no | 26 |
| 4 | `REASON_ERROR` | System UI failed to render it | – | 26 |
| 5 | `REASON_PACKAGE_CHANGED` | Posting app was modified (e.g. disabled) | – | 26 |
| 6 | `REASON_USER_STOPPED` | Owning user was stopped | – | 26 |
| 7 | `REASON_PACKAGE_BANNED` | User blocked the app's notifications | – | 26 |
| 8 | `REASON_APP_CANCEL` | App cancelled it: chat read inside the app, or "Mark as read" | **yes** | 26 |
| 9 | `REASON_APP_CANCEL_ALL` | App cancelled all its notifications; for Viber mostly an app restart | see [user_reaction](#user_reaction) | 26 |
| 10 | `REASON_LISTENER_CANCEL` | A notification listener dismissed it | no | 26 |
| 11 | `REASON_LISTENER_CANCEL_ALL` | A notification listener dismissed all | no | 26 |
| 12 | `REASON_GROUP_SUMMARY_CANCELED` | Its group summary was cancelled | – (not yet tested) | 26 |
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

## user_reaction

The passive label for training, derived from how a notification was removed. Decided
2026-10-04 from on-device tests (see [Device notes](#device-notes)).

| Removal | user_reaction |
|---|---|
| Opened (code 1 or 8), `removed_at - timestamp` ≤ 300 s | `opened_immediately` |
| Opened, 300 s – 24 h | `opened_later` |
| Opened after more than 24 h | `ignored` |
| Dismissed (code 2, 3, 10, 11, 18, 19, 24) | `ignored` |
| Still showing after 24 h | `ignored` |
| Code 9 not followed by a re-post, code 12, any "–" code, or still showing < 24 h | unknown (excluded from training) |

- **Code 8 counts as opened.** It covers reading the chat in the messenger and tapping
  "Mark as read": in both the user looked at the message. It can also mean the message
  was read on another device or deleted by the sender; accepted as noise.
- **Code 9 doesn't count by itself.** Viber sends it when its process restarts, then
  re-posts the unread messages. The row takes the outcome of the re-posted notification
  (reopened by the app from schema v2; `resolve_reposts` for v1 data). Without a re-post
  it stays unknown.
- **Code 12** stays unknown until tested: swiping a notification group vs tapping it.
- `user_reaction` is not yet the sound/silent label: mapping it (especially
  `opened_later`) to `sound`/`silent` is a separate, later decision.

## CSV export

**`dev` flavor only.** An "Export CSV" button on the main screen
(`app/src/dev/.../export/CsvExporter.kt`); the `user` flavor doesn't contain it. Each
tap writes a new file:

```
/sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/notification_log_<yyyyMMdd_HHmmss>.csv
```

Pull every export with:

```
adb pull /sdcard/Android/data/com.github.chirilbinzaru.smartmute.dev/files/exports/ .
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

Xiaomi Redmi Note 13 Pro 5G, HyperOS 3 (Android 16), tested 2026-10-04 with Viber:

| Action | Lock screen | Unlocked |
|---|---|---|
| Tap the notification (opens the chat) | 1 | 1 |
| Swipe it away | 2 | 2 |
| "Mark as read" action | 8 | 8 |
| Open Viber and the chat directly | 8 | 8 |

- **New message in a chat already on screen:** Viber updates the notification in place
  (same key, no removal); the earlier message's row stays open.
- **Viber process restart:** Viber clears all its notifications (code 9, plus system code
  20 for its channels) and re-posts the unread messages ~2 s later, all in one
  notification. In the first export, 34 of 50 code-9 events were followed by a Viber post
  within 5 s.
- **HyperOS kills background apps** ("OneKeyClean", "SwipeUpClean" in logcat). The
  listener needs Autostart and Battery saver → No restrictions, and after a refused start
  it only reconnects when notification access is toggled or the phone reboots.

Not yet tested: Telegram, WhatsApp, Gmail, SMS; notification groups (code 12); reading
on another device.
