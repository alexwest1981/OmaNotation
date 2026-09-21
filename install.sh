#!/usr/bin/env bash
# Installerar notat: kommandot, VAD-modellen, en whisper-modell och bar-knappen i Omarchy.
#   ./install.sh            (laddar ner kb-whisper-small, 466 MB)
#   ./install.sh --ingen-modell
set -euo pipefail

ROT="$(cd "$(dirname "$0")" && pwd)"
MODELL_ROT="$HOME/.local/share/notat/models"
VAD="$MODELL_ROT/ggml-silero-v5.1.2.bin"

behövs() {
  command -v "$1" >/dev/null || { echo "saknas: $1  ->  $2"; exit 1; }
}
behövs python3 "installera python3"
behövs ffmpeg "pacman -S ffmpeg"
behövs pactl "pacman -S pipewire-pulse  (pactl följer med)"
command -v whisper-cli >/dev/null || echo "varning: whisper-cli saknas i PATH - bygg whisper.cpp med CUDA: https://github.com/ggml-org/whisper.cpp"

mkdir -p "$HOME/.local/bin" "$HOME/.config/notat" "$MODELL_ROT"

# 1. kommandot
ln -sf "$ROT/notat" "$HOME/.local/bin/notat"
echo "notat -> $HOME/.local/bin/notat"

# 2. config (rör inte en befintlig)
if [ ! -f "$HOME/.config/notat/config.json" ]; then
  cp "$ROT/config.example.json" "$HOME/.config/notat/config.json"
  echo "skrev $HOME/.config/notat/config.json"
fi

# 3. VAD-modellen - utan den hittar whisper på text i tystnaden
if [ ! -f "$VAD" ]; then
  echo "hämtar VAD-modellen ..."
  curl -sL -o "$VAD" "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"
fi

# 4. en whisper-modell
if [ "${1:-}" != "--ingen-modell" ]; then
  "$HOME/.local/bin/notat" hamta kb-whisper-small || echo "kunde inte ladda ner modellen - kör: notat hamta kb-whisper-small"
  "$HOME/.local/bin/notat" modell kb-whisper-small || true
fi

# 5. bar-knappen (Omarchy). Måste vara en riktig mapp - validate vägrar symlänkar.
if [ -d "$HOME/.config/omarchy/plugins" ]; then
  PLUG="$HOME/.config/omarchy/plugins/custom.notat"
  mkdir -p "$PLUG"
  cp "$ROT/bar/custom.notat/BarWidget.qml" "$ROT/bar/custom.notat/manifest.json" "$PLUG/"
  omarchy plugin enable custom.notat >/dev/null 2>&1 || true
  omarchy-restart-shell >/dev/null 2>&1 || true
  echo "bar-knappen installerad (högerklick på mikrofonikonen väljer källor och modell)"
  echo "  uppdatera senare genom att köra ./install.sh igen (filerna kopieras)"
fi

echo
echo "klart. prova:  notat devices   och   python3 test_notat.py"
