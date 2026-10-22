# TikTok → Dark live test

## Server mapping

The API loads [../config/dark_tiktok_mapping.json](../config/dark_tiktok_mapping.json)
at startup. Set `INTERARCADE_DARK_TIKTOK_MAPPING_PATH` to use another local
JSON file. Edit the file and restart the local API before a test; Dark's game
code does not need changing.

Default rules:

| Original TikTok event | InterArcade Dark action |
| --- | --- |
| Follow | `PLAYER_HELP` |
| Every 50 accepted likes per session and source account | `LIGHT_BOOST` |
| Gift total of 1–9 diamonds | `LIGHT_BOOST` |
| Gift total of 10–99 diamonds | `PLAYER_HELP` |
| Gift total of 100+ diamonds | `REVEAL_MAP` |

The gift total equals the unit diamond value times the finalized
`repeat_count`. One incoming like event can produce at most one action even if
it crosses several thresholds; its full count remains in the persisted total.
Gift ID overrides take precedence over case-insensitive name overrides, then
the diamond tiers. The default file includes `rose` and `galaxy` name
examples. To add a precise rule, add `"12345": "LIGHT_BOOST"` to
`gifts.id_overrides` or `"custom gift": "REVEAL_MAP"` to
`gifts.name_overrides`. A gift without a known diamond value or override is
recorded but produces no Dark action. Unknown event types are recorded and
ignored by the mapper.

The TikTokLive 6.6.1 connector asks the SDK for gift metadata on connect. It
ignores intermediate callbacks for streakable gifts and emits the final
callback with its complete repeat count. Non-streakable gifts are emitted at
once, even when `repeat_end` is false. Native message IDs and timestamps are
used when present; a generated ID/time is used when the SDK omits them.

The original `ia:event` envelope stores `gift_id`, `gift_name`,
`gift_diamond_count`, `gift_total_diamonds`, `repeat_count`, and `repeat_end`
when available. The derived `ia:action` envelope includes `trigger` with the
original event ID/type and the available gift or like fields. Original and
derived events are stored atomically. The like total is persisted in
`dark_live_like_progress`; the table is an additive migration.

## First controlled test with @songmicon

1. Ensure `@songmicon` is broadcasting. No Euler API key is required for a
   standard test: leave `EULER_API_KEY=` empty in the local, ignored
   `.env.integration`. TikTokLive uses its default community signing. If you
   have an approved key for higher limits, place it in that file; never paste
   it into Git, logs, or chat. For detailed event traces, optionally set
   `INTERARCADE_TIKTOK_DARK_TRACE=true` there and restart the stack with
   `./scripts/start.sh`. No connection starts merely by setting these values.
2. Confirm the local stack is running with `./scripts/status.sh` (start it with
   `./scripts/start.sh` if needed). Open `http://192.168.1.12:15000/demo#dark` on
   the Mac and select **Tester le jeu**.
   Copy the **Session de test** ID shown in the Dark action panel.
3. On the InterArcade host, run the following. The command uses the existing
   admin route; it does not put an admin token in the browser. Enter the
   session ID when prompted.

   ```bash
   cd /opt/interarcade
   set -a
   . ./.env.integration
   set +a
   read -r -p 'Session Dark : ' DARK_SESSION_ID
   curl -fsS -X POST "http://${INTERARCADE_BIND_HOST}:15000/api/v1/listeners/start" \
     -H "Authorization: Bearer ${INTERARCADE_ADMIN_TOKEN}" \
     -H 'Content-Type: application/json' \
     --data "{\"tenant_id\":\"${INTERARCADE_DEMO_TENANT_ID:-demo-creator}\",\"username\":\"@songmicon\",\"session_id\":\"${DARK_SESSION_ID}\"}"
   ```

4. Watch the logs on the InterArcade host:

   ```bash
   docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml logs -f api worker
   ```

   When `INTERARCADE_TIKTOK_DARK_TRACE=true`, the trace uses
   `tiktok_event_received`, `tiktok_dark_mapping` (including a reason when
   ignored), and `dark_action_delivered`. It logs event and source IDs, action
   names and available gift metadata, but no signing or admin token. Trigger
   a follow from a viewer who does not already follow, then enough likes to
   cross the configured threshold. Test gifts only if appropriate for the
   account; the logs show their observed diamond values and tier. Use the
   launcher simulation for costly gift tiers until a real gift test is agreed.
5. Return to the library in the launcher. This ends the Dark session and
   stops its source. Run `./scripts/status.sh` and
   `python3 scripts/diagnostic.py` to confirm health. If ending the browser
   session is not possible, stop the source with the existing admin
   `/api/v1/listeners/stop` route, then close the session.

The worker is deliberately **not** connected to `@songmicon` by this change
alone. A real test depends on the account being live, the community signing
service being available and within its free limits, SDK/protocol availability,
and gift metadata availability. A key is optional and raises the signing limit.

## Connection diagnostics

TikTokLive 6.6.1's HTML room parser can fail when TikTok omits `SIGI_STATE`.
Its API fallback can then return the creator's last `roomId` even when the
user-room API reports status `4` (offline). A separate `room/check_alive`
check can reject a newly detected room before a WebSocket is attempted.

The worker now keeps one SDK client per source, discovers the room and status
together from the user-room API, removes the previous room ID from the next
discovery request, and passes the detected room ID to `connect()` with the
separate room check disabled. It keeps the WebSocket until the SDK connection
ends or the listener is stopped. API status `4` is logged as an API report,
not proof that the phone is offline. A new room gets an immediate, limited
WebSocket probe; an unchanged offline room is probed at most every five
minutes. Normal retries back off to 30 seconds.
Rate-limit errors wait 60 seconds before another attempt.

Worker lifecycle messages are `tiktok_room_detected` (with old/new room IDs),
`tiktok_api_reports_offline`, `tiktok_offline_room_probe`,
`tiktok_connection_attempt`, `tiktok_websocket_connected`,
`tiktok_websocket_lost`, `tiktok_connection_failed` (exception class only),
and `tiktok_reconnect_scheduled`. An Euler HTTP 200 alone does not prove that
the WebSocket connected; `tiktok_websocket_connected` does. Raw SDK HTTP URLs
are suppressed from worker INFO logs. No signing key or token is logged.
