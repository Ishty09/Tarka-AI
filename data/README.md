# data/

Operator-side input lists. **`.json` and `.txt` files in this directory are
gitignored** so production invitee lists never land in the repo. Only
`*.example` files are tracked.

## Beta invite lists

Copy the example, fill in real emails, run the script:

```bash
cp data/inner-circle.json.example data/inner-circle.json
$EDITOR data/inner-circle.json

NEXT_PUBLIC_SUPABASE_URL=... \
SUPABASE_SERVICE_ROLE_KEY=... \
pnpm invite:beta -- --file data/inner-circle.json --cohort wave-0 --dry-run

# When the dry-run looks right:
pnpm invite:beta -- --file data/inner-circle.json --cohort wave-0
```

See `infra/runbooks/beta-cohort.md` for the rest of the procedure.

## Cohort naming convention

- `wave-0` — inner circle (≤ 10 people, friends + family). First send.
- `wave-1` — extended friends, founder network. Sent after wave-0 looks
  stable (24-48h later).
- `wave-2` — public hand-picked list (HN, X, partners). Sent after wave-1
  retention starts looking healthy.
- `product-hunt` — anyone who signs up via the PH link post-launch.

Cohort tag is what `cohort_retention` view + `/admin/retention` slice on,
so naming consistency matters.
