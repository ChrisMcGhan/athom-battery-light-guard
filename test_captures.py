"""Validate the guard state machine, and the stream decoder against the included recorded frames."""
import json, pathlib, subprocess, tempfile
root = pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as tmp:
    exe = str(pathlib.Path(tmp) / 'test_guard')
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(root/'test_guard.cpp'), '-o', exe], check=True)
    subprocess.run([exe], check=True)
    decode = str(pathlib.Path(tmp) / 'test_stream')
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(root/'test_stream.cpp'), '-o', decode], check=True)
    samples = json.loads((root/'samples/frames.json').read_text())
    cases = [(v['timings_us'], v['signature'].lower()) for v in samples.values()]
    frame = samples['Power Off']['timings_us']
    cases += [(frame[:i], '') for i in range(67)]
    for i in range(2, 66, 2):
        bad = frame.copy()
        bad[i] = 1100
        cases.append((bad, ''))
    data = ''.join(str(len(a))+' '+' '.join(map(str, a))+'\n' for a, _ in cases)
    result = subprocess.run([decode], input=data, text=True, capture_output=True, check=True)
    lines = result.stdout.splitlines()
    assert len(lines) == len(cases)
    for line, (_, expected) in zip(lines, cases):
        assert line.strip() == expected, (line, expected)
    print(f'All {len(cases)} captured-frame and rejection cases passed.')
