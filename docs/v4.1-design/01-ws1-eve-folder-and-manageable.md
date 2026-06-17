# WS1 — .eve/ folder convention + "manageable" terminology

## Contract changes
1. **Terminology**: v4.0's "SSH-readiness boundary" → "**manageable** boundary". A target is
   "manageable" when eve can reach it to execute commands — SSH for cloud/VM providers,
   `docker exec` for the docker provider, direct for local-qemu. This is a reword, not a
   behavior change.

2. **`.eve/` folder convention**: Discovery uses the selected directory or its `.eve/` subdir,
   identified by a marker file (`.eve/eve-project` or `.eve/config.yaml`). NOT a `.git`-walk-up.
   Consumer projects tuck content in `.eve/`; plugin repos keep visible subdirs.

## Approach
- Reword "SSH-ready" / "SSH-readiness" → "manageable" across docs, help text, error messages.
- Document the `.eve/` folder convention in the v4.1 roadmap.
- No discovery code change needed yet — the marker convention is documentation-only for now
  (Workdir already uses `.eve/` as the data dir).

## Gate
- No golden changes (terminology reword only).
- `poetry run make test` green.
