"""Check that passive GPIO traces preserve the actual decoder input."""
import json
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parent
sample = json.loads((root / "samples/frames.json").read_text())["Power On"]["timings_us"]
source = r'''
#include <iostream>
#include "edge_trace.h"
#include "stream_decoder.h"
int main() {
  battery_light_stream_core::EdgeTrace<4, 128> trace;
  battery_light_stream_core::Decoder decoder;
  int32_t value;
  while (std::cin >> value) {
    trace.observe(value);
    uint32_t starts = decoder.starts();
    uint32_t code = decoder.push(value);
    if (decoder.starts() != starts) trace.begin(1234, 5, 0);
    trace.progress(decoder.bits());
    if (code) trace.accepted(code);
  }
  uint32_t code = decoder.idle();
  if (code) trace.accepted(code);
  trace.idle();
  char out[1536];
  while (trace.next_dump(out, sizeof(out))) std::cout << out << '\n';
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    (p / "test.cpp").write_text(source)
    exe = p / "test"
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I" + str(root / "components/battery_light_stream"), str(p / "test.cpp"), "-o", str(exe)],
        check=True,
    )
    for pulses in (sample, [1800, -50, 2100] + sample[1:]):
        result = subprocess.run([str(exe)], input=" ".join(map(str, pulses)), text=True, capture_output=True, check=True)
        assert result.stdout.startswith("BGEDGE "), result.stdout
        trace = json.loads(result.stdout.removeprefix("BGEDGE "))
        assert trace["timings_us"] == [max(-32768, min(32767, n)) for n in pulses]
        assert trace["code"] == "E0960107" and trace["end"] == "idle"
        assert trace["discontinuities"] == 5 and trace["overflows"] == 0
        assert trace["bits"] == 32
    # Ambient noise that never gets past a leader is recorded but not reported.
    noise = [3950, -500, 520, -500, 5000, -20000]
    result = subprocess.run([str(exe)], input=" ".join(map(str, noise)), text=True, capture_output=True, check=True)
    assert result.stdout == "", result.stdout
    # A near miss (valid leader and several bits, then a corrupted bit) is reported with its progress.
    near = sample[:12] + [1100] + sample[13:]
    result = subprocess.run([str(exe)], input=" ".join(map(str, near)), text=True, capture_output=True, check=True)
    trace = json.loads(result.stdout.splitlines()[0].removeprefix("BGEDGE "))
    assert trace["code"] == "00000000" and trace["bits"] == 5, trace
    # Falling behind yields one summary line, then only retained traces: never one line per lost trace.
    result = subprocess.run([str(exe)], input=" ".join(map(str, sample * 10)), text=True, capture_output=True, check=True)
    lines = result.stdout.splitlines()
    assert json.loads(lines[0].removeprefix("BGEDGE ")) == {"lost_sequences": [1, 6]}, lines[0]
    assert len(lines) == 5 and all('"code":"E0960107"' in line for line in lines[1:]), lines
print("Passive GPIO trace preserves On frames, reports near misses, hides noise, and summarizes overwritten traces.")
