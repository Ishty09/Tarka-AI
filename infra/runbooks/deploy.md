# Deploy procedures

apps/web ships via Vercel; apps/workers ships via Coolify on the
DigitalOcean droplet. Both are git-driven — pushing to `main` is the
production deploy.

## apps/web (Vercel)

### Normal deploy

1. Land changes on `main`. Vercel's GitHub integration builds + ships
   automatically.
2. Watch the Vercel dashboard for the build. If it goes red:
   - Check the build log for the failing step.
   - Roll back via `vercel rollback` if it shipped a broken build.
3. Smoke test:
   - `curl https://quarrel.ai/api/health` → 200 + `"ok"`.
   - Open `/chat`, send one message, confirm streaming works.
   - Open `/settings/billing`, confirm subscription state renders.

### Rolling back

```
vercel rollback                # picks the most recent successful deploy
vercel rollback <deployment>   # specific deployment ID from the dashboard
```

A rollback is fully effective in under 30 seconds (Vercel edge
swap). Always pair the rollback with a Sentry filter for the bad
deploy SHA so the noise stops.

### Env var changes

1. Add the variable in **Vercel → Project → Settings → Environment
   Variables**.
2. Pick the right scope (Production / Preview / Development).
3. Trigger a redeploy — env changes don't apply to running builds.
4. Update `infra/SECRETS.md` if the value is sensitive.

## apps/workers (Coolify)

### Normal deploy

Coolify's GitHub webhook handler builds + restarts the worker container
on push to `main`. Default behaviour is rolling restart with health
probe.

Watch the deploy in Coolify → Applications → quarrel-workers → Logs.

Smoke test:

```
curl -H "Authorization: Bearer $CRON_SECRET" \
  https://api.quarrel.ai/health
```

Plus a synthetic chat round-trip from a logged-in browser.

### Rolling back

Coolify keeps the last successful image tagged. To roll back:

1. Coolify → Applications → quarrel-workers → Deployments.
2. Pick the previous green deploy → "Redeploy".

Restore takes ~30 seconds; the LiteLLM proxy and database connections
re-establish on first request.

### Env var changes

1. Coolify → quarrel-workers → Environment Variables.
2. **Restart required**: yes (the FastAPI process reads env at boot).
3. Update `infra/SECRETS.md` if sensitive.

## Coordinated deploys

When a change touches both apps (e.g., a new chat field), deploy in
dependency order so the workers can serve the new request shape before
the web sends it:

1. Merge to `main`.
2. Wait for Coolify (workers) green.
3. Wait for Vercel (web) green.
4. Smoke test.

If the web ships first and the workers haven't caught up, requests will
fail with a schema mismatch until the workers deploy completes. The
dependency-ordered wait above prevents the user-visible blip.

## Deploy freeze

Per §27 step 27 (post Phase L) and during the §28 launch window, no
production deploys without explicit sign-off. To enforce:

1. Set `VERCEL_FORCE_NO_DEPLOY=1` in the Vercel project env (Vercel
   honors this to skip auto-builds).
2. Disable the Coolify GitHub webhook.
3. Add a banner in this file + the README naming the freeze window.

Unfreezing is the same reversed.

## Vercel + Coolify auth

- Vercel deploy token: stored as `VERCEL_TOKEN` in 1Password. Used by
  ad-hoc CLI runs from the founder's laptop only — no CI uses it.
- Coolify webhook: GitHub → Webhooks. URL + secret in 1Password under
  `Coolify GitHub webhook`.

## Mobile (later)

When `apps/mobile` ships, deploys go through EAS Build + EAS Submit
with manual approval per §3. Add procedure here when that lands.
