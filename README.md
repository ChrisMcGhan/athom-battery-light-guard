# Athom battery-light guard

ESPHome firmware overlay for an Athom ESP32 RF/IR Remote. It listens for a specific 433.92 MHz battery-light remote and sends Power Off **five minutes after Power On**, unless a native timer button was heard. The countdown runs on the Athom; Home Assistant is optional for diagnostics.

Current version: **battery-guard-1.4**, built with **ESPHome 2026.9.0**.

## AI creation and human direction

The custom firmware overlay, RF decoder, tests, and project documentation were created with **OpenAI Codex** under the direction of **Chris McGhan**. Chris defined the requirements, operated the physical remote, and confirmed the observed light behavior during hardware testing. The underlying ESPHome platform and Athom configuration are third-party work credited below.

This AI contribution includes the initial firmware publication in commit `ba76704753258e49e1a84ba5103f4686c98957ee`, even though that commit originally listed only Chris as its author. AI-assisted commits can record Codex's contribution with this Git trailer:

```text
Co-authored-by: Codex <noreply@openai.com>
```

See [GitHub's co-author documentation](https://docs.github.com/en/pull-requests/how-tos/commit-changes/creating-a-commit-with-multiple-authors). Commit attribution and GitHub's repository Contributors display are separate; a trailer does not guarantee a particular sidebar listing.

## Behavior

- Power On starts/restarts a 300-second fallback from that press.
- The first 10 seconds display “Awaiting timer selection”; the countdown is already running.
- Any native 15/30/60/120-minute timer command cancels the fallback, including a later timer selection.
- Power Off cancels it. Color, white, warm, and motion commands do not alter it. Motion activation is outside the intended use: automatic motion activation cannot start this fallback.
- Repeated copies of the same command within 800 ms are deduplicated.
- On expiry, transmit the captured four-frame Power Off burst.
- No countdown is restored after reboot. Wi-Fi/API disconnection does not intentionally reboot the device.

This recognizes one captured remote command set, not all 433 MHz lights. Carrier frequency alone does not establish compatibility. A product/protocol identification has not been confirmed.

## Files

- `guard.h`: allocation-free pulse decoder and countdown state machine.
- `guard.yaml`: ESPHome overlay, Off waveform, and Home Assistant diagnostic entities.
- `fetch_stock.py`: fetches and verifies Athom's pinned configuration, generating `stock.yaml` with a pinned Flash_comp dependency.
- `samples/frames.json`: one recorded frame per button, stripped of capture metadata.
- `test_guard.cpp`, `test_captures.py`: state-machine and recorded-waveform tests.

The program retains upstream RF/IR and Bluetooth proxy features. It removes the vendor firmware-update entity because installing stock firmware would remove this overlay.

## Build and install

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 fetch_stock.py
esphome config guard.yaml
esphome compile guard.yaml
esphome upload guard.yaml --device YOUR_ATHOM_IP
```

Provision the device's Wi-Fi using the supported Athom/ESPHome provisioning flow. No Wi-Fi credentials, API credentials, or device-specific addresses are supplied here. Confirm your hardware is the compatible ESP32 Athom RF/IR Remote before installing. Upload only to your intended device; OTA restarts it and clears any active fallback.

## Tests and verification

```sh
python3 test_captures.py
```

Requires a C++17 compiler named `c++` on PATH. Tests cover the five-minute boundary, cancellation by all four timers and Off, repeated frames, restart, unrelated commands, clock rollover, twelve captured command signatures, truncation, and invalid pulses.

Live hardware testing confirmed remote Power On recognition, native Timer 30 cancellation, and a complete physical automatic-shutoff cycle with the earlier 15-minute version. Version 1.3 changes the deadline and diagnostic text to five minutes; its boundary tests pass, but a complete five-minute physical cycle has not yet been documented. Repeated-trial and range reliability remain unmeasured.

## Diagnostics and limitations

Home Assistant receives last command, protection status, last action, remaining seconds, and command count through the ESPHome native API. These describe commands heard/sent, not measured lamp state. The receiver may hear its own Off transmission and then report `Power Off heard` / `Idle`. There is no lamp acknowledgment. Missed RF commands, loss of power, or a reboot can defeat the fallback; this is a convenience feature.

The decoder uses a 6 ms receive gap, folds isolated glitches up to 150 microseconds, and requires a known complete 32-bit signature with leader and trailer. The signature is a recognition convention, not a claim of a fully documented protocol. Transmit timings have different polarity/alignment from the plotted receiver samples.

![Recorded waveforms](samples/waveforms.png)

## Upstream attribution

Base configuration and Flash_comp: [athom-tech/esp32-configs](https://github.com/athom-tech/esp32-configs), pinned at `6181202ed9fe274c3f994112ef3b847f295dd9f4`. These third-party sources are fetched by `fetch_stock.py` and during the build and are not vendored here. ESPHome: https://github.com/esphome/esphome.


## Passive diagnostics and missed-press reports (v1.4)

Keep the remote in its normal location. The five-minute control logic and decoder are unchanged; diagnostics observe normal use.

### Where records live

- **Athom RAM:** a fixed 4,116-byte ring stores the latest 12 plausible remote-frame candidates, with up to 160 pulse durations each, partial decoded code, rejection reason, sequence number, and device uptime. The logger/counters/API add some overhead beyond the ring. No diagnostic writes go to Athom flash. A reboot loses this buffer; overflow replaces the oldest candidate and increments an exposed counter.
- **Home Assistant disk:** the optional custom integration continuously subscribes to the native RF stream, including noise/noncandidate bursts, records selected state changes and device logs, and requests a ring dump every minute and after reconnect. The private SQLite file is `/config/battery_light_diagnostics/rolling.sqlite3`. Records are committed with SQLite FULL synchronization in batches every two seconds, off the HA event loop. Up to two seconds of queued data can be lost on abrupt power failure. A 512-record queue bounds memory; dropped-record counts and connection gaps are visible.
- **Retention:** rolling payload is capped at 256 MiB or seven days, whichever limit comes first. SQLite is capped at 512 MiB of pages; its reusable allocated file space can exceed current payload. The status sensor shows actual oldest/newest available records. Continuous noise means seven days is not guaranteed.
- **Incidents:** the Report Missed On button saves the preceding 60 minutes to a separate compressed JSONL file under `/config/battery_light_diagnostics/incidents/`. Keep the latest 20 incidents, each limited to 64 MiB of uncompressed records; truncation is explicitly recorded. These files are not removed when the rolling log rotates. They are not automatically uploaded anywhere. Copy important incidents elsewhere before the 20-report retention limit.

Install `custom_components/battery_light_diagnostics` in HA's `/config/custom_components`, adapt `home-assistant.example.yaml` with your own secrets, check the HA configuration, and restart HA. The integration depends on the existing ESPHome integration's API library and opens one additional native-API connection. No MQTT broker or permission for the Athom to execute HA actions is required.

HA entities:

- `sensor.battery_light_rf_recorder`: recording/disconnected/error, queue drops, retention bounds, and latest incident path.
- `button.battery_light_report_missed_on`: records your report, requests the available RAM buffer, and preserves the recent window. It does not transmit Power On or Off.
- The firmware adds raw-burst, rejected-candidate, receiver-error, and overwritten-candidate counters.

For a delayed report, call `battery_light_diagnostics.report_missed_on` with `lookback_minutes` (1–1440) and a `note`. The action optionally returns the incident path, count, and truncation status. Normal HA backups that include the configuration directory should include these private files; they are not a substitute for an independently verified backup.

The Athom cannot detect a press it never hears. An owner report is the reference observation. A candidate filter can miss badly damaged frames, which is why HA retains the full raw stream. During an HA/network outage, only the bounded candidate ring remains; complete raw recording resumes after reconnect. `Power Off heard` may be the Athom hearing its own transmission rather than the remote. Diagnostic record timestamps distinguish HA wall-clock receipt time from the device uptime in buffered records.

Additional tests:

```sh
c++ -std=c++17 -Wall -Wextra -Werror test_diagnostics.cpp -o /tmp/test_diagnostics
/tmp/test_diagnostics
python3 test_storage.py
```

The ring tests cover acceptance/rejection, wrapping, overwritten snapshot records, and memory bounds. Storage tests cover bounded retention, reopening, preserved incidents, and incident rotation.

Deployment validation on September 19, 2026: v1.4 compiled successfully (about 1.49 MB firmware), was read back on the device, and the HA recorder persisted raw RF and state records across the firmware reboot. The snapshot action is asynchronous: it emits log records and does not return an API action response. The unchanged decoder/control tests and new buffer/storage tests pass. No new physical range or shutoff reliability claim is made.
