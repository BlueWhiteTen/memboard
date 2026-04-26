# Memboard 📝

A Django web app for saving shared memories with friends.
Create group boards, add post-it memories, tag friends, and upload photos.

---

## Features

- **Auth** — Register, login, logout
- **Friends** — Send/accept/decline friend requests, remove friends
- **Group boards** — Create boards, set privacy (Friends only / Invite only / Just me)
- **Members** — Invite friends to boards; members shown with colour-coded initials
- **Memories** — Add post-it notes with title, content, colour, optional photo
- **Tagging** — Tag group members on each memory; tagged friends shown as stacked initials
- **Filter** — Filter board view by creator or tagged person
- **Delete** — Memory creators can remove their own memories
- **Admin** — Full Django admin at `/admin/`

---

## Quick Start

### 1. Clone / unzip the project

```bash
cd memboard   # the folder containing manage.py
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 3. Run the setup script

```bash
bash setup.sh
```

This installs Django + Pillow, runs migrations, and prompts for a superuser.

### 4. Start the server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

---

## Manual setup (if you prefer)

```bash
pip install -r requirements.txt
python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Project structure

```
memboard/
├── manage.py
├── requirements.txt
├── setup.sh
├── memboard/                  ← Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── core/                      ← Main application
    ├── models.py              ← Group, Memory, Friendship, FriendRequest
    ├── views.py               ← All views
    ├── urls.py                ← URL patterns
    ├── forms.py               ← All forms
    ├── admin.py               ← Admin registration
    ├── context_processors.py  ← Sidebar data (groups, pending count)
    └── templates/core/
        ├── base.html          ← Shared sidebar layout
        ├── login.html
        ├── register.html
        ├── home.html          ← Dashboard with board grid
        ├── create_group.html  ← New board form with live preview
        ├── group_detail.html  ← Board with post-it memories + modals
        └── friends.html       ← Friend management
```

---

## URL reference

| URL | Name | Description |
|-----|------|-------------|
| `/` | `home` | Dashboard |
| `/register/` | `register` | Create account |
| `/login/` | `login` | Sign in |
| `/logout/` | `logout` | Sign out |
| `/groups/new/` | `create_group` | New board |
| `/groups/<pk>/` | `group_detail` | Board view |
| `/groups/<pk>/invite/` | `invite_member` | Add member (owner only) |
| `/groups/<pk>/delete/` | `delete_group` | Delete board (owner only) |
| `/groups/<pk>/memory/add/` | `add_memory` | Post new memory |
| `/memory/<pk>/delete/` | `delete_memory` | Remove memory (creator only) |
| `/friends/` | `friends` | Friends page |
| `/friends/request/` | `send_friend_request` | Send request |
| `/friends/accept/<id>/` | `accept_friend_request` | Accept request |
| `/friends/decline/<id>/` | `decline_friend_request` | Decline request |
| `/friends/remove/<id>/` | `remove_friend` | Unfriend |

---

## Extending the app

### Adding photo thumbnails
Install `django-imagekit` and add a `ProcessedImageField` to `Memory.photo`.

### Email notifications
Add `django.core.mail` calls in `accept_friend_request_view` and `invite_member_view`.

### Production deployment
- Set `DEBUG = False` and a real `SECRET_KEY` (use environment variables)
- Use PostgreSQL instead of SQLite
- Serve media files via nginx or a cloud bucket (S3, Cloudflare R2)
- Run `python manage.py collectstatic`

---

## Tech stack

- **Backend** — Django 4.2, Python 3.10+
- **Database** — SQLite (dev) / PostgreSQL (prod)
- **Fonts** — Lora (serif headings), DM Sans (UI), Caveat (handwritten notes)
- **Styling** — Plain CSS with CSS variables, no framework
- **Images** — Pillow for photo upload handling
