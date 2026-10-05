# Typed guest access and provider identity

`command-io.schema.json` and `observed-state.schema.json` validate the same closed
SSH guest-access object. Required fields are `address` (IPv4), `port` (1–65535),
`protocol` (`ssh`), `version` (`2`), `username` (SSH account name, including Linux
and Windows account names), `credential_reference` (absolute file path and type
`ssh-private-key-file`), `host_identity`, and `provider_identity`. Credential
references are selectors, never private-key contents.

Host identity contains only a SHA-256 OpenSSH fingerprint and a mechanism:
`configured-fingerprint` means an explicit controller pin; `incus-authenticated-exec`
means the guest public host key was retrieved through the authenticated Incus
API. Neither permits trust-on-first-use or bypassing SSH host verification.

Provider identity is a closed, provider-discriminated envelope, not an arbitrary
configuration object. The current variant is `{provider: incus, identity: {...}}`.
Only the Incus-specific `identity` requires HTTPS endpoint, remote, project,
instance name, and a 64-hex ownership digest. Future providers add their own
closed schema variants under the discriminator; they do not inherit these Incus
concepts. Every variant and nested object rejects undeclared fields. The access
object itself contains no OS or provider lifecycle assumptions.

Normal Incus running status includes authenticated guest access. Core validates
the exact JSON status object it consumes, normalizes failed observations through
its existing error presentation, and preserves the raw observation for diagnosis.
Every refresh replaces the access binding; non-running states, invalid output,
or refresh errors remove cached binding/address. Confirmed observed failures
disable running-only actions even if an earlier provisioned state was running.
These are observation/presentation changes, not new Determa transition or
restoration semantics.

Runtime schema, FSM, scripts, default config, TUI, and shipped OS assets are
explicitly included in installed wheels. `python scripts/test-wheel` builds and
installs a wheel in a fresh venv outside the repository, checks `eve --help`,
loads runtime schemas/assets, and accepts/rejects command outputs. CI executes
this artifact check independently of source/Poetry test execution.
