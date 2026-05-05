# Agent Orchestration Plan

> Status: **Active** — implementation starting on v3 branch.
> Note: Catalog profile structure is being refactored (separating VM location from
> packages more cleanly). Profile definitions below are illustrative and will be
> updated to match the final catalog schema.

## Overview

A Discord-based multi-agent orchestration layer that lets you dispatch coding tasks
to Hermes, Codex, Goose, OpenCode, and Claude from a single Discord server. Hermes
is the primary orchestrator (Discord gateway, subagents, memory, skills, scheduling)
but the design stays swappable — an abstract agent registry means Hermes can be
replaced later without rearchitecting.

## Principles

1. **Hermes-first** — use its Discord gateway, subagents, memory, skills, scheduling.
2. **Swappable** — abstract agent registry so Hermes can be replaced later.
3. **All infra through this repo** — provision always-on headless VMs for Hermes +
   Discord. Raspberry Pi is the primary platform; TrueNAS VM and cloud VMs are
   secondary.
4. **Separate config repo (`agent-hub`)** — agent configs, skills, recipes, Discord
   server layout. Installed as a package during provisioning.
5. **Backups built in** — snapshot-based (ZFS on TrueNAS, rsync on Pi), never lose
   data.
6. **Voice deferred** — text/memo-based interaction first; continuous real-time voice
   is Phase 9.

## Deployment Targets

| Target | Role | Priority | Notes |
|--------|------|----------|-------|
| Raspberry Pi 5 | Primary orchestrator | High | Always-on, arm64, low power. Main AI engineering platform. |
| TrueNAS VM | Secondary orchestrator | Medium | Always-on VM on NAS. amd64. ZFS snapshots for backup. |
| Vultr / AWS | Tertiary / fallback | Low | Cloud VM when local hardware unavailable. |

## Repository Structure

### This repo (`ephemeral-cloud-gaming`) — Infrastructure

- Machine / OS / bundle / profile definitions in `config/catalog.yaml`.
- Provisioning steps in `linux/provision/scripts/steps/`.
- Backup tooling per provider.
- New `.env` variables for Discord / Hermes.

### Config repo (`agent-hub`) — Agent Configuration

```
agent-hub/
├── install.sh                    # Called by provisioning step
├── discord/
│   ├── setup-server.sh           # Creates Discord server + channels via API
│   └── server-template.yaml      # Channel/role layout definition
├── hermes/
│   ├── config.yaml               # Hermes gateway config
│   ├── skills/                   # Custom skills for agent dispatch
│   │   ├── dispatch-codex.yaml
│   │   ├── dispatch-goose.yaml
│   │   ├── dispatch-opencode.yaml
│   │   └── dispatch-claude.yaml
│   ├── recipes/                  # Structured subagent workflows
│   │   ├── code-review.yaml
│   │   ├── security-audit.yaml
│   │   └── parallel-research.yaml
│   └── personalities/            # Agent personality profiles
│       ├── orchestrator.md
│       └── reviewer.md
├── backup/
│   ├── hermes-backup.sh
│   └── hermes-restore.sh
├── agents/
│   ├── registry.yaml             # Abstract agent registry (swappable)
│   ├── codex.yaml
│   ├── goose.yaml
│   ├── opencode.yaml
│   ├── claude.yaml
│   └── hermes.yaml
├── knowledge-base/               # Phase 8: Obsidian-style structured markdown
│   ├── agents/                   # Per-agent notes, capabilities, quirks
│   ├── architecture/
│   │   ├── decisions/            # ADR-style decision records
│   │   └── diagrams/            # Mermaid diagrams
│   ├── runbooks/                 # Operational runbooks
│   ├── sessions/                 # Important session summaries
│   └── learnings/                # Agent-generated knowledge
└── voice/                        # Phase 9: voice pipeline
    └── README.md                 # Placeholder
```

## Agent Registry

The key abstraction in `agents/registry.yaml` — orchestrator-agnostic:

```yaml
agents:
  - name: hermes
    type: hermes-native
    capabilities: [memory, skills, scheduling, subagents, discord-gateway]
    config: hermes.yaml

  - name: codex
    type: cli-subagent
    command: codex
    capabilities: [code-editing, shell, git]
    acp_adapter: codex-acp
    config: codex.yaml

  - name: goose
    type: cli-subagent
    command: goose
    capabilities: [code-editing, shell, mcp-extensions, subagents]
    config: goose.yaml

  - name: opencode
    type: cli-subagent
    command: opencode
    capabilities: [code-editing, shell, git]
    config: opencode.yaml

  - name: claude
    type: api
    provider: anthropic
    capabilities: [reasoning, code-editing, analysis]
    config: claude.yaml
```

## Discord Server Layout

Created by `discord/setup-server.sh`:

```
Agent Hub
├── 📋 control
│   ├── #overview              — pinned: server rules, command reference
│   ├── #tasks                 — create/assign tasks via slash commands
│   └── #status                — agent heartbeats, error alerts
├── 🤖 agents
│   ├── #hermes                — Hermes primary channel
│   ├── #codex                 — dispatch to codex
│   ├── #goose                 — dispatch to goose
│   ├── #opencode              — dispatch to opencode
│   └── #claude                — dispatch to claude API
├── 🔊 voice
│   ├── 🔊 General             — shared voice (async voice memos)
│   ├── 🔊 Hermes              — Hermes voice (Phase 9: continuous voice)
│   └── 🔊 Pair Programming   — collaborative voice channel
├── 📁 logs
│   ├── #hermes-logs
│   └── #system-logs
└── 🧪 dev
    ├── #testing
    └── #playground
```

## New Catalog Entries (Illustrative)

> Note: Profile structure is being refactored. These will be updated to match the
> final catalog schema once the location/package separation is complete.

### New packages

- `agent-orchestrator` — installs agent-hub config repo + Hermes gateway setup
- `backup-utils` — snapshot/backup tooling

### New bundles

- `orchestration-core` — ssh, docker, dev-toolchain, hermes, goose, claude, codex-cli,
  opencode, agent-orchestrator, backup-utils
- `orchestration-minimal` — ssh, docker, hermes, agent-orchestrator, backup-utils

### New profiles (illustrative)

- `rpi-hermes-orchestrator` — Raspberry Pi 5, persistent, orchestration-core
- `truenas-hermes-orchestrator` — TrueNAS VM, persistent, orchestration-core
- `vultr-hermes-orchestrator` — Vultr cheap VM, persistent, orchestration-minimal

## New .env Variables

```bash
# Discord bot token for Hermes gateway.
# HERMES_DISCORD_TOKEN=

# Discord guild (server) ID.
# HERMES_DISCORD_GUILD_ID=

# Discord allowed user IDs (comma-separated).
# HERMES_DISCORD_ALLOWED_USERS=

# Backup retention days for orchestrator VMs.
# ORCHESTRATOR_BACKUP_RETENTION_DAYS=30
```

## Backup Strategy

| Provider | Method | Frequency | Retention |
|----------|--------|-----------|-----------|
| TrueNAS | ZFS zvol snapshot | Every 6 hours | 30 days |
| Raspberry Pi | rsync to TrueNAS / cloud | Daily | 30 days |
| Vultr | `vultr-cli snapshot create` | Daily | 14 days |
| AWS | EBS snapshot | Daily | 14 days |

Hermes data directory (SQLite, memories, skills) is backed up separately by
`backup/hermes-backup.sh` in the agent-hub repo.

## Implementation Phases

| Phase | Scope | Where | Status |
|-------|-------|-------|--------|
| P0 | Commit this plan document | Gaming repo | In progress |
| P1 | Create agent-hub config repo skeleton | New repo | Pending |
| P1.5 | Discord server layout + setup script | Config repo | Pending |
| P2 | Fix Hermes install step (production, arm64) | Gaming repo | Pending |
| P3 | Agent registry + Hermes gateway config | Config repo | Pending |
| P4 | New catalog entries + provisioning steps | Gaming repo | Pending |
| P5 | Agent dispatch skills/recipes for Hermes | Config repo | Pending |
| P6 | Backup automation | Both repos | Pending |
| P7 | Test end-to-end on Raspberry Pi | Both repos | Pending |
| P8 | Knowledge base (Obsidian-style markdown in git) | Config repo | Pending |
| P9 | Voice pipeline (continuous real-time) | Config repo | Deferred |

## Key Decisions (ADRs)

### 001: Hermes as primary orchestrator

- Hermes has Discord gateway, subagents, memory, skills, scheduling built-in.
- 134k GitHub stars, active development, MIT license.
- Can be swapped later thanks to the abstract agent registry.

### 002: Discord over Slack

- Slack requires paid plans per user for API integrations and message history.
- Discord is free, has unlimited message history, native voice channels, bots.
- Discord's voice API supports real-time audio (needed for Phase 9).

### 003: Raspberry Pi as primary platform

- Always-on, low power, arm64, already in the catalog as `kind: metal`.
- Designated as the main AI engineering platform.
- TrueNAS VM and cloud VMs serve as secondary/fallback targets.

### 004: Separate config repo (agent-hub)

- Keeps gaming repo focused on infrastructure (machines, OS, provisioning).
- Agent configs evolve independently from VM lifecycle.
- Installed as a package by the gaming repo's provisioning steps.
