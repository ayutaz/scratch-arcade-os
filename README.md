# Scratch Arcade OS

English | [日本語](README.ja.md)

[![CI](https://github.com/ayutaz/scratch-arcade-os/actions/workflows/host-tests.yml/badge.svg)](https://github.com/ayutaz/scratch-arcade-os/actions/workflows/host-tests.yml)

**Build games and tools on your Mac, then run them on a handheld ESP32-S3.**

Scratch Arcade OS provides a Japanese home screen where you can choose, launch, and close your apps. Add or update an app without rebuilding the OS.

![Lane Catcher running in the Mac simulator](docs/images/host-lane-catcher.png)

*Mac simulator screenshot. This is an independent project, not official Scratch Arcade firmware.*

## What you can do

- Play games with the device's buttons and joystick.
- Keep high scores and timer settings across normal restarts.
- Play sounds and record up to 2 seconds of audio in RAM.
- Control a timer from your Mac over Wi-Fi.

Apps are written in C99 and compiled to WebAssembly. The OS uses ESP-IDF, FreeRTOS, and WAMR. See the [architecture](docs/architecture.md) for details.

## Try a game on your Mac

You need an **Apple Silicon Mac and [uv](https://docs.astral.sh/uv/getting-started/installation/)**. The project uses Python 3.12.13, managed by uv. No device is needed for this step.

```sh
git clone https://github.com/ayutaz/scratch-arcade-os.git
cd scratch-arcade-os
uv sync --locked
uv run --locked python tools/bootstrap.py --font
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/lane-catcher
```

The first setup downloads the pinned compiler, runtime, and font. The last command opens a game window.

Use the arrow keys to move. **Z = A**, **R = X**, **X = B**, **F + X = FN + B**.

The Mac simulator lets you check game logic and drawing. Device audio, network, and persistent storage are not connected in the default window; those apps show a fallback state. Device speed, LCD appearance, and sound quality need hardware tests.

## Included apps

| App | What it does |
|---|---|
| [Lane Catcher](apps/lane-catcher/README.md) | Catch targets in three lanes and save your best score |
| [Maze Runner](apps/maze-runner/README.md) | Find a path around walls and collect targets |
| [Focus Timer](apps/focus-timer/README.md) | Set a 10–300 second timer and keep your settings |
| [Voice Recorder](apps/voice-recorder/README.md) | Record and play back 2 seconds of audio |
| [Audio Desk](apps/audio-desk/README.md) | Try a test tone, short recording, and playback volume |
| [Remote Timer](apps/remote-timer/README.md) | Start, stop, and query a timer from your Mac |

Five smaller SDK examples are also included. A new firmware build starts with game and counter; the other apps are installed separately.

## Build for the device

Hardware support currently targets **one observed Scratch Arcade ESP32-S3 board**. Check the [board information](boards/scratch-arcade/README.md) before planning an installation.

```sh
uv run --locked python tools/bootstrap.py --idf
uv sync --project firmware/esp-idf/host-tools --locked
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.target build-candidate
```

This only builds the firmware. `scripts/flash.sh` refuses device writes. Device testing was done during earlier development; the public-source rebuild has not been flashed again. See [validation](docs/validation.md) and [development instructions](docs/development.md) for the tested scope and installation limits.

## Make your own app

Start with the [SDK and app guide](docs/development.md). To run the host tests:

```sh
uv run --locked python tools/test.py
```

[Contributing](CONTRIBUTING.md) covers TDD and the PR workflow. CI checks the repository, host tests, ESP32-S3 build, and Python dependencies. Main requires all four checks. Version tags can publish source archives and checksums; see [CI/CD](docs/ci-cd.md).

Detailed engineering documents are currently in Japanese.

## License

Original code is [Apache-2.0](LICENSE). Third-party code and fonts keep their own licenses; see [NOTICE](NOTICE) and [third-party notices](THIRD_PARTY_NOTICES.md).
