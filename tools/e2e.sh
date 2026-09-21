#!/usr/bin/env bash
# Ände-till-ände-prov: virtuell sink i båda benen, så inget ljud går ut i rummet
# och rummet inte spelas in. Kräver talsyntesfil: sätt PROV=<fil.mp3>.
set -u
PROV=${PROV:-}
[ -n "$PROV" ] && [ -f "$PROV" ] || { echo "sätt PROV=<ljudfil med tal>"; exit 2; }

MOD=$(pactl load-module module-null-sink sink_name=notat_test sink_properties=device.description=notat_test)
export NOTAT_SINK=notat_test NOTAT_SOURCE=notat_test.monitor

fail=0
notat start || fail=1
sleep 1
pw-play --target notat_test "$PROV" >/dev/null 2>&1
notat stop
notat status --json

pactl unload-module "$MOD"
unset NOTAT_SINK NOTAT_SOURCE

ny=$(ls -t "$HOME/Documents/OmaScribe Vault/Inspelningar/"*.md 2>/dev/null | head -1)
if [ -z "$ny" ]; then echo "FAIL: inget dokument skapades"; exit 1; fi
echo "dokument: $ny"
grep -q "Inget tal hittades" "$ny" && { echo "FAIL: inget tal hittades i inspelningen"; fail=1; }
grep -qE "\[[0-9]{2}:[0-9]{2}\] (Mötet|Du):" "$ny" || { echo "FAIL: dokumentet saknar transkription"; fail=1; }
[ "$fail" = 0 ] && echo "OK"
exit $fail
