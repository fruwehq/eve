# v4.4 §14 — move the real `oses/` provisioning out of core (task spec)

Roadmap item: `docs/v4.4-roadmap.md` §14. This is a **deep item on the order of
§8** — a provisioning-subsystem move + schema decoupling + a new plugin kind +
cross-repo coupling. Independent of §8; sequence separately.

**Run end-to-end autonomously**, same rules as the §8 spec: phases are commit/
bisect boundaries, not approval gates; self-verify each against the health gate;
work on branch **`v4.4`** only; run pytest with `.venv/bin` on `PATH`. A human
reviews the finished result.

## The leak (verified)

- `scripts/provision` finds the OS provision tree by walking
  `root / "oses" / <os_id> / "provision"` (lines ~110, ~355) — core reads its own
  `oses/` dir by OS id.
- Real OS families live in core: `oses/ubuntu-26.04{,-amd64,-arm64}/` and
  `oses/windows-server-2025/`, each a `provision/` subtree. Mock OSes
  (`mockos-*`, `mockwin-*`) are test fixtures.
- OS-id literals hardcoded in core schemas: `provision-manifest.schema.json`
  (`enum [ubuntu, windows]`), `plugin-manifest.schema.json` (`ubuntu`/`windows`
  install specs + an `enum`), `provision-status.schema.json` (`enum`), and the
  `windows` section of `config.schema.json`.
- Core consumers: `scripts/provision`, `scripts/test-provision-runner`,
  `scripts/test-instances`.

## Design (settled)

The provider-specific OS bring-up (image/AMI selection) is **already** provider-
owned — e.g. aws's manifest carries `oses: { aws_ami_name_pattern: ... }`, and
`catalog.oses` is already merged from provider manifests. What remains in core is
the **generic provision tree** (apt/systemd/step scripts), which is the same
across providers and so must **not** be duplicated into each provider.

Therefore: a **new `os` plugin kind**. An OS plugin owns one OS family's generic
`provision/` tree; core discovers it from the installed plugin set, exactly like
providers/packages. Provider manifests keep only their image/boot specifics.

**Home: the `eve-providers` repo, under a shared `oses/` directory** (no new
repo). The real OS families move to `eve-providers/oses/<id>/` as `os` plugins —
a shared, non-per-provider location alongside the repo's existing `_common`/
`_catalog-base` shared dirs, so the generic provision tree is **not** duplicated
into each provider. Mock OSes stay in eve core as test fixtures (discovered via
`EVE_PLUGIN_ROOTS_EXCLUSIVE`, like the `mock-cloud` provider).

## Health gate (every phase)

```
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/python -q
.venv/bin/python -m ruff check eve_sdk tui scripts
.venv/bin/python -m mypy eve_sdk
scripts/test-core-boundary
```

---

## Phase 1 — schema: add the `os` plugin kind + open OS-id enums  *(eve core)*

1. Add `os` to the `kind` enum in `plugin-manifest.schema.json`; add an
   `if kind==os then …` branch declaring how an OS plugin points at its
   provision tree (e.g. `provision: { dir: provision }` relative to the plugin)
   and its `supports` (arch/family). Mirror the provider/package branches.
2. Open the OS-id enums to freeform (drop `enum [ubuntu, windows]`; use
   `additionalProperties`/string) in `provision-manifest.schema.json`,
   `plugin-manifest.schema.json` (install specs + enum), and
   `provision-status.schema.json`. Reclassify the `windows` section of
   `config.schema.json` (move to the OS plugin, or keep only if genuinely a core
   knob — justify in the commit).

Commit: `feat(schema): add os plugin kind; open OS-family id enums (§14)`.

## Phase 2 — discover OS provision trees from plugins  *(eve core, additive)*

Make `scripts/provision` (and `scripts/test-provision-runner`,
`scripts/test-instances`) resolve an OS family's provision tree from the
**installed `os`-plugin set** (`PluginManifest.load_all("os")`) keyed by OS id,
instead of `root/oses/<id>/provision`. Keep the in-repo `oses/<id>` lookup as a
**fallback** so the tree stays green until Phase 3 moves the real OSes. Add a
test that an `os`-plugin-provided provision tree is discovered and used.

Commit: `feat(provision): discover OS provision trees from os plugins (§14)`.

## Phase 3 — move the real OS families to `eve-providers/oses/`  *(release-coupled)*

For each real OS family (`ubuntu-26.04*`, `windows-server-2025`): create an `os`
plugin at `eve-providers/oses/<id>/` with an `eve-plugin.yaml` (`kind: os`, the
family id, arch `supports`) and its `provision/` tree moved verbatim from core.
Port any provision tests. The provider image catalog entries stay in the provider
manifests (already there). Commit per OS family.

## Phase 4 — delete the real `oses/` from core  *(eve core; after Phase 3)*

Once every real OS family is an `eve-oses` plugin and parity-green:
1. Delete `oses/ubuntu-26.04*` and `oses/windows-server-2025` from core. Keep
   only `oses/mockos-*` and `oses/mockwin-*` as test fixtures.
2. Remove the in-repo `oses/<id>` fallback added in Phase 2 — discovery is now
   purely plugin-driven.
3. Remove any remaining `ubuntu`/`windows` literals from core code/comments.

Commit: `refactor(core): drop real OS families; discovery is plugin-only (§14)`.

## Phase 5 — cross-repo parity

```
EVE_PLUGIN_ROOTS_EXCLUSIVE=1 EVE_PLUGIN_ROOTS="<eve-providers>:<pkgs>" \
  PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/python -q
```

Confirm provisioning still resolves + runs steps for a real OS family sourced
from `eve-providers/oses/`, and the mock OSes still work as in-repo fixtures. No
fallback paths — a missing OS plugin must fail loudly.

## Phase 6 — extend the §11 lint to ban OS-family ids  *(eve core; LAST)*

Add OS-family ids (`load_all("os")`) to `scripts/test-core-boundary`'s banned set
(reuse `COMMON_TOKEN_IDS` for dual-meaning words). Run it green; fix any
straggler. Update `docs/v4.4-roadmap.md` §14 + §11 to **done**.

Commit: `chore(lint): ban OS-family ids in core; v4.4 §14 done`.

## Merge discipline

eve `v4.4` + `eve-providers` (the `oses/` addition, alongside #7) + the coupled
packages PRs merge as one set. Core-first (Phase 4 before `eve-providers/oses/`
exists) breaks provisioning. Run Phase 5 parity green before any merge.
