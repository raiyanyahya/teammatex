# Security Policy

TeammateX is a **single-user, self-hosted** AI teammate. By design it has broad
access to the machine it runs on — that is the product premise ("a teammate that
already knows everything local and can just do the work"). Read this before
exposing it anywhere beyond your own machine.

## Supported versions

TeammateX is in **alpha**; only the latest `master` is supported. Please track
`master` and report issues against a recent commit.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately via
[GitHub Security Advisories](https://github.com/raiyanyahya/teammatex/security/advisories/new),
or by email to **raiyanyahyadeveloper@gmail.com**.

Include as much of the following as you can:

- A description of the issue and its impact.
- Steps to reproduce or a proof-of-concept.
- The affected component and commit/version.

We aim to acknowledge reports within a few days and will keep you updated on the
fix. Please give us a reasonable window to remediate before any public
disclosure. Because this is an alpha, self-hosted project, there is no bug-bounty
program — but credit is gladly given in the release notes if you'd like it.

## What is intentional (and why)

- **The agent has a real, unrestricted shell** (`run_command`) and full read/write
  access to the filesystem inside its container. It runs `git`, `gh`, `npm`, tests,
  etc. itself. There is deliberately no command allow-list — the container is the
  sandbox.
- **Containers run as root** and the **Docker socket is mounted** into the app.
  This lets the teammate manage repos/containers, but it also means code in the
  container is effectively host-root.
- **Provider keys and GitHub tokens live in Postgres** (`app_config` table), not in
  `.env` (the env keys are intentionally empty). They persist in the DB volume.

### Trust boundary

Because of the above, **anyone who can reach the API can run arbitrary commands on
the host.** Treat the host as the trust boundary:

- Keep it bound to `localhost` / a trusted network. Do **not** expose it to the
  public internet.
- Put authentication in front of it if multiple people can reach it.

## Secrets — rules

- **Never commit real secrets.** `.gitignore` already excludes `.env`, `.env.*`, and
  `*secret*`. Do not paste API keys or tokens into Markdown/docs.
- Secrets belong in the DB (via `PUT /api/config/...`) or in untracked `.env`.

> **Rotate exposed credentials.** An earlier `NEXT.md` committed a real DeepSeek API
> key and a GitHub PAT. The file has been removed, but **they remain in git history**
> and must be rotated:
> - DeepSeek: revoke the old key at the DeepSeek console, issue a new one, re-save via
>   `PUT /api/config/llm_config`.
> - GitHub: delete the PAT at github.com/settings/tokens, issue a new one with
>   Contents: write + Pull requests: write, re-save in Settings.
> To purge them from history entirely, rewrite history (`git filter-repo`) or rotate
> and move on (rotation is what actually matters).

## Hardening options (if you ever expose it)

- Run containers as a non-root user; drop the Docker socket mount.
- Gate `run_command` behind an allow-list / approval step.
- Front the API with real auth + TLS.
- Use short-lived, least-privilege GitHub tokens (fine-grained, single-repo).
