# InterArcade V2 stable baseline

This baseline was prepared on 2026-10-12 before Dark V2 work. It contains no new
game feature and no public deployment.

## Active runtime

- `app.py` creates the Flask/Socket.IO API.
- `python -m interarcade.worker` runs the TikTok supervisor separately.
- PostgreSQL owns tenants, users, licenses, sessions, listeners, accepted
  events, runtime errors, heartbeats, and Marble rounds.
- Signed session tokens join Socket.IO rooms scoped to one persisted active
  session.
- The local demo uses a dedicated `demo-creator` identity and does not read a
  repository license file.

## Removed compatibility material

- the tracked Windows virtual environment;
- repository license keys and the legacy JSON migration path;
- old listener entry point and listener route aliases;
- unused process-local models, templates, manifests, duplicate cards, and root
  images;
- obsolete Electron/OVH hooks and references to missing Slot sound assets.

## Verification

Run the following against the isolated local stack:

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/test.sh
./scripts/autocheck.sh
./scripts/test_e2e.sh
./scripts/test_resilience.sh
python3 scripts/diagnostic.py
./scripts/stop.sh
```

The real TikTok transport still requires an explicitly supplied test account
and approved credentials. Automated tests use only the authenticated simulated
event ingress.
