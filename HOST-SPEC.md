# The always-on host — a DataBrick for cultural memory

A small physical object in the home that holds the household's cultural
memory and serves it to your devices — visible on a shelf, unpluggable,
sovereign. The lineage is the DataBrick: data as a *thing in place*,
connected outward only where wanted. This spec turns a Raspberry Pi into
that object for the String.

Why it matters beyond tidiness: it retires the sleeping-laptop failure
class (the scrobbler's missed album), and it is the precondition for
capture surfaces that post from anywhere — the pocket totem needs a
String that answers at 11pm from a gallery bar.

## Hardware

| Part | Choice | Notes |
|---|---|---|
| Board | Raspberry Pi 5, 8 GB | 4 GB fine; Pi 4 workable |
| Storage | NVMe SSD via M.2 HAT (or USB3 SSD) | SD cards die under SQLite WAL; SSD is the one non-negotiable |
| PSU | Official 27 W | under-powered PSUs cause silent corruption |
| Case | Any with airflow; passive fine | it should look like an object, not a project — a nice box is on-theme |
| Optional later | small e-ink / LED matrix display | today's bead count as a glyph; the Nothing dot-language, domestically |

## OS & base

Raspberry Pi OS Lite 64-bit. Then:

    sudo apt update && sudo apt install -y docker.io docker-compose-plugin git sqlite3
    sudo usermod -aG docker $USER
    curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up

Tailscale is the connectivity story: every device on your tailnet can
reach the String; nothing is exposed to the public internet. MagicDNS
gives you a stable name (e.g. `http://brick:8100`).

## The String

    git clone https://github.com/Geocontrol/cultureblocs-string
    cd cultureblocs-string
    # copy data/ from the Mac (stop the Mac stack first):
    #   scp -r mac:.../cultureblocs-string/data ./data
    docker compose up -d --build

**Set STRING_TOKEN** in docker-compose.yml before first start: the
moment the String is reachable beyond localhost, auth stops being
optional — it now holds identity app passwords. Give the token to the
timeline (settings), the pocket totem (settings), and workers (env).

## Workers (systemd, not cron — logs and restarts for free)

`/etc/systemd/system/cultureblocs-scrobbler.service`:

    [Unit]
    Description=cultureblocs scrobble worker
    [Service]
    Type=oneshot
    WorkingDirectory=/home/pi/cultureblocs-string
    Environment=LASTFM_USER=you LASTFM_API_KEY=xxx STRING_TOKEN=xxx
    ExecStart=/usr/bin/python3 workers/scrobbler.py

`/etc/systemd/system/cultureblocs-scrobbler.timer`:

    [Unit]
    Description=hourly scrobble sweep
    [Timer]
    OnCalendar=hourly
    Persistent=true
    [Install]
    WantedBy=timers.target

    sudo systemctl enable --now cultureblocs-scrobbler.timer

**sonos-lastfm moves here too** (same LAN as the speakers, always
awake — its natural home). Install via uv/pipx, then a plain service
unit with `Restart=always` — and remember the lesson from the Mac:
set `WorkingDirectory=` to somewhere writable; it creates a relative
`data/` dir and crashes from `/`.

## Backups (non-negotiable once this is the only copy)

Nightly, e.g. `/etc/cron.daily/string-backup`:

    #!/bin/sh
    D=/home/pi/backups/$(date +%F)
    mkdir -p "$D"
    sqlite3 /home/pi/cultureblocs-string/data/string.db ".backup '$D/string.db'"
    cp -r /home/pi/cultureblocs-string/data/media "$D/"
    find /home/pi/backups -maxdepth 1 -mtime +30 -exec rm -rf {} +

Then rsync/restic that directory somewhere *off the brick* (the Mac,
a USB stick, cloud). The db now contains identity app passwords —
treat backups as credential-bearing.

## Cutover checklist

1. Mac: `docker compose down`; final backup of `data/`.
2. Brick: data copied, token set, compose up; timeline loads a day ✓.
3. Repoint: timeline/Studio settings → `http://brick:8100` + token;
   LaunchAgents on the Mac boot out (scrobbler + sonos-lastfm — both
   now live on the brick).
4. Watch one full day: a scrobble session appears; a totem push from
   the Studio lands; a publish works.
5. Only then delete the Mac's `data/`.

## Later, on-theme

- A glyph display: today's beads as dots — the household string,
  ambient. (Ties to the pocket totem's design language.)
- The org's String could live here too (second compose project) the
  day the meetup outgrows one desk.
