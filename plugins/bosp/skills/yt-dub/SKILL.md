---
name: yt-dub
description: >
  Give a YouTube video Yandex's Russian voice-over (the Yandex Browser / voice-over-translation
  one) at any length — including past Yandex's 4-hour limit — and mux it into the best video
  YouTube serves, with the original sound kept as a second track; optionally drop the result
  into Plex on SugarDaddy. Also when only the translated audio is wanted.
when_to_use: >
  Trigger on: yt-dub, "озвучь/переведи это видео", "закадровый перевод для YouTube",
  "хочу посмотреть/послушать это видео на русском", "видео длиннее 4 часов, Яндекс не
  переводит", "склей перевод с видео", "закинь в plex", a YouTube link plus "на русском".
allowed-tools: Bash
---

# yt-dub

`yt-dub` (on PATH via this plugin's `bin/`) does the whole job:

```bash
yt-dub URL                                   # → ~/Downloads/<title> (RU).mp4
yt-dub URL --plex root@192.168.1.10:/mnt/m0/media --ssh-key ~/.ssh/sshs   # and into Plex
```

Flags: `--out DIR`, `--lang en` (source), `--reslang ru|en|kk`, `--browser arc[:Profile 1]`
(cookies), `--orig-volume 0.2` (original under the voice-over), `--plex-container plex`, `--keep`.

A 5-hour video takes about an hour: Yandex needs ~20 min per 2.5-hour part. Run it with
`run_in_background` and tell the user roughly when to expect it. Output paths go to stdout,
progress to stderr.

## What it does

1. Cookies from the browser (`--browser`, default Arc; yt-dlp has no Arc on macOS, the script
   reads it with Arc's keychain item). Without them YouTube answers "confirm you're not a bot".
   The cookie file is temporary and removed at exit. Chromium browsers trigger a Keychain prompt
   the first time.
2. Downloads 360p and cuts it into equal parts under 3 h 50 min (Yandex refuses > 4 h).
3. Serves the parts on 127.0.0.1 through a `cloudflared` quick tunnel (random
   `*.trycloudflare.com` URL, closed when done) and asks Yandex via `npx vot-cli@2.1.0` to
   translate each one by URL; glues the mp3s.
4. Downloads the best video (h264 up to 1080p; above that whatever 4K stream exists) and the
   original audio; muxes: track 1 = voice-over mixed over the original at `--orig-volume`
   (default), track 2 = original.
5. `--plex`: scp to `DIR/<title> (RU)/`, owner copied from `DIR`, then refreshes every library of
   the `plex` container (token read from its Preferences.xml).

Every step's output is cached in `~/Library/Caches/yt-dub/<video id>/`; after a failure just rerun
the same command and it resumes (e.g. translated parts are not requested again). The cache is
deleted on success unless `--keep`.

## Known edges

- At each part boundary the voice-over can clip a phrase (cuts are by time, not at pauses).
- The result has only Yandex's voice for the translated track; quality is Yandex's.
- `Yandex did not translate …` on one part: rerun; it resumes from that part.
- Needs `yt-dlp` (its Python must import `yt_dlp`), `ffmpeg`, `cloudflared`, `node`/`npx`.
- SugarDaddy's Plex libraries: «Фильмы» = `/mnt/m0/media`, «Любимые» = `/mnt/m0/perm`. Plex may
  match the file to a wrong movie; fix in Plex with "Fix Match"/"Unmatch".

Tests: `python3 -m pytest plugins/bosp/skills/yt-dub`.
