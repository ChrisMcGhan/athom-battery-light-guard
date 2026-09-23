# Athom battery-light guard

ESPHome firmware overlay for an Athom ESP32 RF/IR Remote. It listens for a specific 433.92 MHz battery-light remote and sends Power Off **five minutes after Power On**, unless a native timer button was heard. The countdown runs on the Athom; Home Assistant is optional for diagnostics.

Current version: **battery-guard-1.10**, built with **ESPHome 2026.9.0**.

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
- No countdown is restored after reboot. Wi-Fi/API disconnection alone never reboots the device. Since v1.10, an Athom that has had no Home Assistant connection for 10 minutes restarts itself, but only while no fallback countdown is pending.

This recognizes one captured remote command set, not all 433 MHz lights. Carrier frequency alone does not establish compatibility. A product/protocol identification has not been confirmed.

## Files

- `guard.h`: command whitelist, countdown state machine, and offline-recovery rule.
- `guard.yaml`: ESPHome overlay, Off waveform, and Home Assistant diagnostic entities.
- `components/battery_light_stream`: continuous GPIO edge capture, exact stream decoder, ordered-loss queue, and bounded pre-decoder traces.
- `custom_components/battery_light_diagnostics`: multi-receiver Home Assistant recorder, exact host-side decoder, shared recognized events, and incident exports.
- `fetch_stock.py`: fetches and verifies Athom's pinned configuration, generating `stock.yaml` with a pinned Flash_comp dependency.
- `samples/frames.json`: one recorded frame per button, stripped of capture metadata.
- `test_guard.cpp`, `test_captures.py`, `test_stream*.py`, `test_edge_trace.py`, `test_multi_receiver.py`, `test_recorder.py`, and `test_storage.py`: state, recovery, decoder, stream, queue-loss, trace, recorder, and storage tests.

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
python3 test_stream.py
python3 test_stream_adapter.py
python3 test_edge_trace.py
python3 test_multi_receiver.py
python3 test_recorder.py
python3 test_storage.py
```

Requires a C++17 compiler named `c++` on PATH. Tests cover the five-minute boundary, cancellation by all four timers and Off, repeated frames, restart, unrelated commands, clock rollover, publish-on-change, the offline-recovery rule, twelve captured command signatures, truncation, and invalid pulses. `test_recorder.py` needs Home Assistant's Python dependencies (such as `voluptuous`) installed.

Live hardware testing confirmed remote Power On recognition, native Timer 30 cancellation, and a complete physical automatic-shutoff cycle with the earlier 15-minute version. Version 1.3 changes the deadline and diagnostic text to five minutes; its boundary tests pass, but a complete five-minute physical cycle has not yet been documented. Repeated-trial and range reliability remain unmeasured.

## Diagnostics and limitations

Home Assistant receives last command, protection status, last action, remaining seconds, and command count through the ESPHome native API. Since v1.10, command, status, action, and count are published when they change rather than polled every second, so a short-lived state such as `Fallback expired: transmitting Power Off` is no longer overwritten before HA sees it. These describe commands heard/sent, not measured lamp state. The receiver may hear its own Off transmission and then report `Power Off heard` / `Idle`. There is no lamp acknowledgment. Missed RF commands, loss of power, or a reboot can defeat the fallback; this is a convenience feature.

The continuous GPIO edge path (added in v1.6) is the only battery-light decoder since v1.10. It folds isolated glitches up to 150 microseconds and requires a known complete 32-bit signature with leader and trailer. The RMT receiver keeps its 6 ms receive gap and 250 microsecond post-capture filter for learning and the RF proxy that feeds Home Assistant's raw recorder, but no longer decodes battery-light frames. The signature is a recognition convention, not a claim of a fully documented protocol. Transmit timings have different polarity/alignment from the plotted receiver samples.

![Recorded waveforms](samples/waveforms.png)

## Upstream attribution

Base configuration and Flash_comp: [athom-tech/esp32-configs](https://github.com/athom-tech/esp32-configs), pinned at `6181202ed9fe274c3f994112ef3b847f295dd9f4`. These third-party sources are fetched by `fetch_stock.py` and during the build and are not vendored here. ESPHome: https://github.com/esphome/esphome.


## Version history after v1.4

- **v1.5:** raises the existing RMT output filter to 250 microseconds. Source review established that the setting primarily filters after capture on classic ESP32 hardware; it does not prevent the finite RMT symbol memory from filling.
- **v1.6:** adds an independent continuous GPIO edge receiver with a bounded 2,048-edge queue and exact command whitelist. The existing RMT learning, proxy, RF transmit, IR, Bluetooth, and five-minute fallback paths remain available.
- **v1.7:** records queue loss in chronological order so a later overflow cannot erase a complete command already waiting ahead of it.
- **v1.8:** adds bounded pre-decoder `BGEDGE` traces for the GPIO path without changing command acceptance.
- **v1.9:** starts those traces at the decoder's actual leader transition and includes the preceding 16 pulses, covering leaders reconstructed around a short opposite-polarity glitch.
- **v1.10:** fixes repeated out-of-memory aborts. A decoded v1.9 backtrace showed `abort()` from `operator new` while ESPHome copied each RMT burst into the `on_raw` lambda, several times a second on ambient noise. v1.10 removes that duplicate RMT decoder and the RMT candidate ring (`diagnostics.h`, the `diagnostic_snapshot` action, and the raw-burst, rejected-candidate, and overwrite counters). `BGEDGE` traces drop from 16 to 4 records, report only accepted frames or traces that reached four valid data bits, and summarize overwritten traces in one `lost_sequences` line instead of one line each. Guard state is published on change. A `Heap Max Block` sensor reports the largest allocatable block. A guard-aware restart recovers a device that has lost Home Assistant for 10 minutes while idle. Command acceptance and the five-minute logic are unchanged.

The current Home Assistant component accepts multiple receivers, decodes every native RF callback against the exact signature set, tags records by receiver and capture, correlates repeated copies within 800 ms, and emits `battery_light_rf_recognized` for accepted commands. Validated `BGSTREAM` markers from the custom firmware join the same event path. Correlation is based on Home Assistant arrival time; it is not proof that records came from one physical press or that receiver clocks are synchronized.

## Passive diagnostics and missed-press reports

Keep the remote in its normal location. The five-minute control logic and decoder are unchanged; diagnostics observe normal use.

### Where records live

- **Athom RAM:** the continuous path has a bounded 2,048-edge queue and four bounded 128-pulse diagnostic traces. No diagnostic writes go to Athom flash. A reboot loses these buffers; counters expose overflow, discontinuity, and trace activity.
- **Home Assistant disk:** the optional custom integration connects directly to each configured receiver through the native ESPHome API. It records RF callbacks, exact recognized commands, selected state changes, device logs, receiver identity, and connection gaps. The private SQLite file is `/config/battery_light_diagnostics/rolling.sqlite3`. Records are committed with SQLite FULL synchronization in batches every two seconds, off the HA event loop. Up to two seconds of queued data can be lost on abrupt power failure. A 512-record queue bounds memory; dropped-record counts and per-receiver status are visible.
- **Retention:** rolling payload is capped at 256 MiB or seven days, whichever limit comes first. SQLite is capped at 512 MiB of pages; its reusable allocated file space can exceed current payload. The status sensor shows actual oldest/newest available records. Continuous noise means seven days is not guaranteed.
- **Incidents:** the Report Missed On button saves the preceding 60 minutes to a separate compressed JSONL file under `/config/battery_light_diagnostics/incidents/`. Keep the latest 20 incidents, each limited to 64 MiB of uncompressed records; truncation is explicitly recorded. These files are not removed when the rolling log rotates. They are not automatically uploaded anywhere. Copy important incidents elsewhere before the 20-report retention limit.

Install `custom_components/battery_light_diagnostics` in HA's `/config/custom_components`, adapt `home-assistant.example.yaml` with your own secrets, check the HA configuration, and restart HA. The integration depends on the existing ESPHome integration's API library and opens one additional native-API connection per configured receiver. No MQTT broker or permission for an Athom to execute HA actions is required.

HA entities:

- `sensor.battery_light_rf_recorder`: recording/disconnected/error, queue drops, retention bounds, and latest incident path.
- `button.battery_light_report_missed_on`: records your report and preserves the recent window. It does not transmit Power On or Off. (Firmware before v1.10 also offered a RAM candidate snapshot; the integration skips that request when a receiver does not provide it.)
- The firmware adds stream edge, overflow, discontinuity, frame, trace, and receiver-error counters, and a `Heap Max Block` sensor.

For a delayed report, call `battery_light_diagnostics.report_missed_on` with `lookback_minutes` (1–1440) and a `note`. The action optionally returns the incident path, count, and truncation status. Normal HA backups that include the configuration directory should include these private files; they are not a substitute for an independently verified backup.

The Athom cannot detect a press it never hears. An owner report is the reference observation. A candidate filter can miss badly damaged frames, which is why HA retains the full raw stream. During an HA/network outage, only the four bounded edge traces remain on the device; complete raw recording resumes after reconnect. `Power Off heard` may be the Athom hearing its own transmission rather than the remote. Diagnostic record timestamps distinguish HA wall-clock receipt time from the device uptime in buffered records.

Additional tests:

Storage tests (`test_storage.py`) cover bounded retention, reopening, preserved incidents, and incident rotation.

Deployment validation through September 22, 2026: v1.9 compiled and was read back from the intended device; the Home Assistant recorder retained active records from three connected receivers with no reported storage drops. Stream, queue-loss, trace, decoder, and recorder tests pass. This verifies software operation and storage, not reliable recognition of every physical transmission. Private operational captures, device addresses, credentials, and compiled firmware are intentionally excluded from this repository.
