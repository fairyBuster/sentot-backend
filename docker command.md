# Perintah Docker (Django + Gunicorn + Caddy + Postgres)

## Prasyarat
- Domain APP_DOMAIN menunjuk ke IP VPS (DNS A/AAAA).
- Port 80 dan 443 terbuka.
- File `.env` sudah diisi (DATABASE_*, APP_DOMAIN, ACME_EMAIL, DEBUG=False).

## Instalasi Docker di VPS (Ubuntu)
```bash
# Update sistem & alat pendukung
sudo apt-get update && sudo apt-get install -y \
  ca-certificates curl gnupg lsb-release

# Siapkan keyring untuk repositori Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Tambahkan repositori Docker (stable)
echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose plugin
sudo apt-get update && sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Aktifkan service Docker
sudo systemctl enable --now docker

# (Opsional) Izinkan user non-root menjalankan docker
sudo usermod -aG docker $USER
newgrp docker

# Verifikasi
docker -v
docker compose version
```

### Firewall (opsional)
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

## Boot Semua Layanan
```bash
docker compose up -d --build
```

## Inisialisasi Aplikasi
```bash
docker compose exec web python manage.py migrate --noinput
docker compose exec web python manage.py collectstatic --noinput
```

## Cek Kesehatan & Akses
- Health: `https://$APP_DOMAIN/health`
- Log berjalan:
```bash
docker compose logs -f caddy
docker compose logs -f web
docker compose logs -f db
```

## Ubah Domain Cepat (SSL otomatis)
1) Edit `.env`: `APP_DOMAIN=domain-baru.tld` (opsional `ACME_EMAIL`)
2) Terapkan:
```bash
docker compose up -d
```

## Ubah Setting Gunicorn
- Tambahkan di `.env` (dipakai oleh perintah service `web`):
```
WORKERS=4
THREADS=2
TIMEOUT=180
KEEP_ALIVE=65
MAX_REQUESTS=1000
MAX_REQUESTS_JITTER=50
LOG_LEVEL=info
```
- Terapkan:
```bash
docker compose up -d
```

## Manajemen Database
- Import awal dari `backup.sql` otomatis saat Postgres pertama kali inisialisasi.
- Reset DB dan re-import (HAPUS SEMUA DATA):
```bash
docker compose down
docker volume rm sentotbackend_pgdata
docker compose up -d
```

## Masuk Shell Kontainer
```bash
docker compose exec web sh
docker compose exec db sh
```

## Hentikan / Restart
```bash
docker compose down
docker compose restart
```

## Update Kode
```bash
git pull
docker compose up -d --build
```

## Catatan
- Kredensial Postgres dibuat otomatis saat inisialisasi pertama sesuai `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` di `.env`.
- Jika build Alpine gagal karena dependency native, tambahkan paket APK yang diperlukan atau ganti base image ke `python:3.11-slim`.

## Monitoring & Status

### Log
```bash
# Semua service
docker compose logs -f
# Hanya backend (Gunicorn/Django)
docker compose logs -f web
# Hanya Caddy
docker compose logs -f caddy
# Hanya Postgres
docker compose logs -f db
# Tail 100 baris terakhir
docker compose logs --tail=100 web
# Filter error (Ubuntu)
docker compose logs -f web | grep -i error
# Filter error (PowerShell)
docker compose logs -f web | findstr /i error
```

### Status Layanan
```bash
# Daftar service dan status
docker compose ps
# Proses dalam container
docker compose top web
# Resource live (CPU/RAM/NET)
docker stats
# Health DB (ada healthcheck)
docker inspect -f "{{.State.Health.Status}}" sentot-postgres
```

### Cek Kesehatan Aplikasi
```bash
# Dari publik (Caddy + SSL)
curl -I https://$APP_DOMAIN/health
# Dari host ke container web
curl http://localhost:8000/health
# Dari jaringan compose (via container)
docker compose exec caddy wget -qO- http://web:8000/health
```
