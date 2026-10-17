# ChemEduTech — Ubuntu 24.04 серверіне деплой

Docker-сіз: **PostgreSQL + Gunicorn (systemd) + Nginx + Let's Encrypt**, қосымша **db_worker** (AI бағалау,
сертификат PDF). Құрылымы DigitalOcean-ның «How To Set Up Django with Postgres, Nginx, and Gunicorn on Ubuntu»
нұсқаулығына сәйкес, ChemEduTech-ке тән қадамдар қосылған.

Төменде алмастырылатын мәндер:

| Белгі | Мағынасы | Мысал |
|---|---|---|
| `chem` | серверде жоба жұмыс істейтін (sudo құқылы, root емес) пайдаланушы | `chem` |
| `chem.example.kz` | домен | `chemedutech.kz` |
| `/home/chem/chemedutech` | жоба бумасы | — |
| `DB_PASSWORD` | PostgreSQL құпиясөзі | ұзын кездейсоқ жол |

> Барлық команда `chem` пайдаланушысынан орындалады (`sudo` қажет жерде көрсетілген).

---

## 1. Жүйелік пакеттер

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-dev build-essential git curl \
    postgresql postgresql-contrib nginx \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    fonts-dejavu-core gettext
```

- Ubuntu 24.04-те Python 3.12 бар — Django 6 үшін жеткілікті.
- `libpango…`, `libharfbuzz-subset0` — WeasyPrint (сертификат PDF); `fonts-dejavu-core` — PDF-тегі қазақ әріптері.
- `gettext` — тек аудармаларды серверде қайта жинау керек болса (`.mo` файлдары репода бар).

## 2. PostgreSQL

```bash
sudo -u postgres psql
```
```sql
CREATE DATABASE chemedutech;
CREATE USER chem WITH PASSWORD 'DB_PASSWORD';
ALTER ROLE chem SET client_encoding TO 'utf8';
ALTER ROLE chem SET default_transaction_isolation TO 'read committed';
ALTER ROLE chem SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE chemedutech TO chem;
ALTER DATABASE chemedutech OWNER TO chem;
\q
```

`OWNER` маңызды: PostgreSQL 15+ `public` схемасына басқа пайдаланушыға кесте құруға рұқсат бермейді.

## 3. Код және виртуалды орта

```bash
cd ~
git clone https://github.com/mukhagaliaryn/chemedutech.git
cd chemedutech
python3 -m venv env
env/bin/pip install --upgrade pip
env/bin/pip install -r requirements.txt
```

Репозиторий жабық (private) болса — серверде SSH кілтін жасап (`ssh-keygen -t ed25519`), GitHub-қа
**Deploy key** ретінде қосып, `git clone git@github.com:mukhagaliaryn/chemedutech.git` қолданыңыз.

## 4. `.env` — сервер баптаулары

```bash
cp .env.example .env
chmod 600 .env
env/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY үшін
nano .env
```

```ini
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<жоғарыдағы кездейсоқ жол>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=chem.example.kz
DJANGO_CSRF_TRUSTED_ORIGINS=https://chem.example.kz
SITE_URL=https://chem.example.kz

POSTGRES_DB=chemedutech
POSTGRES_USER=chem
POSTGRES_PASSWORD=DB_PASSWORD
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# AI бағалау (кілт болмаса 0 — ашық жауаптар мұғалім кезегіне түседі)
ANTHROPIC_API_KEY=
AI_GRADING_ENABLED=0
AI_GRADING_MODEL=claude-sonnet-5-5

# Құпиясөзді қалпына келтіру хаттары (мысал: Gmail, app password)
DJANGO_EMAIL_HOST=smtp.gmail.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_USE_TLS=1
DJANGO_EMAIL_HOST_USER=example@gmail.com
DJANGO_EMAIL_HOST_PASSWORD=<app password>
DJANGO_DEFAULT_FROM_EMAIL=ChemEduTech <example@gmail.com>
```

- `DJANGO_SETTINGS_MODULE=config.settings.prod` — `manage.py` оны `.env`-тен оқиды, сондықтан серверде барлық
  команда prod баптауларымен орындалады.
- Домен әлі жоқ болса: `DJANGO_ALLOWED_HOSTS=<сервер IP>`, `SITE_URL=http://<IP>` және уақытша
  `DJANGO_SECURE_SSL_REDIRECT=0`, `DJANGO_SECURE_COOKIES=0` (HTTPS-сіз кіру үшін). HTTPS қосылған соң бұл
  екеуін **міндетті түрде алып тастаңыз**.
- `DJANGO_SECURE_HSTS_SECONDS` — HTTPS бір-екі апта тұрақты жұмыс істегеннен кейін ғана (`31536000`).

## 5. Дерекқор, статика, әкімші

```bash
env/bin/python manage.py migrate
env/bin/python manage.py collectstatic --noinput
env/bin/python manage.py createsuperuser          # admin рөлі автоматты беріледі
env/bin/python manage.py check --deploy           # HSTS туралы 2 ескерту қалыпты
```

- Статика хэштелген атаулармен жиналады (`styles.7db4….css`) — жаңартудан кейін браузер ескі файлды алмайды.
- Демо курс керек болса: `env/bin/python manage.py seed_course` (1-тақырып толық, қалғаны бос жоба).

## 6. Gunicorn-ды қолмен тексеру

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8000
sudo ufw enable
env/bin/gunicorn --bind 0.0.0.0:8000 config.wsgi
```

Браузерде `http://<IP>:8000` — бет стильсіз ашылады (статиканы Nginx береді), бұл қалыпты. `Ctrl+C`, содан
кейін `sudo ufw delete allow 8000`.

## 7. systemd: Gunicorn сокеті және қызметі

`sudo nano /etc/systemd/system/chemedutech.socket`
```ini
[Unit]
Description=ChemEduTech gunicorn socket

[Socket]
ListenStream=/run/chemedutech.sock

[Install]
WantedBy=sockets.target
```

`sudo nano /etc/systemd/system/chemedutech.service`
```ini
[Unit]
Description=ChemEduTech gunicorn
Requires=chemedutech.socket
After=network.target postgresql.service

[Service]
User=chem
Group=www-data
WorkingDirectory=/home/chem/chemedutech
ExecStart=/home/chem/chemedutech/env/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --timeout 60 \
          --bind unix:/run/chemedutech.sock \
          config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now chemedutech.socket
sudo systemctl status chemedutech.socket
curl --unix-socket /run/chemedutech.sock localhost     # HTML қайтуы керек (алғашқы сұрау қызметті оятады)
sudo systemctl status chemedutech
```

`--workers` ≈ 2 × CPU + 1 (1 ядро → 3).

## 8. systemd: фондық жұмысшы (AI бағалау, сертификат PDF)

`sudo nano /etc/systemd/system/chemedutech-worker.service`
```ini
[Unit]
Description=ChemEduTech background worker (db_worker)
After=network.target postgresql.service

[Service]
User=chem
Group=www-data
WorkingDirectory=/home/chem/chemedutech
ExecStart=/home/chem/chemedutech/env/bin/python manage.py db_worker --no-reload --interval 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now chemedutech-worker
sudo systemctl status chemedutech-worker
```

Жұмысшы тоқтап тұрса, практиканың ашық жауаптары «бағалануда» күйінде қалады, сертификат PDF жасалмайды.

## 9. Nginx

`sudo nano /etc/nginx/sites-available/chemedutech`
```nginx
server {
    listen 80;
    server_name chem.example.kz;

    client_max_body_size 200M;          # видео және практика файлдарын жүктеу

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /home/chem/chemedutech/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Сертификат PDF-і тек рұқсатпен: /certificates/<uuid>/pdf/ арқылы (Django береді)
    location /media/certificates/pdf/ { return 404; }

    location /media/ {
        alias /home/chem/chemedutech/media/;
    }

    location / {
        include proxy_params;           # Host, X-Forwarded-For, X-Forwarded-Proto
        proxy_pass http://unix:/run/chemedutech.sock;
        proxy_read_timeout 90s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/chemedutech /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
mkdir -p ~/chemedutech/media
chmod o+x /home/chem                    # Nginx (www-data) статика мен медиаға жете алуы үшін
sudo nginx -t && sudo systemctl restart nginx
sudo ufw allow 'Nginx Full'
```

## 10. HTTPS (Let's Encrypt)

Доменнің A жазбасы сервер IP-іне қаралғаннан кейін:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d chem.example.kz
sudo certbot renew --dry-run
```

Содан кейін `.env`-те `SITE_URL=https://…`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://…`; уақытша
`DJANGO_SECURE_SSL_REDIRECT=0` / `DJANGO_SECURE_COOKIES=0` болса — алып тастап, қайта іске қосу:

```bash
sudo systemctl restart chemedutech chemedutech-worker
```

## 11. Сақтық көшірме (зерттеу деректері!)

`LabEvent`, `QuizAttempt`, `AttemptAnswer`, AI бағалары — диссертацияның эксперимент бөлімінің негізі.
Күн сайын көшірме алыңыз және **көшірмені сервер сыртына** (өз компьютеріңізге/бұлтқа) жүктеп отырыңыз.

`nano ~/backup.sh`
```bash
#!/bin/bash
set -euo pipefail
DIR=/home/chem/backups
mkdir -p "$DIR"
STAMP=$(date +%F)
pg_dump -Fc -h localhost -U chem chemedutech > "$DIR/db-$STAMP.dump"
tar -czf "$DIR/media-$STAMP.tar.gz" -C /home/chem/chemedutech media
find "$DIR" -type f -mtime +14 -delete      # 14 күннен ескісін өшіру
```

```bash
chmod +x ~/backup.sh
echo "localhost:5432:chemedutech:chem:DB_PASSWORD" > ~/.pgpass && chmod 600 ~/.pgpass
crontab -e
```
```cron
30 3 * * * /home/chem/backup.sh
0 4 * * 0 cd /home/chem/chemedutech && env/bin/python manage.py prune_db_task_results
```

Өз компьютеріңізге көшіру: `scp chem@chem.example.kz:backups/db-YYYY-MM-DD.dump .`
Қалпына келтіру: `pg_restore --clean --if-exists -h localhost -U chem -d chemedutech db-YYYY-MM-DD.dump`.

## 12. Жаңарту (жаңа нұсқаны шығару)

```bash
cd ~/chemedutech
~/backup.sh                                   # алдымен көшірме
git pull
env/bin/pip install -r requirements.txt
env/bin/python manage.py migrate
env/bin/python manage.py collectstatic --noinput
sudo systemctl restart chemedutech chemedutech-worker
```

- CSS (`ui/static/css/dist/styles.css`) пен аудармалар (`.mo`) репода жиналған күйде келеді — серверге Node.js
  керек емес. Жергілікті компьютерде: `python manage.py tailwind build` және `compilemessages`, содан кейін commit.
- Зерттеу деректерін өзгертетін миграция болса — алдын ала жоспар келісіледі (CLAUDE.md).

## 13. Ақаулар

```bash
sudo journalctl -u chemedutech -n 100 --no-pager          # Django/Gunicorn қателері
sudo journalctl -u chemedutech-worker -n 100 --no-pager   # AI бағалау, PDF
sudo tail -n 50 /var/log/nginx/error.log
sudo systemctl restart chemedutech
```

| Белгі | Себебі |
|---|---|
| 502 Bad Gateway | Gunicorn қызметі тоқтаған немесе `/run/chemedutech.sock` жоқ → `journalctl -u chemedutech` |
| Статика 403/404 | `collectstatic` орындалмаған немесе `chmod o+x /home/chem` жасалмаған |
| Кіргеннен кейін қайтадан кіру беті | HTTPS жоқ, ал `DJANGO_SECURE_COOKIES` қосулы (§4) |
| CSRF verification failed | `DJANGO_CSRF_TRUSTED_ORIGINS` дұрыс емес (схемасымен: `https://…`) |
| 400 Bad Request | `DJANGO_ALLOWED_HOSTS`-та домен/IP жоқ |
| Ашық жауаптар бағаланбайды | `chemedutech-worker` тоқтаған, `AI_GRADING_ENABLED=0` немесе API кілті жоқ |
| YouTube «Видео недоступно» | Nginx `Referrer-Policy`-ды қайта жазбауы керек (Django `strict-origin-when-cross-origin` береді) |
| Сертификат PDF-інде шаршылар | қаріп жоқ: `sudo apt install fonts-dejavu-core` |

## 14. Іске қосқаннан кейінгі тексеріс

- [ ] `https://chem.example.kz` ашылады, тіл — қазақша, стильдер орнында.
- [ ] `/admin/` — кіру; университет → факультет → кафедра → топ, мұғалім.
- [ ] Студент тіркелуі → курсқа жазылу → теория, видео, зертхана (оқиғалар жазылады), практика, тест.
- [ ] Құпиясөзді қалпына келтіру хаты келеді.
- [ ] Практиканың ашық жауабы (AI қосулы болса) бағаланады.
- [ ] Курсты аяқтағанда сертификат PDF жүктеледі, QR-код `SITE_URL`-ге апарады.
- [ ] `~/backup.sh` қолмен іске қосылып, `~/backups/` ішінде файлдар пайда болды.
