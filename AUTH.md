# Sentinel Handshake & Tier Enforcement

## Boot Registration
Agent signs payload `{agent_id, version, ts}` with HMAC SHA-256 using `SENTINEL_SIGNING_KEY`
and POSTs to `${SENTINEL_URL}/v1/agents/register`.

## Run Authorization
Before each run, call `${SENTINEL_URL}/v1/authorize` with `{project_id, run_type}` signed.
Response `{allow: true|false}`. Deny on inactive tiers.

## Config
- `SENTINEL_URL`
- `SENTINEL_SIGNING_KEY`
- `AUTH_ENFORCE` (false = audit-only)

## Telemetry
- `authz_attempts_total{decision=allow|deny}`
