# Bakery Billing (free, self-hosted)

Invoices with PDF, customers, products, expenses and analytics. Python (FastAPI) + Postgres.

## Setup in 6 steps (about 20 minutes, all free)
1. **GitHub:** create a free account and a new *private* repository. Upload everything from this folder (the `static` and `fonts` folders too).
2. **Neon (database):** sign up at neon.tech, create a project (pick Singapore if offered), open "Connect", and copy the connection string that starts with `postgresql://`. That is your `DATABASE_URL`.
3. **Render (hosting):** sign up at render.com with GitHub. New > Web Service > choose your repo.
   - Region: Singapore. Instance type: **Free**.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Environment variables** (same page, "Add environment variable"):
   - `DATABASE_URL` = the string from Neon
   - `APP_PASSWORD` = the password you choose for logging in
   - `PYTHON_VERSION` = `3.12.8`
5. Click **Create Web Service**. After a few minutes you get a URL like `https://yourname.onrender.com`. Open it and log in.
6. In **Settings** check the business details, upload the logo, and set the next invoice number.

## Storage (Neon free = 0.5 GB per project)
Photos are shrunk to roughly 100 KB each and stored as binary, so 0.5 GB holds around 5,000 photos (several years for a home bakery). Settings shows a live storage meter. Deleting an invoice or a photo frees its space. If you ever get close, upgrade Neon (it bills per GB) or tell me and I will move photos to free object storage.

## Notes
- Render's free service sleeps after ~15 minutes idle; the next visit takes up to a minute to wake. Your data is safe in Neon.
- Do not use Render's own free Postgres (it expires). Neon is permanent on the free plan.
- To update the app later, change the files on GitHub; Render redeploys by itself.
- Run on your own computer: `pip install -r requirements.txt`, then `APP_PASSWORD=mypassword uvicorn main:app --reload` (uses a local `bakery.db`).

## Weekly and monthly email summary (optional)
On Render add `MAIL_TO`, `SMTP_USER` (your Gmail) and `SMTP_PASS` (a Gmail "App password"). In GitHub repo settings add secrets `APP_URL` (your Render URL) and `APP_PASSWORD`; `.github/workflows/summary.yml` then emails a summary each Monday and on the 1st of the month. Test: `curl -u x:PASSWORD https://yourapp.onrender.com/api/cron/weekly`
