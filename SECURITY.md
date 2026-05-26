# Security posture

TeammateX is a **single-user, self-hosted** AI teammate. By design it has broad
access to the machine it runs on — that is the product premise ("a teammate that
already knows everything local and can just do the work"). Read this before
exposing it anywhere beyond your own machine.

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
