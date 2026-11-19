#!/usr/bin/env python3
"""singalong - say a song name, get the audio and live synced lyrics in your terminal.

Audio:  yt-dlp + mpv
Lyrics: LRCLIB (free, open, no API key)
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

APP = "singalong"
CONFIG_PATH = os.path.expanduser(f"~/.config/{APP}/config.json")
MUSIC_DIR = os.path.expanduser("~/Music/yt")
SOCK = f"/tmp/{APP}-{os.getpid()}.sock"

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"


def rgb(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


# Each theme: colors for the current line, sung words, upcoming words, and other lines.
THEMES = {
    "neon":   {"sung": rgb(255, 60, 200), "next": rgb(120, 120, 160), "other": rgb(70, 70, 100), "title": rgb(0, 255, 230)},
    "sunset": {"sung": rgb(255, 150, 60), "next": rgb(180, 110, 110), "other": rgb(110, 70, 80), "title": rgb(255, 90, 90)},
    "matrix": {"sung": rgb(0, 255, 80), "next": rgb(0, 120, 40), "other": rgb(0, 70, 30), "title": rgb(0, 255, 80)},
    "mono":   {"sung": "\033[97m", "next": "\033[90m", "other": "\033[90m", "title": "\033[97m"},
    "ocean":  {"sung": rgb(90, 200, 255), "next": rgb(70, 110, 160), "other": rgb(50, 70, 110), "title": rgb(140, 230, 255)},
}
# Display styles: how lyrics are laid out.
STYLES = ["karaoke", "line", "context"]

DEFAULTS = {"theme": "neon", "style": "karaoke", "big": True, "offset": 0.4}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP}/0.1 (personal project)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def fetch_lyrics(query):
    """Return (title, artist, synced_lines) where synced_lines = [(seconds, text)], or plain lines."""
    url = "https://lrclib.net/api/search?q=" + urllib.parse.quote(query)
    try:
        results = http_json(url)
    except Exception as e:
        print(f"lyrics lookup failed: {e}", file=sys.stderr)
        return query, "", [], []
    synced_hit = next((r for r in results if r.get("syncedLyrics")), None)
    hit = synced_hit or (results[0] if results else None)
    if not hit:
        return query, "", [], []
    title, artist = hit.get("trackName", query), hit.get("artistName", "")
    synced = []
    if hit.get("syncedLyrics"):
        for line in hit["syncedLyrics"].splitlines():
            m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)", line)
            if m:
                synced.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
    plain = (hit.get("plainLyrics") or "").splitlines()
    return title, artist, synced, plain


def download(query):
    os.makedirs(MUSIC_DIR, exist_ok=True)
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3", "--no-playlist", "--no-simulate",
        "-o", os.path.join(MUSIC_DIR, "%(title)s.%(ext)s"),
        "--print", "after_move:filepath",
        f"ytsearch1:{query} official audio remastered",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    path = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
    if out.returncode != 0 or not os.path.exists(path):
        sys.exit(f"download failed:\n{out.stderr.strip()[-400:]}")
    return path


class Mpv:
    def __init__(self, path):
        self.proc = subprocess.Popen(
            ["mpv", "--no-video", "--really-quiet", f"--input-ipc-server={SOCK}", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.sock = None
        for _ in range(50):
            try:
                s = socket.socket(socket.AF_UNIX)
                s.connect(SOCK)
                s.settimeout(0.3)
                self.sock = s
                break
            except OSError:
                time.sleep(0.1)

    def alive(self):
        return self.proc.poll() is None

    def time_pos(self):
        if not self.sock:
            return None
        try:
            self.sock.sendall(b'{"command":["get_property","time-pos"]}\n')
            buf = self.sock.recv(4096).decode(errors="ignore")
            for line in buf.splitlines():
                d = json.loads(line)
                if "data" in d and isinstance(d["data"], (int, float)):
                    return float(d["data"])
        except (OSError, ValueError):
            pass
        return None

    def stop(self):
        if self.alive():
            self.proc.terminate()
        try:
            os.unlink(SOCK)
        except OSError:
            pass


def center(text, width):
    visible = len(re.sub(r"\033\[[0-9;]*m", "", text))
    return " " * max(0, (width - visible) // 2) + text


def render_karaoke(line, progress, th):
    """Color words as the line is sung; progress is 0..1 across the line."""
    words = line.split()
    if not words:
        return ""
    cut = progress * len(words)
    out = []
    for i, w in enumerate(words):
        if i < cut:
            out.append(f"{BOLD}{th['sung']}{w}{RESET}")
        else:
            out.append(f"{th['next']}{w}{RESET}")
    return " ".join(out)


def draw(cfg, th, title, artist, synced, t):
    cols, rows = shutil.get_terminal_size((80, 24))
    idx = -1
    for i, (ts, _) in enumerate(synced):
        if ts <= t:
            idx = i
        else:
            break
    buf = ["\033[H\033[J"]
    head = f"{th['title']}{BOLD}{title}{RESET}{DIM} - {artist}{RESET}"
    buf.append(center(head, cols) + "\n")
    mid = rows // 2 - 2
    buf.append("\n" * max(1, mid))

    def get(i):
        return synced[i][1] if 0 <= i < len(synced) else ""

    if idx < 0:
        buf.append(center(f"{th['other']}...{RESET}", cols))
    else:
        start = synced[idx][0]
        end = synced[idx + 1][0] if idx + 1 < len(synced) else start + 4
        # words finish a bit before the next line so the last word isn't rushed
        prog = min(1.0, (t - start) / max(0.5, (end - start) * 0.85))
        style = cfg["style"]
        if style == "context":
            buf.append(center(f"{th['other']}{get(idx - 1)}{RESET}", cols) + "\n\n")
        cur = get(idx)
        if style == "line":
            cur_txt = f"{BOLD}{th['sung']}{cur}{RESET}"
        else:
            cur_txt = render_karaoke(cur, prog, th)
        if cfg.get("big"):
            cur_txt = cur_txt.replace(" ", "  ")
        buf.append(center(cur_txt, cols) + "\n")
        if style == "context":
            buf.append("\n" + center(f"{th['other']}{get(idx + 1)}{RESET}", cols))
    buf.append(f"\033[{rows};1H{DIM}ctrl+c to quit | theme: {cfg['theme']} | style: {cfg['style']}{RESET}")
    sys.stdout.write("".join(buf))
    sys.stdout.flush()


def sing(query, cfg):
    th = THEMES[cfg["theme"]]
    print(f"searching lyrics for: {query}")
    title, artist, synced, plain = fetch_lyrics(query)
    print(f"downloading audio ({title})...")
    path = download(query)
    player = Mpv(path)
    sys.stdout.write("\033[?25l\033[?1049h")
    try:
        if not synced:
            sys.stdout.write("\033[H\033[J" + f"{th['title']}{title}{RESET}\n\n(no synced lyrics found)\n\n" + "\n".join(plain))
            sys.stdout.flush()
            while player.alive():
                time.sleep(0.5)
        else:
            while player.alive():
                t = player.time_pos()
                if t is not None:
                    draw(cfg, th, title, artist, synced, t + cfg["offset"])
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()
        sys.stdout.write("\033[?1049l\033[?25h")


def main():
    cfg = load_config()
    p = argparse.ArgumentParser(prog=APP, description="Type a song name, hear it, and watch the lyrics.")
    p.add_argument("song", nargs="*", help="song name (and artist)")
    p.add_argument("--theme", choices=THEMES)
    p.add_argument("--style", choices=STYLES)
    p.add_argument("--big", choices=["on", "off"], help="wider word spacing")
    p.add_argument("--offset", type=float, help="lyric timing offset in seconds (+ shows lyrics earlier)")
    p.add_argument("--save", action="store_true", help="save the chosen options as your defaults")
    p.add_argument("--list", action="store_true", help="list themes and styles")
    a = p.parse_args()

    if a.list:
        print("themes:", ", ".join(THEMES))
        print("styles:", ", ".join(STYLES))
        return
    if a.theme: cfg["theme"] = a.theme
    if a.style: cfg["style"] = a.style
    if a.big: cfg["big"] = a.big == "on"
    if a.offset is not None: cfg["offset"] = a.offset
    if a.save:
        save_config(cfg)
        print(f"saved to {CONFIG_PATH}")
    if not a.song:
        if a.save:
            return
        p.error("give me a song name")
    sing(" ".join(a.song), cfg)


if __name__ == "__main__":
    main()
