# Live Hub architecture

## Session and source model

A game session is independent of its live sources. It can have no source
(local Test mode), one TikTok source, or several sources at once. Each source
record has its own ID, session ID, tenant ID, platform, creator account ID,
creator username and lifecycle state. The current states are `starting`,
`running`, `stopping`, `stopped`, `error`, and local `simulated`.

`interarcade/worker/live_source.py` defines the `LiveSource` lifecycle
protocol and immutable `LiveSourceBinding`. `TikTokWorker` implements that
protocol. The worker supervisor keys connectors by source ID, so two sources
for one session can run independently. Only TikTok has a real connector now.
No Twitch authentication, SDK, subscription or API call is present.

The admin can attach a TikTok source through
`POST /api/v1/sessions/<session_id>/sources` with `source_platform`,
`source_account_id` and `source_username`. The existing
`/api/v1/listeners/start` and `/api/v1/listeners/stop` routes remain
compatible with the original TikTok flow. An authenticated session can read
its sources at `GET /api/v1/sessions/<session_id>/sources`. The admin can
stop one source at `POST /api/v1/sources/<source_id>/stop`.

In local Demo mode only, the admin may attach a source with
`"simulated": true`; it creates no platform connection. This validates
simultaneous source routing with TikTok and Twitch labels. A non-simulated
Twitch attachment returns `connector_unavailable`. Ending the game session
stops every attached source and closes its Dark or Marble run as before.

## Event boundary

Connectors normalize provider payloads into the versioned InterArcade
envelope described in [EVENT_CONTRACT.md](EVENT_CONTRACT.md). The authenticated
internal ingress checks the tenant, active session and explicit source
binding. It stores the complete envelope in the event outbox and publishes
only to that session's Socket.IO room. Marble applies its server-side rules
once per scoped event ID. Dark receives the same envelope without importing
TikTok or Twitch code. Test mode uses the same normalizer with source
`test`.

Viewer identities are namespaced by platform. The displayed username is
separate from the viewer's platform ID. A future link table may map several
external `actor_id` values to one InterArcade viewer profile. No viewer
account or cross-platform matching exists yet.

## Additive database migration

`Database.initialize()` creates `live_sources` with uniqueness on
`(session_id, platform, account_id)`, copies existing legacy `listeners`
rows once, and adds `event_outbox.envelope_json`. The legacy table and all
old event rows are retained. Historical outbox rows have a null envelope
because their source and viewer metadata was not stored. New event IDs are
scoped; raw provider IDs remain available as `source_event_id`.

## Compatibility notes

Existing games still receive the version 1 aliases, but integrations that
compare `event_id` to a raw provider ID must switch to `source_event_id`.
Legacy TikTok listeners only have a creator username, so that username is
used as `source_account_id` until a stable creator account ID is available.
TikTok viewer IDs use the SDK's numeric ID when present and fall back to its
unique username. If a provider sends no stable event ID, the connector
generates one; retries of that same normalized event are idempotent, while
separate duplicate callbacks still need provider-specific deduplication.

## Completing Twitch later

Add a `LiveSource` implementation with Twitch authentication and approved
credentials, subscribe to Twitch events, extract stable creator and viewer
IDs, normalize payloads through `event_from_source`, and register the
connector in the worker supervisor. Then test reconnects, retries, duplicate
IDs, account revocation, mixed TikTok/Twitch delivery, and production
deployment. Game modules should need no provider-specific change.
