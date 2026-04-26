#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Memboard – one-time setup script
# Run from the project root (the folder containing manage.py)
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "🗄️  Running migrations..."
python manage.py makemigrations core
python manage.py migrate

echo ""
echo "👤 Create your admin account (optional — press Ctrl+C to skip)"
python manage.py createsuperuser --noinput \
  --username admin --email admin@memboard.local 2>/dev/null || true

echo ""
echo "✅ Setup complete!"
echo ""
echo "▶️  Start the server with:"
echo "    python manage.py runserver"
echo ""
echo "🌐 Then open:  http://127.0.0.1:8000/"
echo "🔧 Admin:      http://127.0.0.1:8000/admin/"
