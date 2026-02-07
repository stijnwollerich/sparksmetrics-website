# Deploy Sparksmetrics to a DigitalOcean Droplet

Run these on your droplet (Ubuntu 22.04 / 24.04). Replace placeholders:

- `YOUR_DOMAIN` → e.g. `sparksmetrics.com`
- `YOUR_REPO_URL` → e.g. `https://github.com/yourusername/sparksmetrics-website.git`
- `APP_USER` → user that runs the app (e.g. `deploy` or `root`; below uses `deploy`)
- `APP_DIR` → e.g. `/var/www/sparksmetrics`

---

## What to run every time you deploy

**On your local machine** (from the project root):

```bash
git add -A && git status   # review changes
git commit -m "Your message"
git push
```

**On the server** (SSH into the droplet, then):

```bash
cd /var/www/sparksmetrics   # or your APP_DIR
git pull
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sparksmetrics
```

If you added new DB tables or this is the first deploy: run `python3 scripts/create_tables.py` once (see section 5).

**Env / secrets:**  
- **Local:** `.env` can have `FLASK_DEBUG=1`, `SECRET_KEY=...`, and optionally `DATABASE_URL` if you run Postgres locally. If `DATABASE_URL` is missing, the app runs but lead forms won’t be saved to a DB.  
- **Server:** `.env` must have `FLASK_DEBUG=0`, `SECRET_KEY=...`, and `DATABASE_URL=postgresql://sparksmetrics:YOUR_PASSWORD@localhost:5432/sparksmetrics`. Use the same password you set in PostgreSQL (section 2). Do not commit `.env`; it is in `.gitignore`.

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

If `scripts/create_tables.py` is not on the server yet, use this one-liner (paste as a single line, no extra spaces):

```bash
python3 -c "from app import create_app; from app.models import db; app = create_app(); app.app_context().push(); db.create_all(); print('Tables created.')"
```

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

If you use root and `/var/www/sparksmetrics`, you can install the unit from the repo:

```bash
sudo cp $APP_DIR/deploy/sparksmetrics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sparksmetrics
sudo systemctl start sparksmetrics
sudo systemctl status sparksmetrics
```

(Or create `/etc/systemd/system/sparksmetrics.service` manually and paste the same content as in `deploy/sparksmetrics.service`.)

---

## 8. Nginx (site on IP now; add domain later)

Install the config from the repo (or copy the contents of `deploy/nginx-sparksmetrics.conf`):

```bash
sudo cp /var/www/sparksmetrics/deploy/nginx-sparksmetrics.conf /etc/nginx/sites-available/sparksmetrics
sudo ln -sf /etc/nginx/sites-available/sparksmetrics /etc/nginx/sites-enabled/
# Remove default site so this one is used for all requests
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Allow HTTP in the firewall (if you use ufw):

```bash
sudo ufw allow 80
sudo ufw status
```

The site is now available at **http://YOUR_DROPLET_PUBLIC_IP** (get the IP from the DigitalOcean dashboard or run `curl -s ifconfig.me` on the server).

**When you want to use your real domain:** point your domain’s DNS A record to the droplet’s IP, then edit the Nginx config and add your domain to `server_name`:

```bash
sudo nano /etc/nginx/sites-available/sparksmetrics
# Change: server_name _;
# To:     server_name _ yourdomain.com www.yourdomain.com;
sudo nginx -t && sudo systemctl reload nginx
```

(Optional) Then add HTTPS with Certbot (section 9).

---

## 8b. Go live: switch sparksmetrics.com from WordPress (Hostnet) to droplet

**1. On the droplet** – ensure Nginx serves the domain and pull latest config:

```bash
cd /var/www/sparksmetrics && git pull
sudo cp /var/www/sparksmetrics/deploy/nginx-sparksmetrics.conf /etc/nginx/sites-available/sparksmetrics
sudo ln -sf /etc/nginx/sites-available/sparksmetrics /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow 80
sudo ufw allow 443
sudo ufw status
```

**2. Get your droplet’s public IP** (e.g. DigitalOcean dashboard or `curl -s ifconfig.me` on the server).

**3. At Hostnet (DNS)** – point the domain to the droplet:

- **sparksmetrics.com** → A record → droplet IP (e.g. `167.172.32.42`)
- **www.sparksmetrics.com** → A record → same droplet IP (or CNAME to `sparksmetrics.com` if you prefer)

Remove or leave old WordPress A records; once the new A records propagate, traffic goes to the droplet.

**4. Wait for DNS** – can take a few minutes up to 48h. Check with:

```bash
dig sparksmetrics.com +short
dig www.sparksmetrics.com +short
```

When both show your droplet IP, continue.

**5. Add HTTPS on the droplet** (after DNS points to the droplet):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d sparksmetrics.com -d www.sparksmetrics.com
```

Follow the prompts (email, agree to terms). Certbot will configure SSL and redirect HTTP → HTTPS.

**6. Test** – open https://sparksmetrics.com and https://www.sparksmetrics.com. Your Flask app is live; WordPress on Hostnet is no longer used for this domain.

---

## 9. HTTPS with Certbot (if not done in 8b)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d sparksmetrics.com -d www.sparksmetrics.com
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
- [ ] Nginx config installed; `nginx -t` passes; port 80 (and 443 for SSL) allowed
- [ ] DNS: A records for sparksmetrics.com and www.sparksmetrics.com point to droplet IP
- [ ] Certbot run so https://sparksmetrics.com works
