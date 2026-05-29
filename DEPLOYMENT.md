# Deploying Smart Canteen to Vercel with Supabase

1. Create a Supabase project and copy its Postgres connection string.
   Use the pooled connection string when possible, and keep `sslmode=require`.

2. Add these Vercel environment variables:

   - `DATABASE_URL`
   - `DJANGO_SECRET_KEY`
   - `DJANGO_DEBUG=false`
   - `DJANGO_ALLOWED_HOSTS=.vercel.app,your-domain.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://*.vercel.app,https://your-domain.com`
   - `CANTEEN_ADMIN_PASSWORD`
   - `CANTEEN_STAFF_PASSWORD`
   - `TIME_ZONE=Asia/Manila`

3. Deploy the project to Vercel. The build runs:

   ```bash
   python manage.py collectstatic --noinput
   ```

4. Run migrations against Supabase after setting `DATABASE_URL` locally or in a one-off shell:

   ```bash
   python manage.py migrate
   ```

5. For the RFID bridge, run it on the computer connected to the reader and point it at the deployed app:

   ```powershell
   $env:SCAN_API_URL="https://your-app.vercel.app/api/scan/"
   python rfid_bridge.py
   ```
