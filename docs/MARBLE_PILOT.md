# Marble V2 pilot

## Runtime flow

1. The launcher creates a licensed `marble` session.
2. Marble calls `POST /api/v1/sessions/<session_id>/games/marble/start` with
   its configuration and receives a persisted round state.
3. The Socket.IO client authenticates with the signed session token and
   listens for `ia:game_state` messages filtered by `game_id` and
   `session_id`.
4. TikTok events enter through the normalized version-1 `ia:event` contract.
   The API persists the event idempotently, applies the event to the active
   round, and broadcasts the resulting authoritative state.
5. A target reached by gifts or likes changes the round to `finished` exactly
   once. Further events cannot change its score or winner.
6. `POST /api/v1/sessions/<session_id>/games/marble/start` with `reset: true`
   starts the next round. `POST /api/v1/sessions/<session_id>/end` closes the
   live session.

## Configuration

The launcher currently sends:

- `gift_target`;
- `like_target`;
- `like_unit` (likes required for one server-side like point);
- `lion_multiplier` remains available in the server contract for special
  gifts.

Values are validated and clamped server-side. The client cannot change a
score directly.

## Current boundary

The local demo provides a test session and simulated events. TikTok account
selection, official login and live detection remain placeholders until a test
TikTok account and the required approved integration credentials are supplied.
No public live or public deployment is started by this pilot.
