# claude-meter

Host-side daemon that fetches Claude API usage data and pushes a rendered image to a [GeekMagic SmallTV-Ultra](https://github.com/GeekMagicClock/smalltv-ultra).

![demo](assets/demo.png)

No firmware flashing required — the display runs its own webserver and the daemon uploads a fresh JPEG every 60 seconds.

## Display setup

On the SmallTV-Ultra:

1. **Settings** → select the **Photo album** theme
2. **Pictures** → disable **Image auto display**

## What is shown on the display

The display is split into two panels, refreshed every 60 seconds:

- **Session (5h)** — how much of your rolling 5-hour quota you've consumed, and how long until that window resets.
- **Weekly (7d)** — same for your 7-day rolling window.

Each panel shows the utilisation percentage, a progress bar, and the time remaining before the quota resets. The bar colour gives a quick at-a-glance signal:

| Colour | Meaning |
|---|---|
| Green | Below 50% — plenty of headroom |
| Amber | 50–79% — getting busier |
| Red | 80%+ — approaching the limit |

At the bottom of the screen a status line shows the current quota state reported by Anthropic (e.g. `ok`) and the time of the last successful update.

## How it works

Every 60 seconds the daemon:

1. **Reads your Claude Code credentials** from `~/.claude/.credentials.json` — the same token the `claude` CLI uses, so no separate API key is needed. If the token has expired, the daemon automatically refreshes it by running `claude` in the background.
2. **Calls the Anthropic API** with a minimal request (1 token) to retrieve your current rate-limit utilisation for both the 5-hour and 7-day windows.
3. **Renders a 240×240 JPEG** with the two usage panels, progress bars, and the status line.
4. **Pushes the image to the display** over the local network — no cloud relay, no account required on the display side.

If a cycle fails for any reason (network hiccup, API error, etc.) the daemon logs the error and retries on the next tick; the display simply keeps showing the last good image.

## Setup

```bash
pip install -r requirements.txt
```

Edit `DISPLAY_HOST` at the top of `claude-meter.py` to match your display's IP address.

## Run

```bash
python3 claude-meter.py
```

To run as a background service, use your system's process manager (systemd, launchd, etc.) or simply `nohup python3 claude-meter.py &`.

## Configuration

Only one value needs to be changed:

| Variable | Default | Description |
|---|---|---|
| `DISPLAY_HOST` | `192.168.2.233` | IP address of the display |
| `POLL_INTERVAL` | `60` | Seconds between refreshes |
| `W = H` | `240` | Display resolution |
| `LOCAL_OUTPUT` | `None` | Write the JPEG to a local path instead of pushing to the display (e.g. `/tmp/usage.jpg`). Useful for debugging or piping to another tool. |

## Dependencies

- `Pillow >= 8.2.0` — image rendering
- `requests` — HTTP uploads and API calls
- Font and logo assets from `./assets/` (part of this repo)

## Display protocol

The daemon expects the display to expose two endpoints:

- `POST /doUpload?dir=/image/` — multipart file upload (`field: file`, `filename: usage.jpg`)
- `GET /set?img=usage.jpg` — instruct the display to show the uploaded file

Tested with a 240×240 display running a compatible HTTP firmware. The daemon tolerates truncated HTTP responses from the upload endpoint (`ChunkedEncodingError`) and silent `/set` calls (`Timeout`), both of which are normal on embedded webservers.
