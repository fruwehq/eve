# WS5 — Docker provider (roadmap §3)

## Contract changes
1. **Schema**: add `"docker"` to `provider_supports.engines` enum (peer of terraform/qemu/vagrant/metal).
2. **New provider** in `eve-providers/docker/`: engine `docker`, kind `vm`.
   - A container as a limited **manageable** instance (docker exec, not SSH).
   - Lifecycle commands backed by the `docker` CLI.
   - `host_tools: [docker]` so doctor checks Docker availability.
   - Catalog contribution: a docker-ubuntu machine + OS overlay (docker_image field).
   - Access rules: `root` user (containers default to root; `docker exec` as root).
3. **Core**: no changes needed — `engine_for` already reads `supports.engines[0]` from the
   manifest. Doctor's `ENGINE_TOOLS` already includes docker. The `docker` engine name
   carries through resolve/dispatch/profile_resolve generically.

## Approach
- `commands/docker`: a single Python script dispatching lifecycle commands (init=noop,
  up=docker run, down=docker rm, start/stop/status/ip=docker inspect, ssh=docker exec).
  Honors `EVE_PLUGIN_DRY_RUN` (prints JSON intent instead of running).
- `commands/connectivity`: probes `docker --version`.
- Catalog: one machine (`docker-ubuntu-medium`), OS overlay with `docker_image: ubuntu:26.04`.

## Gate
- `eve plugin test docker` passes.
- `poetry run make test` green.
- **FLAGGED golden change**: `tests/golden/catalog-options.json` regenerated — the `providers` list now includes `"docker"` (one line added). Instance goldens (`tests/golden/instances/*.env`) are byte-identical (no fixture uses docker).
