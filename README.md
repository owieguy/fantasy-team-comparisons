# Fantasy Team Comparisons

Tracks each owner's combined NFL team record for two matchups (Owen vs Jamie,
Harry vs Jamie) and publishes an interactive, auto-updating website — no more
manually running a script and emailing a PNG.

- Live data comes from ESPN's public scoreboard API.
- `scripts/build_site.py` fetches the data and writes `docs/*/data.json` +
  `docs/*/index.html`. `docs/` is what GitHub Pages serves.
- A GitHub Actions workflow (`.github/workflows/update.yml`) runs that script
  every Tuesday and commits the refreshed data automatically.

## One-time setup

1. Create a new **public** repo on GitHub (public repos get free GitHub Pages).
2. Push this folder to it:
   ```bash
   git remote add origin https://github.com/<you>/<repo>.git
   git branch -M main
   git add .
   git commit -m "Initial site"
   git push -u origin main
   ```
3. In the repo on GitHub: **Settings → Pages** → under "Build and deployment",
   set Source to "Deploy from a branch", branch `main`, folder `/docs` → Save.
4. Your pages will be live at:
   - `https://<you>.github.io/<repo>/` — landing page with both links
   - `https://<you>.github.io/<repo>/owen-vs-jamie/`
   - `https://<you>.github.io/<repo>/harry-vs-jamie/`

   Send those two matchup links to whoever needs them.

## Automatic weekly updates

`.github/workflows/update.yml` is already wired up to run every **Tuesday at
3:00 AM US Eastern** (`08:00 UTC`) using GitHub's own free, built-in scheduler
— no separate cron service or account needed. It:

1. Runs `scripts/build_site.py` to pull fresh scores from ESPN.
2. Commits the updated `docs/*/data.json` files back to `main` if anything
   changed.
3. GitHub Pages picks up the new commit and the site updates automatically.

**DST caveat:** GitHub Actions cron is always UTC and doesn't shift for
daylight saving. `08:00 UTC` is exactly 3:00 AM Eastern during EST
(roughly early Nov–early Mar) but drifts to about 4:00 AM Eastern during EDT
(roughly Sept–early Nov). If you're not in US Eastern time, or want a
different hour, edit the `cron:` line in `.github/workflows/update.yml`
(use https://crontab.guru to compute the UTC value for your local 3 AM).

You can also trigger a run manually anytime from the repo's **Actions** tab →
"Update fantasy comparison site" → "Run workflow".

## Editing rosters / adding a matchup

Edit the `MATCHUPS` list near the top of `scripts/build_site.py` — each entry
is `slug` (used in the URL), `owner_left`, `owner_right`, `teams_left`,
`teams_right`. Commit and push; the next scheduled (or manual) run picks it
up. Rosters currently in there are placeholders carried over from the 2025
season — update them once real 2026 drafts are set.

## Running locally

```bash
pip install -r requirements.txt
python3 scripts/build_site.py
cd docs && python3 -m http.server 8000
# open http://localhost:8000/
```

## What happened to the old email version

`email_out.py` (and `basic.py` / `text_out.py`) sent a PNG via the macOS Mail
app on a schedule you had to trigger yourself from your Mac. This site
replaces that entirely: it's hosted for free, updates itself on a schedule,
and each matchup gets its own shareable link with hover-for-details and
interactive charts instead of a static image. Those old files are left in
place but are no longer used or needed — delete them whenever you like.
