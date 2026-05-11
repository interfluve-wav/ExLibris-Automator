# Security Policy

ExLibris Automator handles credentials for a live academic research
repository (UMassD Esploro), an OpenAI API key, and a Discord bot token.
Treat this codebase as credential-adjacent and apply the practices below.

---

## 1. Supported versions

The project ships from the `JIT` branch. Only the most recent commit on `JIT`
is supported with fixes. Older commits are kept for history only.

---

## 2. Secrets that must never be committed

| Secret | Where it should live | Notes |
|---|---|---|
| `ESPLORO_USERNAME`, `ESPLORO_PASSWORD` | `.env` (gitignored) or process env | Esploro login. Rotate immediately if exposed. |
| `OPENAI_API_KEY` | `.env` or process env | Treat as a billing key. Rotate via the OpenAI dashboard. |
| `DISCORD_BOT_TOKEN` | `.env` or process env | A leaked token can be revoked in the Discord developer portal; do not just edit the file and force-push. |
| `auth.json` | machine-local | Playwright storage state if you ever capture one — gitignored. |
| `*.env`, `.env.*` | machine-local | Catch-all for environment dumps. |

`.gitignore` covers all of the above. Confirm before committing:

```bash
git status
rg --hidden -n "(sk-[A-Za-z0-9]{16,}|xox[baprs]-|AIza[A-Za-z0-9_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)" \
   -g '!.git' -g '!.venv' -g '!node_modules'
```

The only matches you should ever see for `OPENAI_API_KEY=…`,
`ESPLORO_PASSWORD=…`, or `DISCORD_BOT_TOKEN=…` in tracked files are
**documented placeholders** like `sk-prod-...`, `your_password`,
`your_discord_token` in `docs/ENV_EXAMPLE.md`, `docs/DISCORD_SETUP.md`,
`docs/Web App & Discord Bot Integration Steps.md`, and
`deployment/DEPLOYMENT.md`.

---

## 3. If a secret is exposed

1. **Rotate first, fix the repo second.** A pushed secret must be assumed
   compromised even if you delete the commit.
2. Rotate paths:
   - **OpenAI:** dashboard → API keys → revoke + create new.
   - **Discord:** developer portal → Bot → reset token.
   - **Esploro:** change the operator account password through the normal
     UMassD identity flow.
3. Remove from history. For a single recent commit, the safest path is to
   commit a redacted version and **rotate**. Only force-push history rewrites
   with explicit maintainer approval, and never to `main` without
   coordination.

---

## 4. CI / pre-commit

- `.pre-commit-config.yaml` is in the repo. Enable locally:
  `pip install pre-commit && pre-commit install`.
- CI runs **TruffleHog** on every push (see `Fix TruffleHog CI invocation
  for push events` commit). A failing scan blocks merges by design.
- Do not add `--no-verify` to `git commit` to bypass these hooks unless the
  maintainer has explicitly approved the bypass for a specific commit.

---

## 5. Network / runtime exposure

- The Flask UI binds to `localhost` only. **Do not** expose it to a public
  interface without putting a proper reverse proxy with authentication in
  front of it (see `deployment/` for the systemd pattern).
- The Playwright worker uses real Chromium against the production Esploro
  instance. If you point it at a staging URL, document the override and
  make sure your `.env` reflects staging credentials.
- The Discord bot listens to the channel ID in `CITATION_CHANNEL_ID`. Pick
  a private channel; assume anyone with write access there can enqueue
  citations.

---

## 6. Reporting a vulnerability

This project is operated as an internal tool for UMass Dartmouth. If you
discover a security issue:

1. **Do not** open a public GitHub issue.
2. Email the maintainer directly (the GitHub profile on the latest commits
   is the canonical contact).
3. Include reproduction steps, scope (which secret / which endpoint / which
   data path), and your assessment of impact.

A fix-or-mitigation timeline of **7 days** is the target for credential or
authentication issues. Lower-severity issues are handled on the next
practical release of the `JIT` branch.

---

## 7. Defense-in-depth checklist for contributors

Before merging anything that touches credentials, auth, or external HTTP:

- [ ] All secrets read via `os.getenv(...)` or `python-dotenv`. No literals.
- [ ] No `print()` of env values or full HTTP request bodies.
- [ ] No new files written into the repo root with operator data; route
      runtime output to `logs/` or the configured CSV/summary paths.
- [ ] Any new outbound HTTP target is documented in
      [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- [ ] If you added a new env var, it's in `docs/ENV_EXAMPLE.md` and in
      [`README.md`](README.md) §"Environment Variables".

Adhering to this checklist is what keeps the threat surface small.
