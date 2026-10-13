# Dark V2 pilot

Dark is a first-class InterArcade game module. Its first campaign contains
three cave labyrinths measuring 10×10, 15×15, and 20×20 cells.

## Runtime contract

- PostgreSQL owns the current level, player cell, movement count, status, and
  completion state for each Dark session.
- The browser renders the server state, interpolates movement, and keeps the
  camera centered on the player. Confirmed grid steps are shown as continuous
  motion through adjacent cells, with four facing sprites and a walk cycle.
- Visual speed and the default light radius are configured by `DARK_VISUALS`
  near the top of `games/dark/dark.js`. The radius is measured in tile widths;
  its small flicker is applied separately.
- Movement requests are authenticated with the signed InterArcade session
  token. The API validates every collision and level transition.
- The launcher closes the InterArcade session when the creator returns to the
  library. An active Dark run is then marked `ended`.
- Test mode uses the normal session API and the isolated normalized event
  ingress. It does not start a TikTok listener.
- The local launcher can open the Dark card directly at `/#dark`. The creator
  then selects **Tester le jeu** to start a Test session.
- The Dark Live action stays disabled until credentials and a dedicated test
  account are available for a real transport validation.

## Live compatibility

Dark receives the versioned `ia:event` envelope and exposes it to the client
as the browser event `interarcade:event`. The first three levels do not change
gameplay in response to audience events. Future mappings can consume that
provider-neutral contract without importing TikTok behavior into Dark.

## Out of scope

Enemies, traps, keys, batteries, chests, timers, additional worlds, Twitch,
payments, public deployment, and the final desktop shell are outside this
pilot.
