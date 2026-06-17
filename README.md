# eve — agnostic plugin host for VM instance management

eve stands up, provisions, and manages virtual machine instances across
cloud and local providers. It is a **thin orchestrator** over existing tools
(Terraform, QEMU, Vagrant, Docker) — not a configuration-management system.

The core ships **zero providers, zero packages, zero catalog data**.
Everything comes from external plugin repos that you pull with `eve pull`.
This keeps eve provider-agnostic: anyone can extend it from their own repos.

## Install

**macOS:**

```bash
brew install jq poetry python@3.14 shellcheck yq
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
# Terramate:
TERRAMATE_VERSION=0.17.0
curl -fsSLo /tmp/tm.tar.gz "https://github.com/terramate-io/terramate/releases/download/v${TERRAMATE_VERSION}/terramate_${TERRAMATE_VERSION}_darwin_$(uname -m | sed 's/x86_64/x86_64/;s/arm64/arm64/').tar.gz"
sudo tar -C /usr/local/bin -xzf /tmp/tm.tar.gz terramate

git clone https://github.com/fruwehq/eve.git && cd eve
poetry install
```

**Ubuntu:**

```bash
sudo apt-get install -y jq make python3.14 python3.14-venv ripgrep shellcheck yq
curl -sSL https://install.python-poetry.org | python3.14 -
# Terraform + Terramate: see their install docs
git clone https://github.com/fruwehq/eve.git && cd eve
poetry install
```

**pipx (when published):**

```bash
pipx install "git+https://github.com/fruwehq/eve"
```

## Quickstart

```bash
# Pull provider + package plugins (defined in config/plugin-sources.yaml)
eve pull

# Check which tools eve needs based on your pulled providers
eve doctor

# List available provider/platform choices
eve catalog list --json

# Create a concrete instance
eve instance create my-dev \
  --machine local-qemu-medium \
  --os ubuntu-26.04-arm64 \
  --location tokyo \
  --bundles dev-ai

# Lifecycle
eve instance up my-dev
eve instance provision my-dev
eve instance ssh my-dev
eve instance down my-dev

# Or use the TUI
eve tui
```

## Architecture

```
eve (this repo)              eve-providers              eve-packages-linux
  agnostic core               aws, gcp, vultr,           vnc, rustdesk, docker,
  eve CLI                     truenas, local-qemu,       steam, sunshine, ...
  TUI                         raspberry-pi, docker       dev tools, desktops
  plugin host SDK
  contract schemas            eve-packages-windows
  conformance harness         rdp, rustdesk (win half),
  warm Engine                 sunshine (win half), ...
```

**Dependency direction is one-way:** plugins depend on eve, never the reverse.
Each plugin repo runs `eve plugin test` in its own CI to prove conformance
against eve's published contract.

### Plugin model

- **Provider plugins** declare machines, OS image overlays, inits, locations,
  and lifecycle commands (Terraform, QEMU, Docker). They own the
  bring-up → manageable boundary.
- **Package plugins** declare bundles, install steps, remote-desktop actions,
  and per-OS provision trees. They run over an SSH (or docker exec) session
  to a manageable instance.
- The **catalog** is reconstructed at runtime by aggregating all pulled plugin
  contributions — no central catalog file.

### Warm Engine

The in-process Engine (`eve_sdk.engine`) memoizes catalog + plugin parsing
once per session. The TUI, `eve batch`, and scripted callers share one warm
parse — a 12× speedup on catalog reads vs. the cold subprocess path.

```bash
# Run N ops against one warm Engine
echo 'catalog list --json
plugin list --kind provider
instance view my-dev' | eve batch
```

## CLI reference

```
eve instance   create|list|up|down|start|stop|ssh|ip|provision|status|view|delete|...
eve package    list|select|install|status|down|action|verify
eve provider   list|status|action
eve bundle     list|select|unselect
eve plugin     list|validate|sync|test
eve catalog    list
eve config     get|set|list
eve doctor     [--json]
eve pull       [--frozen|--if-stale TTL]
eve batch      # stream ops from stdin against one warm Engine
eve tui
```

Run `eve <group> --help` for verb listings.

## Configuration

- **Non-secret config:** `.eve/config.yaml` (structured, validated, TUI-editable)
- **Secrets:** `.eve/secrets/<provider>.yaml` (mode 0600, gitignored)
- **Plugin sources:** `config/plugin-sources.yaml` (pinned git repos)
- **Instance registry:** `.eve/instances.yaml` (local, gitignored)

Press `S` in the TUI to open Settings; on first run, a `FirstRunScreen` lists
missing required fields.

## For plugin authors

```bash
# Scaffold from the template
git clone https://github.com/fruwehq/eve-plugin-template

# Validate against the contract
eve plugin test ./my-plugin

# Publish: push to a git repo, add it to config/plugin-sources.yaml, eve pull
```

The contract (`core/schema/plugin-manifest.schema.json`) defines manifest
shape, required commands, access rules, config schemas, and the manageable
boundary. See [`docs/v4.0-roadmap.md`](docs/v4.0-roadmap.md) and
[`docs/v4.1-roadmap.md`](docs/v4.1-roadmap.md) for the full design.

## Development

```bash
poetry install
make test           # full suite (hermetic — no sibling repos needed)
make test.python    # ruff + mypy + pytest only
make test.lint      # yaml/terraform/terramate lint
```

The test suite is fully self-contained: synthetic fixture plugins under
`tests/fixtures/hermetic/` exercise every code path (catalog merge, dispatch,
emit_env, dual-OS package merge) without cloning external repos.

## License

MIT — see [LICENSE](LICENSE).
