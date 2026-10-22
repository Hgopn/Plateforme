# InterArcade event contract

The API emits provider-neutral `ia:event` messages to the authenticated
Socket.IO room for one game session. The additive schema remains version `1`
so the existing games continue to consume `type`, `actor`, and `payload`.
New game code should use the explicit fields below.

```json
{
  "schema_version": 1,
  "event_id": "ia:session-123:tiktok:creator-42:gift-987",
  "source_event_id": "gift-987",
  "timestamp": "2026-10-13T12:00:00+00:00",
  "tenant_id": "tenant-1",
  "session_id": "session-123",
  "source_platform": "tiktok",
  "source_account_id": "creator-42",
  "source_username": "creator",
  "event_type": "gift",
  "event_value": 2,
  "actor_id": "tiktok:viewer-900",
  "actor_platform_id": "viewer-900",
  "actor_username": "alex",
  "source": "tiktok",
  "type": "gift",
  "actor": "alex",
  "payload": {
    "gift": "Rose",
    "count": 2
  }
}
```

`source_platform` identifies the service, while `source_account_id` and
`source_username` identify the creator account carrying the live stream.
`actor_platform_id` identifies the viewer on that service;
`actor_username` is display text. The stable external viewer key is
`actor_id = source_platform + ":" + escaped(actor_platform_id)`. Never join
viewers by username across services. A future InterArcade viewer profile can
link multiple `actor_id` values without changing this event contract.

`event_id` is scoped by session, platform, source account and the provider's
`source_event_id`. Components are URL escaped before joining, so identical
raw IDs from two platforms or two creator accounts cannot collide.
`event_value` equals the normalized `payload.count` for `gift`, `like`
and `share`; it defaults to `null` for `comment` and `follow`. The timestamp is an
ISO 8601 datetime with a timezone. `source`, `type`, and `actor` are
compatibility aliases; `actor` is a display name and must not be used as an
identity key.

Supported event types are `gift`, `like`, `comment`, `share`, `follow`, and
`action`. An `action` event carries an InterArcade action key in
`payload.action_type`; for Dark, the API accepts only the five keys in
[DARK_LIVE_ACTIONS.md](DARK_LIVE_ACTIONS.md), fixes their duration server-side,
and publishes a separate `ia:action` message with the source and viewer
identity fields preserved. A mapped TikTok action also contains `trigger`
with the original event ID/type and any available gift or like metadata;
see [TIKTOK_DARK_LIVE_TEST.md](TIKTOK_DARK_LIVE_TEST.md). The API accepts old
internal version 1 inputs and fills missing
source metadata for compatibility. New connectors send the complete envelope
through authenticated internal ingress. Explicitly identified sources must
be attached to the active session. Browser input is never an authoritative
source of live events.
