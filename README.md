# Coach Chess

Coach Chess is a local-first training app that lets you:

- play chess against the computer in your browser
- ask for a hint when you are stuck
- run a post-game review based on engine analysis
- turn that engine review into plain-English coaching with LM Studio running locally

## Why this setup

The strongest path for actual chess improvement is:

1. use a chess engine for the truth about the position
2. use a local LLM only to explain the engine findings in a friendlier way

That keeps the analysis grounded instead of asking a language model to guess chess lines on its own.

## What is inside

- `app.py`: Flask entry point
- `coach_chess/`: gameplay, engine, review, and LM Studio integration
- `templates/` and `static/`: browser UI

## Requirements

- Python 3.9+
- Stockfish installed locally for the best playing strength and review quality
- LM Studio with a local instruct model loaded if you want natural-language post-game coaching

The app still runs without Stockfish, but it falls back to a lightweight built-in engine. That is fine for basic play, but Stockfish is what makes the review trustworthy.

## Setup

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Stockfish

If `stockfish` is already on your `PATH`, you are done.

If not, install it and point the app at the binary:

```bash
export STOCKFISH_PATH="/absolute/path/to/stockfish"
```

On macOS, a common route is installing it through Homebrew and then using the installed binary path.

### 3. Start LM Studio

LM Studio supports an OpenAI-compatible local server. According to LM Studio's docs, the common local base URL is `http://localhost:1234/v1`, and it supports `POST /v1/chat/completions` for local chat inference:

- [OpenAI compatibility endpoints](https://lmstudio.ai/docs/developer/openai-compat/)
- [Chat completions](https://lmstudio.ai/docs/developer/openai-compat/chat-completions)
- [Local server setup](https://lmstudio.ai/docs/developer/core/server)

Recommended LM Studio setup:

1. Load any local instruct model that fits your machine.
2. A 7B to 8B instruct model is a good starting point for this app.
3. Start LM Studio's local server from the Developer tab or with `lms server start`.

Optional environment variables:

```bash
export LM_STUDIO_BASE_URL="http://127.0.0.1:1234/v1"
export LM_STUDIO_MODEL="your-loaded-model-id"
export LM_STUDIO_API_KEY="lm-studio"
```

If `LM_STUDIO_MODEL` is not set, the app tries to use the first model returned by LM Studio's `/v1/models` endpoint.

### 4. Run the app

```bash
python3 app.py
```

Then open:

```text
http://127.0.0.1:8000
```

## How to use it

### During the game

- choose your color and difficulty
- click a piece, then click its destination square
- click `Get Hint` when you want a suggested move

### After the game

- click `Analyze Game`
- review the engine summary
- read the LM Studio coaching notes
- copy the PGN if you want to save the game elsewhere

## Useful environment variables

```bash
export COACH_CHESS_HOST="127.0.0.1"
export COACH_CHESS_PORT="8000"
export COACH_CHESS_REVIEW_DEPTH="12"
export ALLOW_CORS_ORIGIN="https://your-username.github.io"
```

`ALLOW_CORS_ORIGIN` is there for a future split-frontend setup. If you later want a GitHub Pages frontend, you can keep this Python backend local and allow the hosted frontend to call it.

## Next upgrade path

If you decide later that you want a GitHub Pages or React frontend, this project is already close:

- keep the Python API local
- host the UI separately as static files
- point the frontend at the local API
- keep LM Studio and Stockfish on your own machine

That architecture is very workable. It is just a second step, not a blocker.
# AI-Chess-Learn
