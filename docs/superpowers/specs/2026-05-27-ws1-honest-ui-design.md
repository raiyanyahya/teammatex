# WS1 — Fix the lies (honest UI)

_Date: 2026-05-27_

## Goal

Stop the UI from misrepresenting state. Two classes of problem: a render bug that
hides real progress, and Settings controls that look editable but aren't wired.
Scope decision (chosen): **stop-lying only** — make the genuinely-backed controls
real (LLM, GitHub), and honestly disable/label the rest until their backends exist.

## 1. Onboarding stage green-checks (bug)

`onboarding/page.tsx` builds `stages[i] = s` where `s = {stage, status, error}`, then
the per-stage render does `const status = stages[i]; isDone = status === "completed"`
— comparing the **object** to a string, so stages never render done. Fix: read
`stages[i]?.status`. Completed → green check, running → spinner, failed → red, else
the numbered placeholder. (The header count already reads `.status`, so it's correct.)

## 2. Settings → LLM (make real)

Endpoints (all exist): `GET /api/config/llm/providers` → `{providers: {p:[{model,tier,note}]},
default_provider, active:{provider,model}}`; `PUT /api/config/llm_config`.

- On load, fetch providers; show **Active: `<provider>` · `<model>`** from `active`.
- Provider `<select>` from `Object.keys(providers)`; model `<select>` from
  `providers[provider]` showing `model` + `tier` (kills the hardcoded/stale list with
  `claude-3-5-sonnet`/`gpt-4o`).
- API key field is **optional on edit**: if left blank and the provider is unchanged,
  reuse the stored key (loaded from `GET /api/config` `llm_config.api_key`) so changing
  just the model doesn't force re-entering the key.
- Save → `PUT llm_config` → re-fetch providers so the Active badge updates.

## 3. Settings → Integrations → GitHub (make real)

`POST /api/config/github_token/verify {}` → `{valid, configured, login, token_type,
can_push, scopes, note}`. `PUT /api/config/github_token`; `DELETE /api/config/github_token`.

- On load, verify the stored token. If valid: show **Connected as `<login>` · `<token_type>`**
  and a push-rights line — for the fine-grained token `can_push` is `null`, so surface the
  returned `note` (the read-only/403 warning). If not configured: "Not connected" + input.
- Update token (PUT + `POST /api/integrations` like today) → re-verify. **Disconnect**
  (DELETE) → back to "Not connected".

## 4. Made honest (disabled + labeled — not wired)

- **Slack / Jira** inputs: disabled, note "Not wired up yet."
- **Updates** tab: disabled; note "Auto-sync runs on a fixed schedule; configurable
  scheduling isn't wired up yet." (auto_sync runs, but the interval isn't config-driven.)
- **Permissions** tab: disabled; note "Not enforced yet." (Only a model exists.)
- **Persona** tab: disabled; note "Set via the `TEAMMATEX_TEAMMATE_PERSONA` env var;
  in-app editing isn't wired up yet." (runtime reads `settings.teammate_persona`, not config.)

## Out of scope (noted, not done here)

- `GET /api/config` returns the raw `llm_config.api_key` to any authenticated client —
  a pre-existing info leak; worth fixing separately (mask/omit secrets server-side).
- Actually wiring persona/auto-sync/permissions/slack/jira — each is its own feature.

## Testing

Frontend-only (no backend change). Verify in the running app via authenticated
headless Chrome: onboarding shows green checks at 12/12; LLM shows the active model
and a populated dropdown; GitHub shows "Connected as raiyanyahya" + the push note;
the disabled tabs render their honest labels.
