#!/usr/bin/env bash
# End-to-end test: a virtual sink in both legs, so no audio goes out into the room
# and the room is not recorded. Requires a speech file: set SAMPLE=<file.mp3>.
set -u
SAMPLE=${SAMPLE:-}
[ -n "$SAMPLE" ] && [ -f "$SAMPLE" ] || { echo "set SAMPLE=<audio file with speech>"; exit 2; }

MOD=$(pactl load-module module-null-sink sink_name=notat_test sink_properties=device.description=notat_test)
export NOTAT_SINK=notat_test NOTAT_SOURCE=notat_test.monitor
# the test run writes in its own vault if NOTAT_VAULT is set (otherwise Alex's real one)
VAULT="${NOTAT_VAULT:-$HOME/Documents/OmaScribe Vault}"

fail=0
notat start || fail=1
sleep 1
pw-play --target notat_test "$SAMPLE" >/dev/null 2>&1
# --wait: the test wants the document in hand, not just a receipt that the job started
notat stop --wait
notat status --json

pactl unload-module "$MOD"
unset NOTAT_SINK NOTAT_SOURCE

latest=$(ls -t "${VAULT:-$HOME/Documents/OmaScribe Vault}"/Recordings/*.md 2>/dev/null | head -1)
if [ -z "$latest" ]; then echo "FAIL: no document was created"; exit 1; fi
echo "document: $latest"
grep -q "No speech was found" "$latest" && { echo "FAIL: no speech was found in the recording"; fail=1; }
grep -qE "\[[0-9]{2}:[0-9]{2}\] (Meeting|You|Speaker [0-9]+):" "$latest" || { echo "FAIL: the document has no transcript"; fail=1; }
[ "$fail" = 0 ] && echo "OK"
exit $fail
