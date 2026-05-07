# AI Agent Sandboxes

Docker Sandboxes can be useful for unattended AI engineering runs because each
agent runs in an isolated microVM with its own filesystem, network, and Docker
daemon. Treat it as a host-side safety tool for running agents against this
repository, not as part of the VM provider/package lifecycle.

The feature is still experimental, so this repository only provides a thin
opt-in helper:

```bash
make ai.sandbox AGENT=codex
make ai.sandbox AGENT=opencode
make ai.sandbox AGENT=claude
make ai.sandbox AGENT=shell
```

Use this when you want an agent to work for a while without touching the host
outside the mounted project workspace. Do not make core v3 flows depend on it.
The normal scripts and tests must continue to work directly on macOS and Linux.

Install and sign in with Docker's `sbx` CLI first. Current Docker docs describe
macOS, Windows, and Ubuntu installation paths, but platform requirements and CLI
behavior may change while Sandboxes remains experimental.

Recommended scope for this repo:

- Good fit: long-running AI implementation, broad dependency installation,
  trying untrusted package-manager changes, and parallel agent experiments.
- Poor fit: provisioning real cloud/local VMs, accessing host credentials, or
  replacing the instance/plugin state machine.
- Security stance: pass only the credentials the selected agent needs, prefer
  project-local config, and avoid mounting extra host paths unless required.
