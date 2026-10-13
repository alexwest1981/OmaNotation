#!/usr/bin/env bash
# Installs notat: the command, the VAD model, a whisper model and the bar button in Omarchy.
#   ./install.sh            (downloads kb-whisper-small, 466 MB)
#   ./install.sh --no-model
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
MODEL_ROOT="$HOME/.local/share/notat/models"
VAD="$MODEL_ROOT/ggml-silero-v5.1.2.bin"

require() {
  command -v "$1" >/dev/null || { echo "missing: $1  ->  $2"; exit 1; }
}
require python3 "install python3"
require ffmpeg "pacman -S ffmpeg"
require pactl "pacman -S pipewire-pulse  (pactl comes with it)"
command -v whisper-cli >/dev/null || echo "warning: whisper-cli is not in PATH - build whisper.cpp with CUDA: https://github.com/ggml-org/whisper.cpp"

mkdir -p "$HOME/.local/bin" "$HOME/.config/notat" "$MODEL_ROOT"

# 1. the command
ln -sf "$ROOT/notat" "$HOME/.local/bin/notat"
echo "notat -> $HOME/.local/bin/notat"

# 2. config (leave an existing one alone)
if [ ! -f "$HOME/.config/notat/config.json" ]; then
  cp "$ROOT/config.example.json" "$HOME/.config/notat/config.json"
  echo "wrote $HOME/.config/notat/config.json"
fi

# 3. the VAD model - without it whisper finds text in the silence
if [ ! -f "$VAD" ]; then
  echo "fetching the VAD model ..."
  curl -sL -o "$VAD" "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"
fi

# 4. a whisper model
if [ "${1:-}" != "--no-model" ]; then
  "$HOME/.local/bin/notat" download kb-whisper-small || echo "could not download the model - run: notat download kb-whisper-small"
  "$HOME/.local/bin/notat" model kb-whisper-small || true
fi

# 4b. speaker separation (sherpa-onnx + voice models, ~70 MB) - lets the document
#     write "Speaker 1, 2 ..." instead of a single "Meeting". No torch, no cloud service.
if [ "${1:-}" != "--no-model" ]; then
  "$HOME/.local/bin/notat" speakers fetch || echo "could not fetch the speaker separation - run: notat speakers fetch"
  "$HOME/.local/bin/notat" speakers on || true
fi

# 5. the bar button (Omarchy). Must be a real directory - validate refuses symlinks.
#    If it was fetched by `omarchy plugin add` it is under git and updated with
#    `omarchy plugin update <id>` - do not copy into it, it dirties the tree.
PLUG="$HOME/.config/omarchy/plugins/io.github.alexwest1981.omanotation"
if [ -d "$HOME/.config/omarchy/plugins" ]; then
  if [ -d "$PLUG/.git" ]; then
    echo "the bar button was fetched by Omarchy ($PLUG)"
    echo "  update it with: omarchy plugin update io.github.alexwest1981.omanotation"
  else
    mkdir -p "$PLUG"
    cp "$ROOT/BarWidget.qml" "$ROOT/manifest.json" "$PLUG/"
    echo "bar button copied to $PLUG (right-click the microphone icon picks sources, model and voices)"
  fi
  omarchy plugin enable io.github.alexwest1981.omanotation >/dev/null 2>&1 || true
  omarchy-restart-shell >/dev/null 2>&1 || true
fi

echo
echo "done. try:  notat devices   and   python3 test_notat.py"
