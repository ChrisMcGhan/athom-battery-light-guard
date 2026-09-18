"""Fetch the pinned upstream base without vendoring third-party source."""
import hashlib
import pathlib
import urllib.request
COMMIT = "6181202ed9fe274c3f994112ef3b847f295dd9f4"
EXPECTED_SHA256 = "d8b75bdaf1f03ed2422ed9b8b1dc347e998b2451d56ebb48a07ddaf00a132c70"
url = f"https://raw.githubusercontent.com/athom-tech/esp32-configs/{COMMIT}/athom-rf-ir-remote.yaml"
data = urllib.request.urlopen(url, timeout=30).read()
assert hashlib.sha256(data).hexdigest() == EXPECTED_SHA256, "Upstream source checksum mismatch"
text = data.decode().replace("github://athom-tech/esp32-configs@main", f"github://athom-tech/esp32-configs@{COMMIT}")
pathlib.Path(__file__).with_name("stock.yaml").write_text(text)
print("Fetched verified pinned Athom configuration")
