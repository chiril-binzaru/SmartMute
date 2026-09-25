# Smart Notification Muting — Android + on-device ML

## Idea

An Android app that intercepts messenger notifications and decides whether
a notification should play sound or stay silent, based on message content
and conversation context — not via rigid user rules (like DND), but via a
model trained on the user's actual behavior.

**Pain it solves:** DND is a binary switch (all or nothing), which means
either important messages get missed (close people get anxious when they
don't get a reply) or focus gets broken by unimportant noise (photos,
closing replies like "ok", group chat chatter).

**Product principle:** the app exists to REMOVE decisions from the user
("should I check my phone right now"), not add new ones. This drives the
architectural constraint below.

## Core decision

One output per notification: `sound` / `silent`. Everything else
(end-of-day prioritized list, digest of unread/muted channels) is a
secondary feature, not core.

## Architectural constraint: feedback is dev-only

**Feedback buttons (👍/👎 was this decision correct) exist ONLY in the
debug/dev build, gated behind `BuildConfig.DEBUG` or a separate dev flag.**

Reason: if the end user has to confirm on every notification whether the
decision was correct, we're trading "minus one decision" for "plus one
decision" — which undermines the entire point of the app. The production
version for regular users must learn from **passive** signals instead:
- `onNotificationRemoved` — when and how a notification was
  dismissed/read
- time to open (`time_to_open_sec`)
- implicit correction: if the user manually opens a silent notification
  almost immediately after receiving it — signal that the decision was
  wrong (should have been sound)
- if the user doesn't open a sound notification for a long time — weak
  signal that it could have been silent

Explicit feedback (buttons) is a tool ONLY for the development /
personal-model-training stage, not for the production build.

## Tech stack

- **Android Studio + Kotlin** — `NotificationListenerService` is a deeply
  native Android API; cross-platform frameworks (Flutter/RN) don't offer
  any advantage here since iOS has no equivalent API for reading other
  apps' notifications
- **Room** — local storage for notification logs and (dev build only)
  feedback
- **ONNX Runtime Mobile** — on-device inference of sentence-transformer
  embeddings (`intfloat/multilingual-e5-small`, multilingual — works for
  ru/ro/en without retraining)
- **LightGBM / MLP (PyTorch)** — classifier on top of the embedding + hand
  features; this is the core ML-learning part of the project, trained/
  retrained on the user's own data. Training happens offline on a PC,
  inference on-device
- **WorkManager** — background tasks (periodic retraining / weight updates)
- **No backend for MVP** — everything runs on-device, nothing leaves the
  phone (except optionally for cold-start label generation via an LLM API)

## Notification channels (required, Android 8+)

Notification sound is hard-tied to a notification channel, not settable
per-notification. Need at least two channels:
- `loud_channel` — importance HIGH, with sound
- `silent_channel` — importance LOW, no sound

Flow: `NotificationListenerService` intercepts the original notification →
`cancelNotification()` → repost through the appropriate channel based on
the decision engine's output.

## Data schema (Room / CSV for training)

```
message_id                              -- notification.getKey() in prod
timestamp
sender_id                               -- EXTRA_TITLE from the notification
app_package                             -- Telegram/Viber/WhatsApp/SMS/Gmail/...
content_type                            -- text/photo/video/voice/file/
                                         -- sticker/emoji_only/reaction
message_text                            -- empty for media with no caption
chat_type                               -- dm/group/channel/broadcast
time_since_last_msg_from_sender_sec
conversation_state                      -- last_msg_was_question/
                                         -- last_msg_was_answer/neutral
user_reaction                           -- opened_immediately (≤300s) /
                                         -- opened_later (300s–24h) /
                                         -- ignored (>24h or never opened)
time_to_open_sec
decision                                -- sound/silent — what the engine decided
feedback                                -- [DEV ONLY] correct/incorrect/none
corrected_decision                      -- [DEV ONLY] if incorrect
```

## Feature engineering for the classifier

Beyond the raw fields above:

- `has_qmark` — presence of "?" in the text (weak signal in practice on
  the current test data — don't overweight it)
- `text_len`
- `is_media` — content_type in [photo, video, voice, file]
- **Sender prior (key finding):** `chat_type` alone is a weak aggregate —
  real importance depends on the specific sender (confirmed on data:
  sound_rate within dm ranges from 0% to 100% depending on sender_id).
  Needs a personalized prior:

```
history_length                = count of past messages from this sender_id
                                 (computed ONLY from data BEFORE the
                                 current message — otherwise data leakage)
sender_historical_sound_rate  = share of sound among past decisions for
                                 this sender_id (fallback = global_prior
                                 when history_length = 0)
adjusted_rate (IMDB/Bayesian shrinkage):
    adjusted_rate = (v × R + m × C) / (v + m)
    where v = history_length, R = sender_historical_sound_rate,
          C = global_prior (mean sound_rate across all senders),
          m = trust threshold (3–5)
```

Feed the classifier BOTH the raw features (`history_length`,
`sender_historical_sound_rate`) and the derived `adjusted_rate` — trees
are robust to redundant/correlated features and can fine-tune what a
fixed `m` doesn't capture.

## Experiment status (on a 200-row manual dataset)

- Rule-based baseline (content_type=reaction/sticker→silent;
  conversation_state=question→sound; group/channel/broadcast→silent;
  photo→silent; else sound): **68.5% accuracy**
- LightGBM (5-fold CV) on the full feature set: **66.5% (±8.6%)** —
  **did not beat the baseline**, within noise. Expected: 200 rows isn't
  enough for gradient boosting, especially with categorical features
  (chat_type/content_type/app_package got zero importance — not enough
  data for stable splits)
- Conclusion: rely on the rule-based baseline in production for now,
  accumulate real automatic logs through the app, revisit the ML
  classifier once there's substantially more data (hundreds to
  thousands of examples)

## Implementation order

1. `NotificationListenerService` — just log incoming notifications to
   Room, no decisions yet (verify interception works for Telegram/
   Viber/WhatsApp/SMS/Gmail)
2. Two notification channels + rule-based decision engine (the same one
   that scored 68.5%) — repost notifications through the right channel
3. `onNotificationRemoved` — log user_reaction / time_to_open_sec with
   no user involvement
4. [DEV BUILD ONLY] Feedback actions (👍/👎) on the notification →
   write to Room
5. Export Room → CSV → same Python pipeline (feature engineering +
   LightGBM) once enough data accumulates
6. ONNX Runtime Mobile integration — after the classifier trained on a
   PC shows quality better than the baseline

## Explicitly out of core scope (discussed and deliberately deferred)

- Digest of unread/muted channels (Instagram with push disabled, class
  group chat) — separate feature, not part of the sound/silent decision
- Cross-platform (iOS) — technically not possible at the API level,
  Apple provides no access to other apps' notifications
- Cloud backend / cross-device sync — not needed for MVP
