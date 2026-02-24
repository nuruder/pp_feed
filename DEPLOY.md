# PadelPoint Parser — Operations Guide

## Deploying on Ubuntu VPS (from scratch)

### 1. System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
    postgresql postgresql-contrib \
    git curl wget
```

If `python3.11` is not in the default repos (Ubuntu 22.04):
```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### 2. PostgreSQL

```bash
# Create database and user
sudo -u postgres psql <<'SQL'
CREATE USER padelpoint WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
CREATE DATABASE padelpoint OWNER padelpoint;
GRANT ALL PRIVILEGES ON DATABASE padelpoint TO padelpoint;
SQL
```

Verify connection:
```bash
psql -U padelpoint -h localhost -d padelpoint
```

### 3. Project

```bash
# Clone
cd /opt
sudo mkdir pp_parser && sudo chown $USER:$USER pp_parser
git clone <your-repo-url> pp_parser
cd pp_parser

# Virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Dependencies
pip install -r requirements.txt

# Playwright (headless Chromium)
playwright install chromium
playwright install-deps
```

### 4. Configuration

```bash
cp .env.example .env
nano .env
```

Set all values:
```
DATABASE_URL=postgresql+asyncpg://padelpoint:CHANGE_ME_STRONG_PASSWORD@localhost:5432/padelpoint
PP_EMAIL=your_email@example.com
PP_PASSWORD=your_password
TWOCAPTCHA_API_KEY=your_2captcha_api_key
REQUEST_DELAY=1.5
API_HOST=0.0.0.0
API_PORT=8000
```

### 5. Initialize DB and first scrape

```bash
source .venv/bin/activate
cd /opt/pp_parser

# Create tables and scrape categories
python -m scraper.categories

# Scrape product listings
python -m scraper.products

# Authenticate (auto via 2Captcha, or manual fallback)
python run.py auth login

# Full scrape (prices, sizes, descriptions)
python run.py scrape full
```

### 6. systemd services

#### Scraper scheduler

```bash
sudo tee /etc/systemd/system/padelpoint-scheduler.service << 'EOF'
[Unit]
Description=PadelPoint Scraper Scheduler
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/pp_parser
ExecStart=/opt/pp_parser/.venv/bin/python run.py scheduler
Restart=always
RestartSec=60
Environment=PATH=/opt/pp_parser/.venv/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF
```

#### API server

```bash
sudo tee /etc/systemd/system/padelpoint-api.service << 'EOF'
[Unit]
Description=PadelPoint API
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/pp_parser
ExecStart=/opt/pp_parser/.venv/bin/python run.py api
Restart=always
RestartSec=10
Environment=PATH=/opt/pp_parser/.venv/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF
```

#### Enable and start

```bash
# Give www-data access
sudo chown -R www-data:www-data /opt/pp_parser/data

sudo systemctl daemon-reload
sudo systemctl enable padelpoint-scheduler padelpoint-api
sudo systemctl start padelpoint-scheduler padelpoint-api

# Check status
sudo systemctl status padelpoint-scheduler
sudo systemctl status padelpoint-api
sudo journalctl -u padelpoint-api -f
```

### 7. Nginx reverse proxy (optional)

```bash
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/padelpoint << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/padelpoint /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

For HTTPS add certbot:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Daily Operations

### Scheduling (2x daily)

The built-in scheduler (`python run.py scheduler`) runs:
- Quick price/stock updates at 08:00 and 20:00
- Full scrape on Sundays at 03:00

Alternatively, use cron:
```cron
0 8 * * *   cd /opt/pp_parser && .venv/bin/python run.py scrape quick >> data/logs/cron.log 2>&1
0 20 * * *  cd /opt/pp_parser && .venv/bin/python run.py scrape quick >> data/logs/cron.log 2>&1
0 3 * * 0   cd /opt/pp_parser && .venv/bin/python run.py scrape full >> data/logs/cron.log 2>&1
```

### 2Captcha Setup

A 2Captcha API key enables fully automated headless login (no display needed).

1. Register at [2captcha.com](https://2captcha.com) and add funds (~$3 for 1000 solves)
2. Copy your API key from the dashboard
3. Set `TWOCAPTCHA_API_KEY` in `.env`

Without a key, login falls back to manual mode (requires a browser window).

---

## API Access

Docs: `http://<your-server>:8000/docs`

### Example Requests

```bash
# Stats overview
curl http://localhost:8000/api/v1/stats

# Products (filtered, paginated)
curl "http://localhost:8000/api/v1/products/?category_id=3&brand_name=Nox&in_stock=true&page=1&page_size=50"

# Single product
curl http://localhost:8000/api/v1/products/42

# Category tree
curl http://localhost:8000/api/v1/categories/tree

# Latest prices (bulk)
curl "http://localhost:8000/api/v1/prices/latest?in_stock_only=true"

# Price history
curl http://localhost:8000/api/v1/prices/history/42

# Export to Excel
python run.py export --output catalog.xlsx
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/stats` | Overall statistics |
| GET | `/api/v1/categories/` | List top-level categories |
| GET | `/api/v1/categories/tree` | Full category tree |
| GET | `/api/v1/categories/{id}` | Single category |
| GET | `/api/v1/products/` | List products (filters, pagination) |
| GET | `/api/v1/products/{id}` | Full product detail |
| GET | `/api/v1/products/by-external/{ext_id}` | Product by site ID |
| GET | `/api/v1/brands/` | List brands |
| GET | `/api/v1/prices/history/{product_id}` | Price history |
| GET | `/api/v1/prices/latest` | Bulk latest prices |
| GET | `/health` | Health check |

Products return `categories` as an array (a product can belong to multiple categories).

---

## Session & Cookie Management

### How Authentication Works

1. `python run.py auth login` tries 2Captcha auto-login first (headless)
2. If that fails — opens a headed browser for manual CAPTCHA
3. Cookies are saved to `data/cookies.json`
4. The scraper reuses cookies until they expire
5. When expired, authenticated scraping is skipped (guest scraping continues)

### Commands

```bash
python run.py auth login          # auto-login (2Captcha → manual fallback)
python run.py auth interactive    # force manual login
python run.py auth check          # check if session is valid
```

On a headless VPS without 2Captcha, use X11 forwarding:
```bash
ssh -X user@server
cd /opt/pp_parser && .venv/bin/python run.py auth interactive
```

---

## Database Management

### Reset and rebuild

```bash
# Drop and recreate all tables
sudo -u postgres psql -c "DROP DATABASE padelpoint;"
sudo -u postgres psql -c "CREATE DATABASE padelpoint OWNER padelpoint;"

# Recreate tables and scrape
cd /opt/pp_parser && source .venv/bin/activate
python -m scraper.categories
python -m scraper.products
python run.py scrape full
```

### Backup

```bash
pg_dump -U padelpoint -h localhost padelpoint > backup_$(date +%Y%m%d).sql
```

### Restore

```bash
psql -U padelpoint -h localhost padelpoint < backup_20260224.sql
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `playwright install` fails | `playwright install-deps` (installs system libs) |
| Cloudflare blocks requests | Increase `REQUEST_DELAY` in `.env` |
| Session expired | `python run.py auth login` |
| 2Captcha fails | Check API key and balance at 2captcha.com |
| Empty prices | datalayerDataGMT format may have changed on site |
| Missing images | Images extracted from datalayer + HTML fallback |
| Cannot connect to DB | Check `DATABASE_URL` in `.env`, verify `pg_isready` |
| Permission denied | `sudo chown -R www-data:www-data /opt/pp_parser/data` |
| Service won't start | `sudo journalctl -u padelpoint-api -n 50` for logs |
| Schema changed | Drop and recreate DB (see Database Management above) |
