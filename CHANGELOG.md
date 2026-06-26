# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
TeammateX is in **alpha** and pre-1.0, so minor versions may include breaking
changes until the API stabilizes.

## [Unreleased]

### Security
- Block SSRF in the agent's `http_request` tool: resolve the host and reject
  any URL pointing at private, loopback, link-local, reserved, or metadata
  addresses; restrict to `http(s)`; disable redirect-following.
- Enforce the approved-API registry in `http_request` (opt-in: once any active
  entry exists, requests are limited to registered domains/methods/paths).
- Replace the in-process plugin "sandbox" with a real forked subprocess that
  applies `RLIMIT_AS` + `RLIMIT_CPU` and is killed on wall-clock overrun.
- Add an `execute` permission capability gating `run_command` / `run_lint` /
  `run_tests`, so shell access can be disabled from Settings.
- Make the session cookie `Secure` flag configurable via `COOKIE_SECURE`.

### Fixed
- `get_diff` / `get_blame` / `get_commit_log` opened the parent of the clones
  instead of a real repository and always raised; they now resolve a clone via
  `repo_name` / context / the sole repo.
- `schedule_task` no longer reports a false success; it schedules only known
  Celery tasks with a validated ISO `eta`, or returns an honest error.
- Align `_is_safe_path` tests with the hardened, workspace-confined contract.

### Added
- Project community files: `LICENSE` (MIT), `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, issue/PR templates, and this changelog.
- README "what it is" badges and an alpha-status notice.

<!--
Going forward, cut a dated, versioned section per release, e.g.:

## [0.1.0] - 2026-01-01
### Added
- ...
-->
