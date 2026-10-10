# Private online deployment (free-tier setup)

Users open the hosted HTTPS link in a browser; they do not install Python or
PostgreSQL. The free-tier setup uses:

- Render's free web service for the Flask app.
- Neon's free PostgreSQL database for shared records.
- A scheduled GitHub Actions workflow for daily and monthly emails.

This is a $0 hobby setup, not an always-on or production-reliability promise.
Render's free web service sleeps after inactivity, the free database and
GitHub Actions have quotas/limits, and GitHub may delay scheduled workflows.
An email configured for 5:30 PM India time is scheduled then, but is not
guaranteed to arrive exactly at 5:30 PM.

## Before deployment

- Keep the GitHub repository private. The checked-in `.gitignore` excludes
  `cng.db`, Excel files, and generated files; never force-add local records,
  credentials, or `.env` files.
- Create a Neon free project and copy its PostgreSQL connection string. Treat
  this URL as a password. Do not use Render's free PostgreSQL for permanent
  data: Render's free database expires after 30 days.
- Rotate the email app password that was previously present in the source
  code. For Gmail, use an app password, not your normal account password.

## Deploy the app and migrate existing records

1. In Render, create a Blueprint from the private GitHub repository and deploy
   `render.yaml`. Choose only the **Free** web plan. Set the prompted
   `DATABASE_URL` to the Neon connection string and set
   `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`. Use a password of at
   least 12 characters. If migrating an existing account, use that admin's
   existing username so the initial password can be replaced. Do not paste
   secrets into chat or commit them.
2. After the web service is deployed, copy the same Neon connection string into
   these private GitHub repository Actions secrets:
   `DATABASE_URL`, `SMTP_USER`, `SMTP_PASS`, and `SMTP_FROM`. Add them under
   **Settings → Secrets and variables → Actions → New repository secret**.
   These are used only by the report workflow.
3. On the computer containing the existing `cng.db`, open PowerShell in the
   project folder and set the Neon URL for that terminal session:

   ```powershell
   $env:DATABASE_URL = "paste-the-Neon-connection-string-here"
   python migrate_sqlite_to_postgres.py
   ```

   The migration refuses to overwrite inspection data. It replaces only the
   single bootstrap admin, copies existing users and records, and hashes legacy
   plain-text passwords. Keep the database URL private.
4. Open the Render web-service URL, sign in, confirm the records and admin
   email addresses, and remove `INITIAL_ADMIN_PASSWORD` from the Render
   environment after migration. If you did not migrate the old admin account,
   sign in with the new bootstrap account instead.
5. In the admin screen, create accounts only for approved users and set the
   email address on every admin profile that should receive reports.
6. In the private GitHub repository, open **Actions** and enable workflows if
   GitHub asks. Select **Daily and monthly email reports → Run workflow** to
   test sending. Check the run logs for errors, and then verify the next daily
   scheduled run.

## Scheduled reports

The GitHub Actions workflow in `.github/workflows/daily-reports.yml` uses
`0 12 * * *` UTC, which is 5:30 PM India time. Every run sends the daily
summary. On the last calendar day of the month, that same run also sends the
monthly Excel report. Reports go to admin addresses saved in their profiles.
The workflow runs independently of your laptop and the web service being open.
GitHub scheduled workflows can be delayed or dropped during high load; review
**Actions → Daily and monthly email reports** for run status and logs.

## Limitations and privacy

- The free Render web service can sleep after inactivity and take about a
  minute to start when next opened. Its local filesystem is temporary, so the
  database must stay on Neon, not in `cng.db` on Render.
- Check the current Neon free-plan storage/compute limits and GitHub Actions
  free-minute quota for your account. Set usage alerts or limits where
  available.
- The app's Excel-style page and authenticated **Download Excel** link read
  from the shared PostgreSQL database. The app requires login for records and
  data APIs, although anyone with the URL can reach the sign-in page.
- A free tier may change its terms or limits. Keep an independent backup of
  important records.
- Do not expose the database URL, SMTP app password, or Render secret key.
