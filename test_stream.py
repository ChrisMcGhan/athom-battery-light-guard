"""Exercise continuous decoding beyond RMT capacity without synthesizing live events."""
import gzip, importlib.util, json, pathlib, random, subprocess, tempfile
root=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('decoder',root/'custom_components/battery_light_diagnostics/decoder.py')
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
frames=json.loads((root/'samples/frames.json').read_text())
cases=[];expect=[]
def case(a,codes): cases.append(a);expect.append(codes)
for sample in frames.values():
    f=sample['timings_us'];code=decoder.decode(f)[0][1]
    case(f,[code])
    # Continuous noise longer than the entire RMT hardware allocation, then a command.
    case([80,-90]*2000+[-10000]+f,[code])
    case(f*4,[code]*4)
    for end in range(67): case(f[:end],[])
    # A lost queue segment must force resynchronization, never join its two sides.
    for split in range(1,67): case(f[:split]+[0]+f[split:]+[-10000]+f,[code])
    for scale in (.9,1.1):case([round(p*scale) for p in f],[code])
    for i in range(2,66,2):
        bad=f.copy();bad[i]=1100;case(bad,[])
    for i in range(67):
        p=f[i];sign=1 if p>0 else -1
        # Inject a 60us opposite glitch while preserving the original elapsed width.
        a=abs(p);left=(a-60)//2;right=a-60-left
        noisy=f[:i]+[sign*left,-sign*60,sign*right]+f[i+1:]
        case(noisy,[code])
rng=random.Random(43392)
for _ in range(1000):
    case([rng.randint(20,5000)*(1 if i%2==0 else -1) for i in range(rng.randint(10,2000))],[])
for path in ('/tmp/battery-good-20260920.jsonl.gz','/tmp/battery-20260921-224209.jsonl.gz'):
    for r in map(json.loads,gzip.open(path,'rt')):
        if r.get('kind')=='raw':case(r['timings_us'],[c for _,c in decoder.decode(r['timings_us'])])
with tempfile.TemporaryDirectory() as d:
    exe=str(pathlib.Path(d)/'stream')
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(root/'test_stream.cpp'),'-o',exe],check=True)
    result=subprocess.run([exe],input=''.join(str(len(a))+' '+' '.join(map(str,a))+'\n' for a in cases),text=True,capture_output=True,check=True)
    outputs=result.stdout.splitlines();assert len(outputs)==len(cases)
    for i,(actual,want) in enumerate(zip(outputs,expect)):
        got=[int(c,16) for c in actual.split()]
        assert got==want,(i,got,want,cases[i])
assert decoder.stream_code('\x1b[0;32m[I][battery_guard:123]: BGSTREAM code=E0960107\x1b[0m')==0xE0960107
for text in ('BGSTREAM code=E0960107','[I][battery_guard_diag:123]: BGSTREAM code=E0960107','[I][battery_guard:123]: BGSTREAM code=FFFFFFFF','[I][battery_guard:123]: BGSTREAM code=E0960107 junk'):
    assert decoder.stream_code(text) is None,text
print(f'{len(cases)} continuous-stream cases passed; live marker validation passed.')
