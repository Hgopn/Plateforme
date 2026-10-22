# Dark live actions

Dark receives only the versioned InterArcade `ia:action` message. A live
connector or a future rule mapper submits a normalized `event_type: "action"`
event with `payload.action_type`; the API validates the active Dark run,
records the event once and publishes the action to that session's Socket.IO
room. No gift, Bits, or provider-specific rule is present in Dark.

| Action | Effect | Duration |
| --- | --- | ---: |
| `LIGHT_BOOST` | Light radius ×1.6 | 8 seconds |
| `LIGHT_REDUCE` | Light radius ×0.7 | 8 seconds |
| `REVEAL_MAP` | Remove the darkness overlay for the visible viewport | 5 seconds |
| `PLAYER_HELP` | Show the direction of the current level's exit | 7 seconds |
| `PLAYER_HINDER` | Show confirmed steps at 70% of normal walking speed | 7 seconds |

The server owns durations in `interarcade/games/dark_actions.py`. The browser
uses a monotonic clock and holds at most one effect in each of four slots:
light, reveal, help and hinder. A new light action replaces its opposite;
a repeated action refreshes its slot instead of stacking. Duplicate event IDs
are ignored. Every effect expires independently, and reset clears them all.
Movement validity, collision, map progression and session identity remain
server-owned. Dark behaves exactly as before when no action arrives.

The `ia:action` envelope contains `schema_version`, `game_id`, `action_type`,
`duration_ms`, `event_id`, `source_event_id`, `timestamp`, `tenant_id`,
`session_id`, `source_platform`, `source_account_id`, `source_username`,
`actor_id`, `actor_platform_id` and `actor_username`. The light notice uses
the viewer's display name and platform label; `actor_id`, never the display
name, distinguishes viewers across platforms.

## Local test on Mac

With the local integration stack active in Demo mode, open
`http://192.168.1.12:15000/demo#dark` on the same private network. Select
**Tester le jeu**. In the **Action live** panel, choose one of the five
actions, a simulated platform and a spectator name, then select
**Déclencher l’action**. The launcher sends the signed game session token.
Choosing TikTok or Twitch here only labels a
simulated source; it never starts a platform connection. To test distinct
identities, send actions from both simulated platforms with the same name.

The action notice can be hidden with `live_notices=0` on the Dark iframe URL;
the effects still run. Its default visibility and display time are configured
by `DARK_ACTION_UI` in `games/dark/dark.js`. The underlying light radius and
movement speed remain configured by `DARK_VISUALS` there.

The server-side TikTok mapping is documented in
[TIKTOK_DARK_LIVE_TEST.md](TIKTOK_DARK_LIVE_TEST.md). A Twitch connector and
the final Broadcast mode remain future work.
