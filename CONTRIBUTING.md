# Contributing

## Add a provider

1. Add `providers/<provider>.yaml` with stable ID, source URLs, docs URL, attribution, thresholds.
2. Prefer configuration-driven adapters.
3. Add sanitized fixtures under `tests/fixtures/`.
4. Regenerate outputs and ensure tests pass.

## Adapter changes

- Keep adapter responsibilities limited to fetch + extract.
- Keep shared normalization/validation in shared modules.

## Test expectations

- Include fixture and deterministic output coverage.
- Validate strict CIDR parsing, ordering, dedupe, category handling, and no-op regeneration checks.
