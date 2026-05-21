#!/usr/bin/env python3
"""
claude-meter daemon.
Fetches Claude API usage, renders a 240x240 JPEG, uploads to the display webserver.
"""

import io
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# ── Configuration (edit this) ────────────────────────────────────────────────

DISPLAY_HOST   = "192.168.2.233"
POLL_INTERVAL  = 60   # seconds between refreshes
W = H          = 240  # display resolution

# ── Display endpoints (derived, do not edit) ──────────────────────────────────

DISPLAY_URL      = f"http://{DISPLAY_HOST}/doUpload?dir=/image/"
DISPLAY_SET_URL  = f"http://{DISPLAY_HOST}/set"
DISPLAY_IMG_PATH = "usage.jpg"

# ── Asset paths ───────────────────────────────────────────────────────────────

_ASSETS = Path(__file__).parent / "assets"
FONT_TIEMPOS  = _ASSETS / "TiemposText-400-Regular.otf"
FONT_STYRENE  = _ASSETS / "StyreneB-Regular.otf"
FONT_MONO     = _ASSETS / "DejaVuSansMono.ttf"
LOGO_PATH     = _ASSETS / "logo_80.png"

# ── Color palette (Anthropic dark, AMOLED-friendly) ──────────────────────────

BG       = (0,   0,   0)
PANEL    = (31,  31,  30)
TEXT     = (250, 249, 245)
DIM      = (176, 174, 165)
ACCENT   = (217, 119, 87)
GREEN    = (120, 140, 93)
AMBER    = (217, 119, 87)
RED      = (192, 57,  43)
BAR_BG   = (42,  42,  40)
PILL_BG  = (58,  58,  56)

# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str, err: bool = False) -> None:
    out = sys.stderr if err else sys.stdout
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=out, flush=True)


def read_token() -> str:
    creds = Path.home() / ".claude" / ".credentials.json"
    # Mirror the daemon's grep approach: find the first accessToken anywhere in the JSON
    m = re.search(r'"accessToken":"([^"]+)"', creds.read_text())
    if not m:
        raise RuntimeError("accessToken not found in ~/.claude/.credentials.json")
    return m.group(1)


def fetch_usage(token: str) -> dict:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "claude-code/2.1.5",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        },
        timeout=15,
    )

    h = resp.headers
    now = time.time()

    def pct(key: str) -> int:
        return round(float(h.get(key, "0")) * 100)

    def mins(key: str) -> int:
        ts = float(h.get(key, "0") or "0")
        return max(0, int((ts - now) / 60))

    return {
        "session_pct":        pct("anthropic-ratelimit-unified-5h-utilization"),
        "session_reset_mins": mins("anthropic-ratelimit-unified-5h-reset"),
        "weekly_pct":         pct("anthropic-ratelimit-unified-7d-utilization"),
        "weekly_reset_mins":  mins("anthropic-ratelimit-unified-7d-reset"),
        "status":             h.get("anthropic-ratelimit-unified-5h-status", "unknown"),
        "fetched_at":         datetime.now().strftime("%H:%M"),
    }


def fmt_reset(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    h = minutes // 60
    m = minutes % 60
    if h < 24:
        return f"{h}h {m}m"
    return f"{h // 24}d {h % 24}h"


def bar_color(pct: int) -> tuple:
    if pct < 50:
        return GREEN
    if pct < 80:
        return AMBER
    return RED


def render(data: dict) -> bytes:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Fonts
    ft_title  = ImageFont.truetype(str(FONT_TIEMPOS), 26)
    ft_pct    = ImageFont.truetype(str(FONT_STYRENE), 32)
    ft_sub    = ImageFont.truetype(str(FONT_STYRENE), 20)
    ft_label  = ImageFont.truetype(str(FONT_STYRENE), 11)
    ft_status = ImageFont.truetype(str(FONT_MONO),    14)

    # Logo — resize from 80×80 source to 36×36
    _lanczos = getattr(Image, "Resampling", Image).LANCZOS
    logo = Image.open(LOGO_PATH).convert("RGBA").resize((36, 36), _lanczos)
    img.paste(logo, (10, 8), logo)

    # Title
    draw.text((W // 2, 16), "Usage", font=ft_title, fill=TEXT, anchor="mt")

    # ── Panel helper ──────────────────────────────────────────────────────────
    MARGIN   = 10
    PANEL_W  = W - MARGIN * 2   # 220
    PANEL_H  = 78
    BAR_H    = 8
    BAR_X    = MARGIN + 8
    BAR_W    = PANEL_W - 16

    def draw_panel(top: int, pct_val: int, reset_mins: int) -> None:
        # Background card
        draw.rounded_rectangle(
            [(MARGIN, top), (MARGIN + PANEL_W, top + PANEL_H)],
            radius=4, fill=PANEL,
        )

        # Percentage left, reset time right — same baseline
        baseline = top + 42
        draw.text((MARGIN + 8,           baseline), f"{pct_val}%",               font=ft_pct, fill=TEXT, anchor="lb")
        draw.text((MARGIN + PANEL_W - 8, baseline), f"{fmt_reset(reset_mins)} left", font=ft_sub, fill=DIM,  anchor="rb")

        # Progress bar track
        bar_y = top + 54
        draw.rounded_rectangle(
            [(BAR_X, bar_y), (BAR_X + BAR_W, bar_y + BAR_H)],
            radius=4, fill=BAR_BG,
        )
        # Progress bar fill (minimum 4px so 0% is still visible)
        fill_w = max(4, round(BAR_W * min(pct_val, 100) / 100))
        draw.rounded_rectangle(
            [(BAR_X, bar_y), (BAR_X + fill_w, bar_y + BAR_H)],
            radius=4, fill=bar_color(pct_val),
        )


    draw_panel(46,  data["session_pct"], data["session_reset_mins"])
    draw_panel(132, data["weekly_pct"],  data["weekly_reset_mins"])

    # Status line at bottom
    draw.text(
        (W // 2, H - 8),
        f"● {data['status']} @ {data['fetched_at']}",
        font=ft_status, fill=ACCENT, anchor="mb",
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def send_image(img_bytes: bytes) -> None:
    try:
        requests.post(
            DISPLAY_URL,
            files={"file": ("usage.jpg", img_bytes, "image/jpeg")},
            timeout=10,
        )
    except (requests.exceptions.ChunkedEncodingError, requests.exceptions.InvalidHeader):
        pass  # device closes connection or sends malformed headers — upload still succeeded
    try:
        requests.get(DISPLAY_SET_URL, params={"img": DISPLAY_IMG_PATH}, timeout=15)
    except requests.exceptions.Timeout:
        pass  # display doesn't always ack the set command


def main() -> None:
    log("=== Clawdmeter host-display daemon ===")
    log(f"Interval: {POLL_INTERVAL}s  |  Display: {DISPLAY_URL}")

    while True:
        t0 = time.time()
        try:
            token = read_token()
            data  = fetch_usage(token)
            log(
                f"Session {data['session_pct']}% (resets {fmt_reset(data['session_reset_mins'])})  "
                f"Weekly {data['weekly_pct']}% (resets {fmt_reset(data['weekly_reset_mins'])})  "
                f"[{data['status']}]"
            )
            img_bytes = render(data)
            send_image(img_bytes)
            log("Sent OK")
        except Exception as exc:
            log(f"Error: {exc}", err=True)

        wait = max(0.0, POLL_INTERVAL - (time.time() - t0))
        log(f"Next update in {wait:.0f}s")
        time.sleep(wait)


if __name__ == "__main__":
    main()
