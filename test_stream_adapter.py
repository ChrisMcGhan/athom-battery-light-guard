"""Compile the real GPIO adapter with deterministic GPIO/clock stubs.

Unlike test_stream.py this executes edge_(), queue loss handling, and loop().
No network, transmitter, or Home Assistant action is involved.
"""
import json, pathlib, subprocess, tempfile
root=pathlib.Path(__file__).resolve().parent
component=root/'components/battery_light_stream'
with tempfile.TemporaryDirectory() as tmp:
    p=pathlib.Path(tmp);core=p/'esphome/core';core.mkdir(parents=True)
    (core/'component.h').write_text('''#pragma once
#define IRAM_ATTR
namespace esphome {
namespace setup_priority { constexpr float LATE=-100; }
class Component { public: virtual void setup(){} virtual void loop(){} virtual void dump_config(){} virtual void on_shutdown(){} virtual float get_setup_priority()const{return 0;} virtual ~Component()=default; };
}
''')
    (core/'gpio.h').write_text('''#pragma once
extern bool mock_level;
namespace esphome {
namespace gpio { enum InterruptType { INTERRUPT_ANY_EDGE }; }
class ISRInternalGPIOPin { public: bool digital_read(){return mock_level;} };
class InternalGPIOPin { public: void setup(){} ISRInternalGPIOPin to_isr(){return {};} template<class T> void attach_interrupt(void(*)(T*),T*,gpio::InterruptType){} void detach_interrupt(){} };
}
''')
    (core/'automation.h').write_text('''#pragma once
#include <vector>
namespace esphome { template<class T> class Trigger { public: std::vector<T> values; void trigger(T v){values.push_back(v);} }; }
''')
    (core/'hal.h').write_text('''#pragma once
#include <cstdint>
extern uint32_t mock_now;
namespace esphome { inline uint32_t micros(){return mock_now;} }
''')
    (core/'log.h').write_text('#pragma once\n#define ESP_LOGCONFIG(...) ((void)0)\n#define LOG_PIN(...) ((void)0)\n')
    harness=p/'adapter.cpp'
    harness.write_text('''#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>
bool mock_level=true;
uint32_t mock_now=0;
#include "battery_light_stream.cpp"
class TestReceiver: public esphome::battery_light_stream::StreamReceiver {
 public:
  void pulse(int32_t p) {
    assert((p>0)==mock_level);
    mock_now+=p>0?uint32_t(p):uint32_t(-p);
    mock_level=!mock_level;
    edge_(this);
  }
  void gap() {mock_now+=10;edge_(this);} // same level means a detected lost transition
};
int main() {
  {
    battery_light_stream_core::EdgeQueue<8> q;
    for(int round=0;round<100;++round) {
      for(int i=1;i<=7;++i)q.push(i);
      q.push(8);assert(q.loss_pending());
      int32_t p;
      for(int i=1;i<=7;++i){assert(q.pop(p));assert(p==i);}
      assert(!q.pop(p));q.push(9);
      assert(q.pop(p)&&p==0);assert(q.pop(p)&&p==9);assert(!q.pop(p));
      q.push(1);q.push(0);q.push(2);
      assert(q.pop(p)&&p==1);assert(q.pop(p)&&p==0);assert(q.pop(p)&&p==2);
    }
  }
  unsigned mode;size_t n;
  while(std::cin>>mode>>n) {
    std::vector<int32_t>a(n);for(auto &v:a)std::cin>>v;
    mock_level=true;mock_now=UINT32_MAX-1000;
    esphome::InternalGPIOPin pin;TestReceiver r;r.set_pin(&pin);r.setup();
    for(auto p:a) {if(p==0)r.gap();else r.pulse(p);if(mode==1)r.loop();}
    if(mode==2)r.gap();
    mock_now+=6001;
    for(int i=0;i<5;++i)r.loop();
    for(auto code:r.get_trigger()->values)std::cout<<std::hex<<code<<' '<<std::dec;
    std::cout<<'\\n';
  }
}
''')
    exe=p/'adapter'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable','-fsanitize=address,undefined','-I'+str(p),'-I'+str(component),'-I'+str(root),str(harness),'-o',str(exe)],check=True)
    cases=[];expected=[]
    for name,sample in json.loads((root/'samples/frames.json').read_text()).items():
        f=sample['timings_us'];code=sample['signature'].lower() if 'signature' in sample else None
        # derive expected only from known fixture bits, independently of adapter.
        value=0
        for i in range(2,66,2):value=(value<<1)|(f[i]>1000)
        code=f'{value:x}'
        for mode in (0,1,2):cases.append((mode,f));expected.append([code])
        # A complete frame before buffer exhaustion must survive later noise loss.
        cases.append((0,f+[80,-90]*1500));expected.append([code])
        for split in range(1,67):
            cases.append((0,f[:split]+[0]+f[split:]+f));expected.append([code])
    result=subprocess.run([str(exe)],input=''.join(f'{m} {len(a)} '+' '.join(map(str,a))+'\n' for m,a in cases),text=True,capture_output=True,check=True)
    failures=[(i,m,line.split(),want) for i,((m,a),line,want) in enumerate(zip(cases,result.stdout.splitlines(),expected)) if line.split()!=want]
    assert len(result.stdout.splitlines())==len(cases)
    if failures:raise AssertionError(f'{len(failures)} failures among {len(cases)} adapter cases; first: {failures[:5]}')
    print(f'{len(cases)} real-adapter cases passed: delayed drain, later loss, overflow, partial reset, clock rollover.')
