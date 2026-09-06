# Memboard v8

A Django-based shared memory-keeping app with rich social features, PWA support, and Cloudflare R2 photo storage.

---

## ✨ What's new in v8.1 (social features)

This round adds the bigger new-features list that was deferred from the first
v8 pass:

| Feature | Details |
|---|---|
| **Groups** (friend groups) | Cluster your friends into named groups (Settings → Groups in the sidebar). A group can be used to control who sees a board, or as a shortcut to quick-add a bunch of people when creating a new board. |
| **Board privacy rework** | Boards now have 4 privacy levels: *Just me*, *Only members*, *A specific friend group*, or *All my friends*. The latter two make the board show up (as a bare listing — name and cover only) under "Shared with me" on the home dashboard for people who can see it but haven't joined. |
| **Request to join** | Anyone who can see a board under "Shared with me" can request to join it. The board owner gets a notification and can approve or decline from the board's Members tab. |
| **Visibility notifications** | You're notified when a board becomes newly visible to you — because the owner changed its privacy, you became friends with the owner, or you were added to the friend group a board is shared with. |
| **Shared-boards count** | Friend chips (home page, Friends page) now show how many boards you have in common. |
| **Friend mini-profile** | Click a friend to see a small profile page: boards you share and mutual friends. |
| **On this day** | Memories from this date in past years now surface in three places: a widget on the home dashboard, a dedicated `/on-this-day/` page you can browse day by day, and a daily notification (new `send_on_this_day_notifications` management command — see housekeeping below). |
| **New-user onboarding** | The home dashboard now shows a friendly prompt to add your first friend when you don't have any yet, and board activity/trash empty states got clearer copy. |

## ✨ What's new in v8 (first round)

This round focused on bug fixes and the design flaws flagged as most urgent.

| Fix | Details |
|---|---|
| **Big "Add memory" button** | A large, hard-to-miss button now sits below the board header, above the memories grid — the small `+` FAB is still there too. |
| **Taller map** | The board's Map tab now uses up to ~72% of the viewport height instead of a fixed 400px. |
| **Photo lightbox** | Clicking any memory photo opens it full-size in an overlay (click outside, the ✕, or Esc to close). |
| **Image compression** | Photos are automatically resized (max 1920px) and re-encoded (JPEG/PNG) on upload, for both memory photos and board covers — before they ever reach storage. |
| **Soft delete / recycle bin** | Deleting a memory now moves it to a per-board "Trash" tab instead of destroying it immediately. You can restore your own deleted memories for 30 days; a daily job then purges them for good. |
| **Leave board** | Non-owner members can now leave a board from the Members tab. Owners are told to delete the board or transfer ownership instead. |
| **Rate limiting** | Login and registration are now rate-limited per IP (15 attempts/5 min for login, 10/hour for registration) to slow down brute-force and spam-signup attempts. This is a first pass — see "Before public launch" below for the stronger version planned pre-launch. |
| **Automated daily backups** | A new `backup_db` management command dumps the full database to a gzip-compressed JSON fixture and stores it via whatever storage backend is configured, with automatic pruning of old backups. See "Database backups" below for scheduling it. |
| **Fixed a broken `migrate` on fresh databases** | `0002_v7_additions` had leftover `AddField`/`CreateModel` operations that duplicated columns and tables already defined in `0001_initial` (likely from a migration squash that didn't clean up the old file) — this made `python manage.py migrate` fail immediately on any brand-new database with `duplicate column name`. It's now a no-op placeholder; already-deployed databases are unaffected. |

Deliberately **not** in this round (flagged for later, on request): moving photo
storage to Cloudflare R2, and the SQLite→PostgreSQL item (which turned out to
be about the separate *Vault* project, not Memboard).

### 🗑 Recycle bin, backups & on-this-day housekeeping

Three management commands need to run on a schedule — they don't run themselves:

```bash
python manage.py backup_db                       # dumps + stores a compressed backup, prunes old ones (default: keeps 14)
python manage.py purge_deleted_memories           # permanently removes memories deleted more than 30 days ago
python manage.py send_on_this_day_notifications   # notifies users who have "on this day" memories today
```

Add all three to crontab (or your host's scheduled-job equivalent), running daily, e.g.:

```
0 3 * * *   python manage.py backup_db
0 4 * * *   python manage.py purge_deleted_memories
0 8 * * *   python manage.py send_on_this_day_notifications
```

**Important:** `backup_db` writes through whatever `DEFAULT_FILE_STORAGE` is
configured (local disk by default, or R2/S3 once `USE_R2=True`). Render's own
disk is ephemeral unless you attach a persistent disk — so until R2 (or a
persistent disk) is wired up, backups will disappear on redeploy. Treat this
first pass as "backups exist and are automated," with "backups survive a
redeploy" as a fast-follow once storage is sorted.

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

# Email — sent via the Resend API (https://resend.com), not SMTP, since
# many hosts block outbound SMTP ports. Sign up free, grab an API key.
RESEND_API_KEY=re_your_api_key
RESEND_FROM_EMAIL=onboarding@resend.dev   # or an address on your own verified domain

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
memboard/
├── memboard/
│   ├── settings.py        # All config including R2, email, PWA
│   └── urls.py            # Root URLs + password reset
├── core/
│   ├── models.py          # All models: Group, Memory, Reaction, Comment, Notification, ActivityLog
│   ├── views.py           # All views
│   ├── urls.py            # All URL patterns
│   ├── forms.py           # All forms
│   ├── image_utils.py     # Upload-time image compression/resizing
│   ├── email_utils.py     # Email helpers
│   ├── context_processors.py
│   ├── admin.py
│   ├── static/core/
│   │   └── sw.js          # Service worker
│   ├── templates/core/
│   │   ├── base.html      # Layout with sidebar, search, notif badge
│   │   ├── home.html      # Board listing
│   │   ├── group_detail.html  # Board with memories, map, activity, members, trash tabs
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
│       ├── send_weekly_digest.py
│       ├── backup_db.py             # Daily DB backup (see above)
│       └── purge_deleted_memories.py  # Empties the recycle bin after 30 days
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
