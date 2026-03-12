# Spotie - Music Queue Manager

Aplikasi web untuk mencari lagu di Spotify dan menambahkannya ke antrian musik melalui integrasi n8n webhook.

## Fitur

- 🔍 **Pencarian Lagu** - Cari lagu dari katalog Spotify
- 🎵 **Now Playing** - Lihat lagu yang sedang diputar
- ➕ **Tambah ke Antrian** - Tambahkan lagu ke antrian via n8n webhook
- 🔐 **OAuth Authentication** - Autentikasi aman dengan Spotify

## Teknologi

- Python 3.x
- Flask
- Spotify Web API
- n8n Webhook

## Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/dodonquixote/spotie.git
cd spotie
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Konfigurasi Environment

Buat file `.env` dan isi dengan kredensial Spotify:

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
SPOTIFY_REFRESH_TOKEN=
```

> **Note:** Dapatkan Client ID dan Client Secret dari [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)

### 4. Jalankan Aplikasi

```bash
python app.py
```

Aplikasi akan berjalan di `http://localhost:8000`

## Setup Spotify OAuth

1. Buka `http://localhost:8000/setup`
2. Login dengan akun Spotify
3. Izinkan akses aplikasi
4. Refresh token akan otomatis disimpan ke file `.env`

## API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/` | GET | Halaman utama |
| `/setup` | GET | Setup OAuth Spotify |
| `/callback` | GET | Callback OAuth |
| `/api/search?q=query` | GET | Cari lagu |
| `/api/now-playing` | GET | Lagu yang sedang diputar |
| `/api/queue` | POST | Tambah lagu ke antrian |
| `/api/auth-status` | GET | Status autentikasi |
| `/api/health` | GET | Health check |

## Struktur Proyek

```
spotie/
├── app.py                  # Aplikasi Flask utama
├── requirements.txt        # Dependencies Python
├── .env                    # Environment variables (tidak di-commit)
├── .gitignore
├── README.md
└── templates/
    └── music-queue-manager.html
```

## Lisensi

MIT License
