# WS2 — Host-tool deps + toolchain-aware `eve doctor`

## Contract changes
1. Doctor derives the required host toolchain from the pulled providers' engines:
   - `terraform` engine → `terraform` + `terramate`
   - `qemu` engine → `qemu-system-aarch64` + `qemu-system-x86_64`
   - `vagrant` engine → `vagrant`
   - `metal` engine → (none)
   - `docker` engine → `docker`
2. Provider-specific tools (aws CLI, gcloud, curl, nc) come from each provider's
   `host_tools` declaration (already in the manifest schema from Chunk C).
3. The static "provider" tool list in doctor is removed — replaced by engine-derived
   + host_tools-derived checks. Core tools (bash, jq, python3, etc.) stay static.

## Approach
- Add `ENGINE_TOOLS` mapping in doctor.
- For each loaded provider, add its engine's tools + its host_tools.
- Deduplicate by tool name.
- Add host_tools to gcp (gcloud), truenas (curl, nc), vultr (curl).

## Gate
- No golden changes.
- `poetry run make test` green.
- Provider manifests pass `eve plugin test`.
