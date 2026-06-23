# Feature Self-Iteration

Governance feature changes should include the feature, the gate or runtime check that proves it works, and a focused selftest or explicit framework debt when full enforcement is too large.

Before finalizing a feature change, check:

- The runtime component registry or manifest exposes the new command, gate, or policy.
- The CLI path has stable JSON output for automation.
- False claims are avoided: plugin-enforceable, plugin-auditable, host-client-required, and model/API-required controls are separated.
- Selftest covers the success path and at least one failure or drift path when practical.
- Any deferred schema migration, host integration, or broad refactor is recorded as framework debt with severity.
