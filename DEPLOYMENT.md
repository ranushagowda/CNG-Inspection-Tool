# Private online deployment

This project is a browser-based app. Render runs the Flask app, PostgreSQL stores
the shared records, and a Render cron job sends reports. Users only need the
HTTPS link and an account created by an administrator.

## Before deployment

- Create a private GitHub repository and push the app source, including
  `render.yaml`. Do not upload `cng.db`, Excel files, `.env` files, or other
  private data. `.gitignore` excludes the local database and generated workbook.
- The Render Blueprint provisions paid services: a Starter web service, a
  Starter cron job, and a Basic PostgreSQL database. Review current prices and
  database backup/retention options in Render before approving creation.
- Rotate the email app password that was previously present in the source code.
  For Gmail, use an app password rather than your normal account password.

## Deploy and migrate existing records

1. In Render, create a Blueprint from the private GitHub repository and deploy
   `render.yaml`. Set the prompted `INITIAL_ADMIN_USERNAME`,
   `INITIAL_ADMIN_PASSWORD`, `SMTP_USER`, `SMTP_PASS`, and `SMTP_FROM` values in
   Render's private environment settings. Use a password of at least 12
   characters. If you want the migration to replace the existing admin
   password with this new password, set `INITIAL_ADMIN_USERNAME` to that
   existing admin's username. Do not commit or share credentials in chat.
2. Wait for the PostgreSQL database to be created. Copy its **External
   Database URL** from the database page. Treat it as a password.
3. On the computer that has the existing `cng.db`, open PowerShell in the
   project folder and set the URL for this terminal only:

   ```powershell
   $env:DATABASE_URL = "paste-the-Render-External-Database-URL-here"
   python migrate_sqlite_to_postgres.py
   ```

   The migration refuses to overwrite inspection data. It replaces only the
   single bootstrap admin created during first deployment, copies existing
   users and records, and hashes any legacy plain-text passwords. Keep the
   database URL private and do not paste it into source files or chat.
4. Wait for the web service to finish starting, sign in, and confirm records
   and admin email addresses are correct. If the imported admin did not match
   the bootstrap username, change its password now. Remove
   `INITIAL_ADMIN_PASSWORD` from Render's environment after the migration.
5. In the admin screen, create individual accounts for approved users and set
   the email address for each admin who should receive reports. Share the
   HTTPS link only with your group. The login page can be visited by anyone
   who knows the URL, but app pages and data APIs require a valid login.

## Scheduled reports

The cron job runs every day at 17:30 India time (12:00 UTC). It sends the daily
summary and, on the last calendar day of each month, the monthly Excel report
in the same run. Reports are sent to admins with an email address saved in
their profile. The web app does not need to be open, and your computer can be
off. Review the cron run history and logs in Render after deployment. The SMTP
settings are private service environment variables shared with the cron job.

## Notes

- The app's Excel-style page and authenticated **Download Excel** link read
  from the same PostgreSQL database, so all signed-in users see shared data.
- Keep automatic database backups enabled and test a restore. Hosting and
  scheduled jobs depend on the Render account, service status, and billing.
- If a report run fails, Render marks the cron run as failed and records logs;
  fix the SMTP or admin-email configuration and manually trigger the job.
- Do not expose the Render database URL publicly. Users never need Python,
  PostgreSQL, or a local database installed on their devices.
