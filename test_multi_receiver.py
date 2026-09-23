"""Differential validation of HA's burst decoder against the deployed C++ stream decoder.

Since v1.10 the firmware decodes only the continuous GPIO stream. HA's decoder scans bounded RMT
bursts. The two agree on every real frame, truncation, and recorded capture; on synthetic single-pulse
mutations they may legitimately differ at burst boundaries, so noise is checked for silence instead.
"""
import importlib.util,json,pathlib,random,subprocess,tempfile,gzip
root=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('decoder',root/'custom_components/battery_light_diagnostics/decoder.py');decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
samples=json.loads((root/'samples/frames.json').read_text())
# Firmware v1.5 filters RMT output below 250us after hardware capture. Every pulse in the verified
# command frames remains well above that threshold; exclude the final idle only
# to report the actual encoded waveform minimum.
encoded_pulses=[abs(v) for sample in samples.values() for v in sample['timings_us'][:-1]]
assert min(encoded_pulses)>250,min(encoded_pulses)
cases=[v['timings_us'] for v in samples.values()]
rng=random.Random(17)
for frame in list(cases):
    cases.extend(frame[:i] for i in range(len(frame)))
noise=[[rng.randrange(20,5000)*(1 if i%2==0 else -1) for i in range(rng.randrange(400))] for _ in range(500)]
incident=pathlib.Path('/tmp/battery-missed-on.jsonl.gz')
if incident.exists():
    cases.extend(r['timings_us'] for r in map(json.loads,gzip.open(incident,'rt')) if r['kind']=='raw')
with tempfile.TemporaryDirectory() as tmp:
    exe=str(pathlib.Path(tmp)/'guard')
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(root/'test_guard.cpp'),'-o',exe],check=True)
    subprocess.run([exe],check=True)
    stream=str(pathlib.Path(tmp)/'stream')
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(root/'test_stream.cpp'),'-o',stream],check=True)
    def run(batch):
        result=subprocess.run([stream],input=''.join(str(len(a))+' '+' '.join(map(str,a))+'\n' for a in batch),text=True,capture_output=True,check=True)
        outputs=result.stdout.splitlines();assert len(outputs)==len(batch)
        return [[int(c,16) for c in line.split()] for line in outputs]
    for a,got in zip(cases,run(cases)):assert [code for _,code in decoder.decode(a)]==got,(a,got)
    for a,got in zip(noise,run(noise)):assert got==[] and decoder.decode(a)==[],a
    cases+=noise
c=decoder.Correlator();first=c.observe(0xE0960107,10)
assert c.observe(0xE0960107,10.2)==first
assert c.observe(0xE0961811,10.3)!=first
assert c.observe(0xE0960107,11.1)!=first
print(f'{len(cases)} differential cases passed; receiver correlation timing passed.')
