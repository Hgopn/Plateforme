"use strict";

// Dark understands InterArcade action keys only. One slot per effect keeps
// repeated actions bounded; the latest light action replaces its opposite.
function createDarkActionState(clock = () => performance.now()) {
  const slots = new Map();
  const seen = new Set();
  const valid = new Set(["LIGHT_BOOST", "LIGHT_REDUCE", "REVEAL_MAP", "PLAYER_HELP", "PLAYER_HINDER"]);

  function apply(action) {
    if (!action || action.schema_version !== 1 || action.game_id !== "dark"
        || !valid.has(action.action_type) || typeof action.event_id !== "string"
        || !action.event_id || typeof action.source_platform !== "string"
        || typeof action.source_account_id !== "string" || typeof action.actor_id !== "string"
        || !Number.isFinite(action.duration_ms) || action.duration_ms <= 0
        || action.duration_ms > 30000 || seen.has(action.event_id)) return false;
    seen.add(action.event_id);
    if (seen.size > 256) seen.delete(seen.values().next().value);
    const slot = action.action_type.startsWith("LIGHT_") ? "light" : action.action_type;
    slots.set(slot, { action, expiresAt: clock() + action.duration_ms });
    return true;
  }

  function snapshot() {
    const now = clock();
    for (const [slot, effect] of slots) {
      if (effect.expiresAt <= now) slots.delete(slot);
    }
    const light = slots.get("light")?.action.action_type;
    return {
      lightScale: light === "LIGHT_BOOST" ? 1.6 : light === "LIGHT_REDUCE" ? 0.7 : 1,
      reveal: slots.has("REVEAL_MAP"),
      help: slots.has("PLAYER_HELP"),
      hinder: slots.has("PLAYER_HINDER"),
      active: [...slots.values()].map((effect) => effect.action),
    };
  }

  function clear() { slots.clear(); }
  return { apply, snapshot, clear };
}

globalThis.createDarkActionState = createDarkActionState;
if (typeof module !== "undefined") module.exports = { createDarkActionState };
