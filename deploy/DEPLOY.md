# Deploy Sparksmetrics to a DigitalOcean Droplet

Run these on your droplet (Ubuntu 22.04 / 24.04). Replace placeholders:

- `YOUR_DOMAIN` → e.g. `sparksmetrics.com`
- `YOUR_REPO_URL` → e.g. `https://github.com/yourusername/sparksmetrics-website.git`
- `APP_USER` → user that runs the app (e.g. `deploy` or `root`; below uses `deploy`)
- `APP_DIR` → e.g. `/var/www/sparksmetrics`

---

## 1. Update system and install dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib git
```

---

## 2. PostgreSQL: create database and user

```bash
sudo -u postgres psql -c "CREATE USER sparksmetrics WITH PASSWORD 'CHOOSE_A_STRONG_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE sparksmetrics OWNER sparksmetrics;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sparksmetrics TO sparksmetrics;"
```

Use a strong password and save it; you’ll put it in `DATABASE_URL` below.

---

## 3. App user and project directory

```bash
sudo useradd -m -s /bin/bash deploy  # skip if you use root
sudo su - deploy   # or stay as root and use /var/www/sparksmetrics as your home
```

Then (as `deploy` or root):

```bash
# If using deploy user, use /home/deploy/sparksmetrics; else e.g. /var/www/sparksmetrics
export APP_DIR=/home/deploy/sparksmetrics   # or /var/www/sparksmetrics
mkdir -p $APP_DIR
cd $APP_DIR
git clone YOUR_REPO_URL .
# Or: copy your code here (e.g. rsync from your machine after you push)
```

---

## 4. Python venv and env vars

```bash
cd $APP_DIR
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` (replace values):

```bash
nano .env
```

Paste (adjust to your values):

```env
FLASK_APP=run.py
FLASK_DEBUG=0
SECRET_KEY=generate-a-long-random-string-here
DATABASE_URL=postgresql://sparksmetrics:CHOOSE_A_STRONG_PASSWORD@localhost:5432/sparksmetrics
```

Generate a secret: `python3 -c "import secrets; print(secrets.token_hex(32))"`

Save and exit (Ctrl+O, Enter, Ctrl+X).

---

## 5. Create DB tables

**You must create `.env` (step 4) first.** Otherwise you'll get: `RuntimeError: Either 'SQLALCHEMY_DATABASE_URI' or 'SQLALCHEMY_BINDS' must be set.`

Clear any stale bytecode so the app uses the latest config, then create tables:

```bash
cd $APP_DIR && source .venv/bin/activate
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
python3 scripts/create_tables.py
```

Or one-liner (no paste indentation):  
`python3 -c "from app import create_app; from app.models import db; app = create_app(); app.app_context().push(); db.create_all(); print('Tables created.')"`

Tables are also created automatically on first app start when `DATABASE_URL` is set (e.g. by systemd `EnvironmentFile` below).

---

## 6. Test Gunicorn

```bash
cd $APP_DIR && source .venv/bin/activate
gunicorn --bind 0.0.0.0:8000 "run:app"
```

Visit `http://YOUR_DROPLET_IP:8000`. If it works, stop with Ctrl+C.

---

## 7. Systemd service (run app on boot)

```bash
sudo nano /etc/systemd/system/sparksmetrics.service
```

Paste (fix `APP_DIR` and user if needed). **Use `EnvironmentFile`** so the app gets `DATABASE_URL` and other vars from `.env` (avoids relying on loading `.env` inside the app):

```ini
[Unit]
Description=Sparksmetrics Flask app
After=network.target postgresql.service

[Service]
User=deploy
Group=deploy
WorkingDirectory=/home/deploy/sparksmetrics
EnvironmentFile=/home/deploy/sparksmetrics/.env
Environment="PATH=/home/deploy/sparksmetrics/.venv/bin"
ExecStart=/home/deploy/sparksmetrics/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 "run:app"
Restart=always

[Install]
WantedBy=multi-user.target
```

If you use root and `/var/www/sparksmetrics`:

- `User=root` (or create a dedicated user)
- `WorkingDirectory=/var/www/sparksmetrics`
- `EnvironmentFile=/var/www/sparksmetrics/.env`
- `Environment="PATH=/var/www/sparksmetrics/.venv/bin"`
- `ExecStart=/var/www/sparksmetrics/.venv/bin/gunicorn ...`

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sparksmetrics
sudo systemctl start sparksmetrics
sudo systemctl status sparksmetrics
```

---

## 8. Nginx (reverse proxy and SSL later)

```bash
sudo nano /etc/nginx/sites-available/sparksmetrics
```

Paste (replace `YOUR_DOMAIN`):

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN www.YOUR_DOMAIN;
    root /home/deploy/sparksmetrics;   # or /var/www/sparksmetrics

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /home/deploy/sparksmetrics/app/static;   # or /var/www/sparksmetrics/app/static
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/sparksmetrics /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Point your domain’s DNS A record to the droplet’s IP.

---

## 9. (Optional) HTTPS with Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN -d www.YOUR_DOMAIN
```

---

## 10. Deploy updates (after git push)

```bash
cd /home/deploy/sparksmetrics   # or your APP_DIR
git pull
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sparksmetrics
```

---

## Checklist

- [ ] PostgreSQL user and database created; password in `.env` as `DATABASE_URL`
- [ ] `.env` has `SECRET_KEY` and `DATABASE_URL`
- [ ] Systemd service runs and `systemctl status sparksmetrics` is active
- [ ] Nginx config uses your domain and correct paths; `nginx -t` passes
- [ ] DNS A record for your domain points to the droplet IP
