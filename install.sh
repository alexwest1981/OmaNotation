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

# 4b. talaruppdelningen (sherpa-onnx + röstmodeller, ~70 MB) - gör att dokumentet kan
#     skriva "Deltagare 1, 2 ..." i stället för ett enda "Mötet". Ingen torch, ingen molntjänst.
if [ "${1:-}" != "--ingen-modell" ]; then
  "$HOME/.local/bin/notat" diar-hamta || echo "kunde inte hämta talaruppdelningen - kör: notat diar-hamta"
  "$HOME/.local/bin/notat" röster på || true
fi

# 5. bar-knappen (Omarchy). Måste vara en riktig mapp - validate vägrar symlänkar.
#    Är den hämtad av `omarchy plugin add` ligger den under git och uppdateras med
#    `omarchy plugin update <id>` - kopiera inte in i den, det gör trädet smutsigt.
PLUG="$HOME/.config/omarchy/plugins/io.github.alexwest1981.omanotation"
if [ -d "$HOME/.config/omarchy/plugins" ]; then
  if [ -d "$PLUG/.git" ]; then
    echo "bar-knappen är hämtad av Omarchy ($PLUG)"
    echo "  uppdatera den med: omarchy plugin update io.github.alexwest1981.omanotation"
  else
    mkdir -p "$PLUG"
    cp "$ROT/BarWidget.qml" "$ROT/manifest.json" "$PLUG/"
    echo "bar-knappen kopierad till $PLUG (högerklick på mikrofonikonen väljer källor, modell och röster)"
  fi
  omarchy plugin enable io.github.alexwest1981.omanotation >/dev/null 2>&1 || true
  omarchy-restart-shell >/dev/null 2>&1 || true
fi

echo
echo "klart. prova:  notat devices   och   python3 test_notat.py"
