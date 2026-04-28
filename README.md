# Memboard v7

A Django-based shared memory-keeping app with rich social features, PWA support, and Cloudflare R2 photo storage.

---

## ✨ What's new in v7

| Feature | Details |
|---|---|
| **Reactions** | 6 emoji reactions on memories (❤️😂😮😢🔥🎉), toggle on/off, live counts |
| **Comments** | Per-memory comment threads, loaded on demand |
| **Memory dates** | Record when a memory actually happened |
| **Board cover photo** | Upload a cover image per board (owner only) |
| **Pin a memory** | Pin memories to the top of a board |
| **Search** | Full-text search across all your boards and memories |
| **Notifications** | In-app notifications for reactions, comments, tags, friend requests |
| **Password reset** | Email-based password reset via Django's built-in flow |
| **Cloudflare R2** | All user-uploaded photos stored in R2 (toggle via env var) |
| **Annual recap** | Year-in-review page with stats, charts, top boards |
| **Memory locations** | Geocoded location field with OpenStreetMap autocomplete |
| **Map pins** | Leaflet map tab on each board showing geolocated memories |
| **Activity log** | Per-board feed of all actions (add, edit, delete, pin, comment…) |
| **Weekly digest** | Management command to email a weekly memory digest |
| **PWA** | manifest.json, service worker with offline caching, push notification skeleton |

---

## 🚀 Getting started

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a `.env` file

```env
SECRET_KEY=your-secret-key-here
DEBUG=True

# Database (leave blank for SQLite)
DATABASE_URL=

# Email (Gmail)
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# App base URL (for emails and links)
APP_URL=https://your-app.com

# Cloudflare R2 (set USE_R2=True to enable)
USE_R2=False
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
R2_PUBLIC_DOMAIN=media.yourdomain.com    # optional custom domain
```

### 3. Migrate and run

```bash
python manage.py migrate
python manage.py createsuperuser  # optional
python manage.py runserver
```

---

## ☁️ Cloudflare R2 Setup

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Go to **R2 Object Storage** → **Create bucket**
3. Go to **R2 → Manage R2 API tokens** → **Create API token**
   - Set permissions: **Object Read & Write**
   - Copy **Access Key ID** and **Secret Access Key**
4. Your endpoint URL is: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
   - Find your Account ID in the right sidebar of the R2 page
5. (Optional) Set up a **Custom Domain** on your bucket for public access
6. Add all values to your `.env` and set `USE_R2=True`

---

## 📧 Weekly digest

Run manually:
```bash
python manage.py send_weekly_digest
```

Schedule with cron (every Monday at 8am):
```
0 8 * * 1 /path/to/venv/bin/python /path/to/manage.py send_weekly_digest
```

Or deploy with Celery + Redis using the built-in `CELERY_BEAT_SCHEDULE`.

---

## 📱 PWA

The app registers a service worker automatically when logged in. To test:

1. Serve over HTTPS (required for service workers)
2. Open in Chrome → DevTools → Application → Service Workers
3. The manifest is served at `/manifest.json`
4. For push notifications, generate VAPID keys:
   ```bash
   pip install py-vapid
   vapid --gen
   ```
   Add `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_ADMIN_EMAIL` to `.env`

---

## 🗂 Project structure

```
memboard_v7/
├── memboard/
│   ├── settings.py        # All config including R2, email, PWA
│   └── urls.py            # Root URLs + password reset
├── core/
│   ├── models.py          # All models: Group, Memory, Reaction, Comment, Notification, ActivityLog
│   ├── views.py           # All views
│   ├── urls.py            # All URL patterns
│   ├── forms.py           # All forms
│   ├── email_utils.py     # Email helpers
│   ├── context_processors.py
│   ├── admin.py
│   ├── static/core/
│   │   └── sw.js          # Service worker
│   ├── templates/core/
│   │   ├── base.html      # Layout with sidebar, search, notif badge
│   │   ├── home.html      # Board listing
│   │   ├── group_detail.html  # Board with memories, map, activity, members tabs
│   │   ├── _memory_form.html  # Reusable memory form partial
│   │   ├── search.html    # Search results
│   │   ├── notifications.html
│   │   ├── annual_recap.html
│   │   ├── friends.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── password_reset*.html (4 files)
│   │   └── create_group.html
│   └── management/commands/
│       └── send_weekly_digest.py
├── requirements.txt
├── Procfile
├── build.sh
└── .env (you create this)
```

---

## 🔗 Deploying to Railway / Render / Heroku

1. Set all env vars in the dashboard
2. Set `DEBUG=False`
3. The `build.sh` script runs `collectstatic` and `migrate` automatically
4. `Procfile` starts gunicorn

---

## Carrying over from v6

All v6 features are preserved:
- Email-based login (no username)
- Friend system (requests, accept/decline, remove)
- Group boards with privacy tiers (friends/invite/private)
- Memory sticky notes with colours, photos, tagging, edit permissions
- Font picker per user
- Email invites with auto-join on register
- Member management
