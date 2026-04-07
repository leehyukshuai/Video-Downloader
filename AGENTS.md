# AGENTS.md

This repository is a minimal local video downloader.

## Structure

- `src/`
  - Python backend package
- `web/`
  - static front-end assets, including `supportedsites.json`

## Runtime expectations

The active environment must provide:

- `yt-dlp`
- `ffmpeg`
- `node`

## Startup

```powershell
conda activate video-downloader
python main.py
```

## Conventions

1. Keep the project minimal.
2. Do not reintroduce bundled binaries or launcher scripts unless explicitly requested.
3. Default download directory should remain the system `Downloads` folder unless intentionally changed.
4. If dependencies or startup flow change, update:
   - `environment.yml`
   - `README.md`
