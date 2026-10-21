# Sanitized CrossNode delivery workspace

This parent repository pins component submodules and contains sanitized deployment/acceptance/performance material. Component source changes belong in each component repository. Do not copy binaries or source trees into the parent.

Read VERSION.md before work. Use exact gitlinks, not submodule update --remote. Preserve existing dirty changes. Make component commits available upstream before updating parent pins.

All builds and tests must run on a remote task-isolated environment, not the local development workstation. Do not modify shared services, stop unrelated processes, or disable isolation or TLS validation. Use per-task credentials outside Git.

Distinguish source, historical acceptance, new build and deployment identities. Record every component state change in VERSION.md. Document checks in Docs/checks/ with question, method, data, conclusion, followups, command-level reproduction and cleanup disclosure. Keep plans separate from accepted progress.

This delivery has no complete fresh-host full SDK/reader-retirement replay yet. Do not claim that component tests, native diagnostics or historical binary measurements establish production readiness.

