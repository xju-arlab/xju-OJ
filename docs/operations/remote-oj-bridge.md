# Remote OJ bridge

XJU-OJ can reuse practice problems from Luogu, Nowcoder, and Codeforces without
storing third-party passwords or cookies on the server. A ScriptCat userscript
runs the provider interaction inside each user's own browser session.

## User setup

1. Open `/remote-bridge` on the OJ.
2. Install ScriptCat if the browser does not already have it. The Edge add-on is
   preferred for lab computers with domestic network access.
3. Click **Install userscript** once. ScriptCat uses the script's `updateURL` for
   later updates.
4. Log in to each external OJ that the user wants to submit to.

The script is served from
`/static/userscripts/xju-oj-remote-bridge.user.js`. Nginx disables caching for
this file so updates are immediately visible to ScriptCat.

## Submission flow

Remote problems use the same editor and submit button as local problems. The
visible lifecycle is:

```text
Submitting -> Judging -> provider verdict
```

The OJ creates the submission row first and sends a validated, allowlisted task to
the userscript. The userscript first submits through credentialed background
requests using the provider account already logged in to that browser.

If the provider requests Turnstile, NetEase/YIDUN, an image CAPTCHA, login, or a
risk-control check, the userscript opens the provider's native page for the user
to complete it. The OJ never attempts to solve or proxy the challenge. Once the
provider accepts the submission, result polling continues in the OJ tab.

Supported browser-side adapters:

- Codeforces: native submission form and official submission-status API.
- Luogu: `/fe/api/problem/submit/{pid}`, native verification fallback, and
  record polling.
- Nowcoder ACM/problem pages: session submit API, native risk-control fallback,
  and result polling.

Version 1.1.0 persists pending result events per submission in userscript storage.
An event is removed only after the backend acknowledges it successfully, including
the JSON business status. Network failures and rejected acknowledgements retry
with bounded backoff. Reopening an OJ tab resumes delivery; a shared browser lease
limits duplicate polling from multiple tabs. Provider session tokens remain in
the browser. The OJ tab must stay open for delivery to continue.

The submission list distinguishes provider login, verification, active judging,
and a result that has not synced recently. Submission details offer **Continue
submission** or **Sync result** to the original submitter. `GET
/api/remote_submission/recover` returns only that user's unfinished runs with a
remote ID for automatic query recovery; the explicit `submission_id` form can
also restore the stored code for a task that still needs login or verification.
Recovery never submits code again for an existing remote ID. An interrupted
provider POST with an unknown outcome is retained for checking against the
provider's records, rather than automatically sending a duplicate submission.

Optional invalid statistics (including NaN/null percentages from Nowcoder) do
not reject a final verdict. Compiler messages are bounded and displayed in
submission details. Luogu's overall unaccepted verdict is interpreted according
to the problem rule: ACM uses a known failing testcase verdict, or wrong answer
when no specific failure is available; OI retains positive partial scores.
Zero-score unaccepted records are not labeled partially accepted.

Old scripts may have deleted their local tasks before the backend received a
final verdict. After upgrading to 1.1.0 and refreshing an OJ tab, the recovery API
can rebuild result queries from remote IDs retained by the backend. Login or
verification still requires the original user's provider session. It cannot
reconstruct a remote ID lost before it ever reached the OJ or browser storage.

To repair historical Luogu ACM partial-verdict labels, preview with
`python manage.py normalize_remote_acm_verdicts`, then use `--apply`. The command
saves a private JSON backup under the backend data directory's `backups/` before
each problem's transaction. It normalizes failure labels and their matching
histogram/profile entries, preserving accepted counts, ranks, source code, and
submission timestamps. It does not guess verdicts for pending submissions.

## Admin problem import

The admin problem list exposes **Import Remote Problem** for both the public
library and a contest.

- Luogu accepts IDs such as `P1001` or a problem URL.
- Nowcoder accepts IDs such as `NC322024`, numeric ACM problem IDs, legacy UUIDs,
  and `ac.nowcoder.com/acm/problem/...` URLs.
- Codeforces accepts IDs such as `4A` or a problem URL. If the server is stopped
  by Cloudflare, the userscript opens Codeforces, waits for the browser challenge,
  reads only the rendered problem statement, and sends that statement back to
  the admin import API.

Imports are deduplicated by `(provider, remote_problem_id)`. Imported statements,
limits, samples, source metadata, provider language IDs, and provider URLs are
stored locally; test data is not copied because judging remains remote.

When editing a contest, an admin can either:

- select any public problem already in XJU-OJ, including self-authored and
  previously imported remote problems; or
- import a new remote problem directly as `A`, `B`, and so on.

A newly imported contest problem reserves a public display ID. A delayed backend
worker publishes a copy into the public library after the contest ends. Public
and admin problem-list requests also perform the same idempotent check, so an
expired task is repaired automatically. If the reserved ID was occupied later,
publication stays queued instead of silently choosing another ID.

## Security and trust boundary

- Provider credentials and cookies stay in the user's browser.
- Remote URLs and event transitions are allowlisted and validated by the backend.
- Provider pages never receive the user's XJU-OJ session credentials.
- The userscript has a 1 MiB source limit; Codeforces statement relay has a 2 MiB
  backend limit.
- Browser-reported remote verdicts are suitable for ordinary practice. They are
  inherently less trustworthy than local sandbox results because a user who can
  modify browser scripts can forge browser events. Do not use remote-provider
  verdicts as the sole authority for a formal ranked contest.

## Validation and release

Before release, run:

```bash
sh -n deploy.sh
node --check frontend/static/userscripts/xju-oj-remote-bridge.user.js
pnpm --dir frontend run lint:modern
pnpm --dir frontend run test:routes
pnpm --dir frontend run test:remote-bridge
pnpm --dir frontend run build
```

Backend regression coverage includes `submission.tests_remote_recovery`,
`submission.tests`, and `submission.tests_contest_practice`. Run these against
isolated test PostgreSQL/Redis instances; do not run tests on production data.

Apply Django migrations during the normal deployment. Production deployment is
still `./deploy.sh`; do not use the frontend development override in production.

Real-account acceptance should cover one accepted and one rejected submission
per provider, plus one forced verification/login flow. External DOM and private
API details can change independently of this repository, so this browser check
is required even when automated tests pass.
