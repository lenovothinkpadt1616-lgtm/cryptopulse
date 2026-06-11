# CryptoPulse — крипто-новостной сайт

Тёмный новостной сайт с разделами, автопарсингом, курсами криптовалют и Telegram-ботом.

## Возможности

| Функция | Описание |
|---------|----------|
| **Разделы** | Криптовалюты, Финансы, Жизнь |
| **Автопарсинг** | ForkLog, Bits.media, Ведомости, РИА, Lenta — каждые 2 часа |
| **Курсы** | BTC, ETH, USDT, TON, BNB + USD/RUB (CoinGecko + ЦБ) |
| **Telegram-бот** | Пост в любой раздел + своя дата |
| **Реклама** | Блок oren-change.com в сайдбаре и в статьях |
| **Без авторизации** | Только чтение, никаких лайков |

---

## Быстрый запуск (локально)

### 1. Установка

```bash
cd Desktop\novosti
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### 2. Настрой `.env`

```env
SITE_NAME=CryptoPulse
TELEGRAM_BOT_TOKEN=...     # от @BotFather
ADMIN_USER_IDS=123456789,987654321   # ID админов через запятую (от @userinfobot). Можно одного или нескольких.
SITE_URL=http://localhost:5000
```

### 3. Запуск

```bash
python run.py
```

Открой: **http://localhost:5000**

При старте сразу парсятся все источники, потом — каждые 2 часа.

---

## Telegram-бот

Только для админов из `ADMIN_USER_IDS` (один или несколько ID через запятую).

| Команда | Действие |
|---------|----------|
| `/post` | Своя новость в любой раздел: крипто / финансы / жизнь → заголовок → текст → фото → дата |
| `/delete 42` | Удалить новость #42 |
| `/parse` | Спарсить все источники вручную |
| `/list` | Последние 15 новостей с ID |
| `/stats` | Статистика по разделам |
| `/cancel` | Отмена |

### Публикация своей новости

```
/post
→ выбери раздел (кнопки)
→ заголовок
→ текст
→ фото или /skip
→ дата: 10.06.2026 14:30  или  /now
```

---

## Разделы и источники

| Раздел | URL | Источники |
|--------|-----|-----------|
| Криптовалюты | `/crypto` | ForkLog, Bits.media + свои посты |
| Финансы | `/finance` | Ведомости + свои посты |
| Жизнь | `/life` | РИА, Lenta.ru + свои посты |

Свои новости через `/post` в боте — выбираешь любой из трёх разделов кнопкой.

Источники настраиваются в `config.py` → `RSS_SOURCES`.

---

## Деплой на VPS с доменом

### Что нужно

- VPS (Ubuntu 22.04+, от 1 GB RAM)
- Домен (например `cryptopulse.ru`)
- SSH-доступ

### Шаг 1 — Подготовка сервера

```bash
ssh root@YOUR_SERVER_IP

apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

### Шаг 2 — Загрузка проекта

```bash
mkdir -p /opt/cryptopulse
# Скопируй папку novosti на сервер (scp, git, или вручную):

# С локального ПК (PowerShell):
scp -r C:\Users\lenov\Desktop\novosti root@YOUR_SERVER_IP:/opt/cryptopulse
```

Или через git:
```bash
cd /opt/cryptopulse
git clone YOUR_REPO .
```

### Шаг 3 — Python-окружение

```bash
cd /opt/cryptopulse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

В `.env` на сервере:
```env
SITE_NAME=CryptoPulse
SITE_URL=https://твой-домен.ru
TELEGRAM_BOT_TOKEN=...
ADMIN_USER_IDS=123456789,987654321   # один или несколько через запятую
SECRET_KEY=длинная-случайная-строка-32-символа
HOST=0.0.0.0
PORT=5000
PARSE_INTERVAL_MINUTES=120
```

### Шаг 4 — Systemd (автозапуск)

```bash
cp deploy/cryptopulse.service /etc/systemd/system/
# Отредактируй User если нужно:
nano /etc/systemd/system/cryptopulse.service

systemctl daemon-reload
systemctl enable cryptopulse
systemctl start cryptopulse
systemctl status cryptopulse
```

Логи: `journalctl -u cryptopulse -f`

### Шаг 5 — Домен → DNS

В панели регистратора домена добавь A-запись:

```
Тип: A
Имя: @
Значение: IP_ТВОЕГО_VPS
TTL: 300

Тип: A
Имя: www
Значение: IP_ТВОЕГО_VPS
```

Подожди 5–30 минут пока DNS обновится.

### Шаг 6 — Nginx

```bash
cp deploy/nginx.conf /etc/nginx/sites-available/cryptopulse
nano /etc/nginx/sites-available/cryptopulse
# Замени YOUR_DOMAIN на твой домен

ln -s /etc/nginx/sites-available/cryptopulse /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

### Шаг 7 — SSL (HTTPS)

```bash
certbot --nginx -d твой-домен.ru -d www.твой-домен.ru
```

Certbot сам настроит HTTPS и автообновление сертификата.

### Шаг 8 — Проверка

```bash
curl https://твой-домен.ru/health
# {"status":"ok","articles":...}
```

Сайт работает: **https://твой-домен.ru**

---

## Обновление на сервере

```bash
cd /opt/cryptopulse
source venv/bin/activate
# загрузи новые файлы
pip install -r requirements.txt
systemctl restart cryptopulse
```

---

## Структура проекта

```
novosti/
├── run.py              # Запуск всего
├── app.py              # Flask-сайт
├── parser.py           # Парсер RSS
├── rates.py            # Курсы крипты
├── telegram_bot.py     # TG-бот
├── database.py         # SQLite
├── config.py           # Настройки + разделы
├── templates/          # HTML
├── static/css/         # Стили
├── deploy/             # nginx + systemd
└── data/news.db        # База
```

---

## Настройка

| Что | Где |
|-----|-----|
| Название сайта | `.env` → `SITE_NAME` |
| Реклама | `.env` → `AD_URL`, `AD_TEXT` |
| Интервал парсинга | `.env` → `PARSE_INTERVAL_MINUTES` (120 = 2 часа) |
| RSS-источники | `config.py` → `RSS_SOURCES` |
| Дизайн/цвета | `static/css/style.css` → `:root` |
| Разделы | `config.py` → `SECTIONS` |