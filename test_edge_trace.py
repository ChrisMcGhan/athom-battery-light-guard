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
print("Passive GPIO trace preserves clean and folded-leader On frames with acceptance annotations.")
