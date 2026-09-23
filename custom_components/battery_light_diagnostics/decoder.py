"""Passive exact-signature decoder; bounds mirror battery-guard-1.4 guard.h.

No control actions. Correlation IDs group matching commands observed within 800ms;
they are reception groups, not proof of a single physical press.
"""
import uuid
import re
NAMES={0xE0960107:'Power On',0xE0961811:'Power Off',0xE0960304:'Color Plus',0xE0960500:'Color Minus',0xE0960603:'White',0xE096080E:'Warm',0xE096090F:'Motion On',0xE0960B0C:'Motion Off',0xE0960C09:'Timer 15',0xE0960E0B:'Timer 30',0xE0960F0A:'Timer 60',0xE096111F:'Timer 120'}
def stream_code(message):
    """Strict live Study firmware marker, never diagnostic candidate dumps."""
    clean=re.sub(r'\x1b\[[0-9;]*m','',message).strip()
    match=re.fullmatch(r'\[I\]\[battery_guard:\d+\]: BGSTREAM code=([0-9A-F]{8})',clean)
    code=int(match[1],16) if match else None
    return code if code in NAMES else None
def pulse(a,i):
    if i>=len(a):return 0,i
    value=a[i];i+=1
    while i+1<len(a) and ((value>0 and -150<=a[i]<0 and a[i+1]>0) or (value<0 and 0<a[i]<=150 and a[i+1]<0)):
        value+=a[i+1]-a[i];i+=2
    return value,i

def decode(a):
    found=[]
    for start in range(max(0,len(a)-66)):
        leader,i=pulse(a,start);gap,i=pulse(a,i)
        if not (3300<=leader<=4600 and -950<=gap<=-150):continue
        code=0
        for _ in range(32):
            high,i=pulse(a,i);low,i=pulse(a,i)
            if not -950<=low<=-150:break
            if 350<=high<=900:code<<=1
            elif 1250<=high<=2000:code=(code<<1)|1
            else:break
        else:
            trailer,i=pulse(a,i)
            if 1250<=trailer<=3000 and code in NAMES:found.append((start,code))
    return found

class Correlator:
    def __init__(self):self.recent={}
    def observe(self,code,now):
        previous=self.recent.get(code)
        group=previous[1] if previous and 0<=now-previous[0]<0.8 else uuid.uuid4().hex
        self.recent[code]=(now,group)
        return group
