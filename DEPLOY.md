# ChemEduTech — Ubuntu 24.04 серверіне деплой

Docker-сіз: **PostgreSQL + Gunicorn (systemd) + Nginx + Let's Encrypt**, қосымша **db_worker** (AI бағалау,
сертификат PDF). Құрылымы DigitalOcean-ның «How To Set Up Django with Postgres, Nginx, and Gunicorn on Ubuntu»
нұсқаулығына сәйкес, ChemEduTech-ке және **бірнеше сайт тұрған серверге** бейімделген.

**Келісім:**
- Командаларды **root** орындайды (`sudo` керек емес).
- Жоба: **`/var/www/chemedutech`** (басқа сайттар сияқты `/var/www/` ішінде).
- Сайттың өзі (Gunicorn, жұмысшы) **`www-data`** атынан жұмыс істейді — root атынан емес: веб-процесс бұзылса,
  басқа сайттар мен бүкіл сервер қорғалып қалады.
- Барлық атау бірегей (`chemedutech.service`, `/run/chemedutech.sock`, `sites-available/chemedutech`, база
  `chemedutech`) — серверде бар сайттарға тимейді.

Алмастырылатын мәндер:

| Белгі | Мағынасы | Мысал |
|---|---|---|
| `chem.example.kz` | осы сайттың домені | `chemedutech.kz` |
| `DB_PASSWORD` | PostgreSQL құпиясөзі | ұзын кездейсоқ жол |

---

## 1. Жүйелік пакеттер

Бар пакеттер қайта орнатылмайды, жетіспегені ғана қосылады:

```bash
apt update
apt install -y python3-venv python3-dev build-essential git curl \
    postgresql postgresql-contrib nginx \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    fonts-dejavu-core gettext
```

- Ubuntu 24.04-те Python 3.12 бар — Django 6 үшін жеткілікті (`python3 --version`).
- `libpango…`, `libharfbuzz-subset0` — WeasyPrint (сертификат PDF); `fonts-dejavu-core` — PDF-тегі қазақ әріптері.
- `gettext` — тек аудармаларды серверде қайта жинау керек болса (`.mo` файлдары репода бар).

## 2. PostgreSQL — жеке база мен пайдаланушы

Басқа сайттардың базаларына тимейді:

```bash
sudo -u postgres psql
```
```sql
CREATE USER chemedutech WITH PASSWORD 'DB_PASSWORD';
CREATE DATABASE chemedutech OWNER chemedutech;
ALTER ROLE chemedutech SET client_encoding TO 'utf8';
ALTER ROLE chemedutech SET default_transaction_isolation TO 'read committed';
ALTER ROLE chemedutech SET timezone TO 'UTC';
\q
```

`OWNER` маңызды: PostgreSQL 15+ `public` схемасына иесінен басқаға кесте құруға рұқсат бермейді.

## 3. Код және виртуалды орта

```bash
cd /var/www
git clone https://github.com/mukhagaliaryn/chemedutech.git
cd /var/www/chemedutech
python3 -m venv env
env/bin/pip install --upgrade pip
env/bin/pip install -r requirements.txt
```

Репозиторий жабық (private) болса: `ssh-keygen -t ed25519` → `/root/.ssh/id_ed25519.pub` мазмұнын GitHub-та
репоның **Settings → Deploy keys** бөліміне қосып, `git clone git@github.com:mukhagaliaryn/chemedutech.git`.

## 4. `.env` — сайттың баптаулары

```bash
cd /var/www/chemedutech
cp .env.example .env
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
POSTGRES_USER=chemedutech
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

```bash
chown root:www-data .env && chmod 640 .env     # www-data оқиды, басқалар көрмейді
```

- `DJANGO_SETTINGS_MODULE=config.settings.prod` — `manage.py` оны `.env`-тен оқиды, сондықтан барлық команда
  prod баптауларымен орындалады.
- Домен әлі жоқ болса: `DJANGO_ALLOWED_HOSTS=<сервер IP>`, `SITE_URL=http://<IP>` және уақытша
  `DJANGO_SECURE_SSL_REDIRECT=0`, `DJANGO_SECURE_COOKIES=0` (HTTPS-сіз кіру үшін). HTTPS қосылған соң бұл
  екеуін **міндетті түрде алып тастаңыз**. Ескерту: IP-дің 80-порты басқа сайттың `default_server`-іне
  түсуі мүмкін — сондықтан доменмен тексерген дұрыс.
- `DJANGO_SECURE_HSTS_SECONDS` — HTTPS бір-екі апта тұрақты жұмыс істегеннен кейін ғана (`31536000`).

## 5. Дерекқор, статика, медиа, әкімші

```bash
cd /var/www/chemedutech
env/bin/python manage.py migrate
env/bin/python manage.py collectstatic --noinput
env/bin/python manage.py createsuperuser          # admin рөлі автоматты беріледі
env/bin/python manage.py check --deploy           # HSTS туралы 2 ескерту қалыпты

mkdir -p media
chown -R www-data:www-data media                  # жүктелген файлдарды сайт жазады
```

- Статика хэштелген атаулармен жиналады (`styles.7db4….css`) — жаңартудан кейін браузер ескі файлды алмайды.
- Демо курс керек болса: `env/bin/python manage.py seed_course` (1-тақырып толық).
- Код пен `staticfiles/` root-қа тиесілі болып қалады — `www-data` оларды тек оқиды (`/var/www`-те әдепкі
  бойынша оқуға рұқсат бар).

## 6. Gunicorn-ды қолмен тексеру (міндетті емес)

Басқа сайттармен соқтығыспайтын бос порт (мысалы 8765):

```bash
cd /var/www/chemedutech
sudo -u www-data env/bin/gunicorn --bind 127.0.0.1:8765 config.wsgi &
curl -sI http://127.0.0.1:8765/ -H "Host: chem.example.kz" | head -3      # 200 немесе 301 (HTTPS-ке)
kill %1
```

## 7. systemd: Gunicorn сокеті және қызметі

`nano /etc/systemd/system/chemedutech.socket`
```ini
[Unit]
Description=ChemEduTech gunicorn socket

[Socket]
ListenStream=/run/chemedutech.sock
SocketUser=www-data

[Install]
WantedBy=sockets.target
```

`nano /etc/systemd/system/chemedutech.service`
```ini
[Unit]
Description=ChemEduTech gunicorn
Requires=chemedutech.socket
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/chemedutech
ExecStart=/var/www/chemedutech/env/bin/gunicorn \
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
systemctl daemon-reload
systemctl enable --now chemedutech.socket
systemctl status chemedutech.socket
curl --unix-socket /run/chemedutech.sock -H "Host: chem.example.kz" localhost -I   # жауап келуі керек
systemctl status chemedutech
```

`--workers` ≈ 2 × CPU + 1, бірақ серверде басқа сайттар барын ескеріңіз (`nproc`, `free -h`): 2 ядро мен
бірнеше сайт болса — 3 жеткілікті.

## 8. systemd: фондық жұмысшы (AI бағалау, сертификат PDF)

`nano /etc/systemd/system/chemedutech-worker.service`
```ini
[Unit]
Description=ChemEduTech background worker (db_worker)
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/chemedutech
ExecStart=/var/www/chemedutech/env/bin/python manage.py db_worker --no-reload --interval 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now chemedutech-worker
systemctl status chemedutech-worker
```

Жұмысшы тоқтап тұрса, практиканың ашық жауаптары «бағалануда» күйінде қалады, сертификат PDF жасалмайды.

## 9. Nginx — жеке server блогы

Бар сайттардың конфигтеріне және `default`-қа **тимейміз**, тек жаңа файл қосамыз.

`nano /etc/nginx/sites-available/chemedutech`
```nginx
server {
    listen 80;
    server_name chem.example.kz;

    client_max_body_size 200M;          # видео және практика файлдарын жүктеу

    access_log /var/log/nginx/chemedutech.access.log;
    error_log  /var/log/nginx/chemedutech.error.log;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /var/www/chemedutech/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Сертификат PDF-і тек рұқсатпен: /certificates/<uuid>/pdf/ арқылы (Django береді)
    location /media/certificates/pdf/ { return 404; }

    location /media/ {
        alias /var/www/chemedutech/media/;
    }

    location / {
        include proxy_params;           # Host, X-Forwarded-For, X-Forwarded-Proto
        proxy_pass http://unix:/run/chemedutech.sock;
        proxy_read_timeout 90s;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/chemedutech /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx          # reload: басқа сайттар үзілмейді
```

`ufw` қосулы болса, 80/443 басқа сайттар үшін ашық тұрғаны тексеріледі: `ufw status` (`Nginx Full`).

## 10. HTTPS (Let's Encrypt)

Доменнің A жазбасы осы сервердің IP-іне қаралғаннан кейін:

```bash
apt install -y certbot python3-certbot-nginx     # бар болса өткізіп жіберіледі
certbot --nginx -d chem.example.kz               # тек осы доменнің блогы өзгереді
certbot renew --dry-run
```

Содан кейін `.env`-те `SITE_URL=https://…`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://…`; уақытша
`DJANGO_SECURE_SSL_REDIRECT=0` / `DJANGO_SECURE_COOKIES=0` болса — алып тастап, қайта іске қосу:

```bash
systemctl restart chemedutech chemedutech-worker
```

## 11. Сақтық көшірме (зерттеу деректері!)

`LabEvent`, `QuizAttempt`, `AttemptAnswer`, AI бағалары — диссертацияның эксперимент бөлімінің негізі.
Күн сайын көшірме алыңыз және **көшірмені сервер сыртына** (өз компьютеріңізге/бұлтқа) жүктеп отырыңыз.

`nano /usr/local/bin/chemedutech-backup`
```bash
#!/bin/bash
set -euo pipefail
DIR=/var/backups/chemedutech
mkdir -p "$DIR"
STAMP=$(date +%F)
sudo -u postgres pg_dump -Fc chemedutech > "$DIR/db-$STAMP.dump"
tar -czf "$DIR/media-$STAMP.tar.gz" -C /var/www/chemedutech media
find "$DIR" -type f -mtime +14 -delete      # 14 күннен ескісін өшіру
```

```bash
chmod 700 /usr/local/bin/chemedutech-backup
/usr/local/bin/chemedutech-backup && ls -lh /var/backups/chemedutech     # бір рет қолмен тексеру
crontab -e
```
```cron
30 3 * * * /usr/local/bin/chemedutech-backup
0 4 * * 0 cd /var/www/chemedutech && sudo -u www-data env/bin/python manage.py prune_db_task_results
```

Өз компьютеріңізге көшіру: `scp root@chem.example.kz:/var/backups/chemedutech/db-YYYY-MM-DD.dump .`
Қалпына келтіру:
`sudo -u postgres pg_restore --clean --if-exists -d chemedutech db-YYYY-MM-DD.dump`.

## 12. Жаңарту (жаңа нұсқаны шығару)

```bash
cd /var/www/chemedutech
/usr/local/bin/chemedutech-backup             # алдымен көшірме
git pull
env/bin/pip install -r requirements.txt
env/bin/python manage.py migrate
env/bin/python manage.py collectstatic --noinput
systemctl restart chemedutech chemedutech-worker
```

- CSS (`ui/static/css/dist/styles.css`) пен аудармалар (`.mo`) репода жиналған күйде келеді — серверге Node.js
  керек емес. Жергілікті компьютерде: `python manage.py tailwind build` және `compilemessages`, содан кейін
  commit + push.
- Зерттеу деректерін өзгертетін миграция болса — алдын ала жоспар келісіледі (CLAUDE.md).
- `manage.py shell` арқылы файл жасасаңыз (мысалы медиа), кейін `chown -R www-data:www-data media`.

## 13. Ақаулар

```bash
journalctl -u chemedutech -n 100 --no-pager          # Django/Gunicorn қателері
journalctl -u chemedutech-worker -n 100 --no-pager   # AI бағалау, PDF
tail -n 50 /var/log/nginx/chemedutech.error.log
systemctl restart chemedutech
```

| Белгі | Себебі |
|---|---|
| 502 Bad Gateway | Gunicorn қызметі тоқтаған немесе `/run/chemedutech.sock` жоқ → `journalctl -u chemedutech` |
| Басқа сайт ашылады | `server_name` дұрыс емес немесе DNS әлі осы серверге қаралмаған |
| Статика 404 | `collectstatic` орындалмаған немесе `alias` жолы қате |
| Файл жүктегенде 500 / Permission denied | `chown -R www-data:www-data /var/www/chemedutech/media` |
| Қызмет іске қоспайды: `.env` оқылмайды | `chown root:www-data .env && chmod 640 .env` |
| Кіргеннен кейін қайтадан кіру беті | HTTPS жоқ, ал `DJANGO_SECURE_COOKIES` қосулы (§4) |
| CSRF verification failed | `DJANGO_CSRF_TRUSTED_ORIGINS` дұрыс емес (схемасымен: `https://…`) |
| 400 Bad Request | `DJANGO_ALLOWED_HOSTS`-та домен/IP жоқ |
| Ашық жауаптар бағаланбайды | `chemedutech-worker` тоқтаған, `AI_GRADING_ENABLED=0` немесе API кілті жоқ |
| YouTube «Видео недоступно» | Nginx `Referrer-Policy`-ды қайта жазбауы керек (Django `strict-origin-when-cross-origin` береді) |
| Сертификат PDF-інде шаршылар | қаріп жоқ: `apt install fonts-dejavu-core` |

## 14. Іске қосқаннан кейінгі тексеріс

- [ ] `https://chem.example.kz` ашылады, тіл — қазақша, стильдер орнында; басқа сайттар бұрынғыдай жұмыс істейді.
- [ ] `/admin/` — кіру; университет → факультет → кафедра → топ, мұғалім.
- [ ] Студент тіркелуі → курсқа жазылу → теория, видео, зертхана (оқиғалар жазылады), практика, тест.
- [ ] Құпиясөзді қалпына келтіру хаты келеді.
- [ ] Практиканың ашық жауабы (AI қосулы болса) бағаланады.
- [ ] Курсты аяқтағанда сертификат PDF жүктеледі, QR-код `SITE_URL`-ге апарады.
- [ ] `/usr/local/bin/chemedutech-backup` іске қосылып, `/var/backups/chemedutech/` ішінде файлдар пайда болды.
