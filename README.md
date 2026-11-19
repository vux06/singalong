# singalong

Type a song name. Hear it. Watch the lyrics light up word by word in your terminal.

No AI, no accounts, no API keys. Just yt-dlp, mpv and LRCLIB.

## How it works

1. Searches YouTube with yt-dlp and downloads the audio as mp3 to `~/Music/yt`.
2. Fetches time-synced lyrics from [LRCLIB](https://lrclib.net) (free and open).
3. Plays the song with mpv and asks it for the playback position about 20 times a second over mpv's IPC socket.
4. Redraws the current lyric line, spreading the words across the line's duration for a karaoke effect.

## Requirements

- Python 3.8+
- yt-dlp
- mpv
- ffmpeg (used by yt-dlp for mp3 conversion)
- A terminal with truecolor support (kitty, alacritty, foot, etc.)

## Usage

```
python3 singalong.py put your head on my shoulder paul anka
python3 singalong.py --theme sunset --style context blinding lights
python3 singalong.py --theme ocean --style line --save
```

## Options

| Option | What it does |
| --- | --- |
| `--theme` | neon, sunset, matrix, mono, ocean |
| `--style` | karaoke (words glow), line, context (shows previous and next line) |
| `--big on/off` | wider word spacing |
| `--offset SECONDS` | shift lyric timing, positive shows lyrics earlier (default 0.4) |
| `--save` | save the chosen options as your defaults |
| `--list` | list themes and styles |

Settings are stored in `~/.config/singalong/config.json`.

## Notes

Word timing is estimated by spreading the words evenly across each line, since LRCLIB only provides per-line timestamps. Press Ctrl+C to quit.

For personal use. Respect the copyright of the music you download.
