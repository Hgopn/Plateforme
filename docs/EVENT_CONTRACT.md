# InterArcade event contract

The backend emits `ia:event` messages using schema version `1`.

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "timestamp": "2026-01-01T00:00:00+00:00",
  "source": "tiktok",
  "tenant_id": "creator-id",
  "session_id": "live-session-id",
  "type": "gift",
  "actor": "viewer-id",
  "payload": {
    "gift": "Rose",
    "count": 1
  }
}
```

Supported event types in V1 are `gift`, `like`, `comment`, `share`, and
`follow`. Game clients must consume `payload` and must not treat browser input
as an authoritative event source. Only the TikTok worker or an authenticated
internal event producer may publish events.
