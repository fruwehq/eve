# WS3 — Locations as a provider function (roadmap §7)

## Contract changes
1. **Provider `locations` command**: declared in each provider manifest (peer of
   `status`/`ip`). Returns a JSON list of location entries, each carrying the
   per-location data `emit_env` needs (region/zone/host/ssh_port/…). Each provider
   ships a **static fallback** so eve works offline.
2. **`config/catalog.yaml`**: `locations:` section removed (holds only `version: 1`).
3. **Catalog-options**: the `platforms` array no longer enumerates a fixed location
   set. Instead, platforms show provider×machine×os×init without a location axis
   (location is chosen at instance-create time from the provider's list).

## Approach
- Each provider (aws, gcp, local-qemu, raspberry-pi, truenas, vultr) gets a
  `commands/locations` script that prints JSON: a list of `{name, label, data}`
  entries where `data` carries provider-specific fields (region, host, etc.).
- The static fallback is the same list (hardcoded in the script for offline use).
- `catalog-options` drops the location axis from platforms.
- `instance-create` already takes `--location` — the location name must exist
  in the provider's locations list (validated at create time, same as today).
- The location data is threaded through resolve/emit_env via the resolved dict's
  `location` key, sourced from the provider's locations output instead of the
  catalog `locations` section.

## Golden changes (FLAGGED)
- `tests/golden/catalog-options.json`: **regenerated** — platforms drop the
  `location` field (no longer enumerated). This is intentional.
- `tests/golden/instances/*.env`: **must stay byte-identical** — the resolved
  instance env sources the same location data, just from the provider's locations
  command instead of the catalog `locations` section.

## Gate
- `poetry run make test` green.
- Instance `.env` goldens byte-identical.
- `eve plugin test` for changed providers.
- `core-boundary` clean.
