# Telegram Notifications

## Goal

Let each authenticated Deep Foundry user connect a private Telegram chat and
receive selected workspace notifications without entering a phone number or
chat ID.

## User flow

1. The user opens **Settings > Notifications** and selects **Connect Telegram**.
2. Deep Foundry creates a short-lived, single-use link session. Only a SHA-256
   hash of its opaque token is stored.
3. The UI opens the returned `https://t.me/<bot>?start=<token>` link (and may
   show it as a QR code).
4. The user taps **Start** in a private chat with the bot.
5. Telegram sends the update to Deep Foundry's webhook. Deep Foundry validates
   the webhook secret, consumes the token atomically, and binds the Telegram
   account to the user that created the link session.
6. The browser polls the link-session status and shows the connected account.
7. The user enables notification types per workspace.

Phone numbers and manually supplied Telegram identifiers are never accepted.

## Data model

- `TelegramConnection`: one verified Telegram account/private chat per user.
- `TelegramLinkSession`: a short-lived, single-use, hashed linking token.
- `TelegramNotificationPreference`: one set of event choices per user and
  workspace.
- `TelegramDelivery`: durable delivery state for each notification.

Telegram numeric identifiers are serialized as strings in the API to avoid
JavaScript integer precision problems. The deployment-wide bot token and
webhook secret remain environment variables and are never stored in user or
workspace data.

## API

- `GET /api/v1/telegram/connection`
- `POST /api/v1/telegram/link-sessions`
- `GET /api/v1/telegram/link-sessions/{id}`
- `DELETE /api/v1/telegram/connection`
- `GET /api/v1/telegram/preferences?workspace_id=<uuid>`
- `PATCH /api/v1/telegram/preferences?workspace_id=<uuid>`
- `POST /api/v1/telegram/test`
- `POST /api/v1/webhooks/telegram` (Telegram only)

Authenticated endpoints only expose records owned by `request.user`.
Workspace preference and test operations require workspace membership.

## Security invariants

- Link tokens contain at least 256 bits of entropy, fit Telegram's 64-character
  start-parameter limit, expire after 10 minutes, and can be consumed once.
- Raw link tokens are returned once and are never persisted or logged.
- Linking is accepted only from a Telegram `private` chat where
  `message.from.id == message.chat.id`.
- Webhooks require an exact, constant-time match for
  `X-Telegram-Bot-Api-Secret-Token`.
- A Telegram user ID already linked to another Deep Foundry user cannot be
  claimed with a new token.
- Disconnecting removes the connection and its pending link sessions and
  preferences; audit entries do not contain Telegram chat IDs or link tokens.
- Notification messages contain a short title and Deep Foundry link. Sensitive
  task results, prompts, errors, monitored page contents, and document bodies
  are excluded.
- Telegram API calls use a fixed configured API origin, bounded timeouts, and
  bounded response reads; no user-controlled URL is fetched.

## Notification events

The first release supports:

- task completed
- research completed
- website changed
- approval requested
- workflow/task failed
- website monitor failed

Task, research, and approval events default on. Change and failure events
default on. Mentions and billing are not sent to Telegram in this release.

## Delivery behavior

Creating an in-app notification remains the source of truth. Email and
Telegram delivery are independent best-effort Celery jobs. Telegram jobs check
the connection and current workspace preference again before sending.
`TelegramDelivery` prevents routine duplicate sends and records sent, skipped,
and failed outcomes. As with any external messaging API without an idempotency
key, a worker crash after Telegram accepts a message but before the database
commit can still produce an at-least-once duplicate on retry.

## Operations

Telegram is disabled when its three settings are absent:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`
- `TELEGRAM_WEBHOOK_SECRET`

When any one is set, all three must be set. Production operators register
`<WEB_APP_URL>/api/v1/webhooks/telegram` with Telegram using the included
management command. The command never prints the bot token or webhook secret.

## Out of scope

- Telegram groups and channels
- phone-number-based discovery
- reading or retaining unrelated user messages
- incoming commands other than the one-time `/start` link flow
- job-specific alerts until a job-search feature creates a supported
  notification event
