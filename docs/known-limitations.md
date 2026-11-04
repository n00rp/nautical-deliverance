# Known limitations (S0)

- `nd_app` can call `set_config` to switch organization; isolation relies on the engine never executing untrusted SQL (S0-R04, `engine/tests/db/test_rls.py`).
- SQLSTATE 42501 (insufficient privilege) from a missing GRANT surfaces as HTTP 403 (engine API error mapping).
- `tools/trace.py` counts `req("...")` inside comments as coverage (D-036).
- No branch protection on GitHub Free; only squash-only merging is checked (D-043).
- CodeQL is dormant until the repository supports it (D-045).
- Trivy ignores unfixed vulnerabilities (`--ignore-unfixed`); a weekly report covers them (D-046).
- Keycloak runs in `start-dev` with dev passwords and a dev realm: dev/CI only (`infra/docker-compose.yml`).
- `PyJWKClient` refetches the JWKS on an unknown `kid`; rate limiting is a P6 concern (`engine/src/nautical_deliverance/api/auth.py`).
