#include "guard.h"
#include <cassert>
#include <iostream>
using namespace battery_guard;
int main() {
 Guard g;assert(!g.tick(1000));assert(g.receive(ON,1000));assert(g.remaining(1000)==300);
 assert(!g.receive(ON,1100));assert(g.started==1000);assert(!g.tick(11000));assert(g.active);
 assert(!g.tick(300999));assert(g.tick(301000));assert(!g.tick(301001));
 for(uint32_t t:{0xE0960C09u,0xE0960E0Bu,0xE0960F0Au,0xE096111Fu}){g.receive(ON,1000000);g.receive(t,1020000);assert(!g.active);assert(!g.tick(2000000));}
 g.receive(ON,3000000);g.receive(OFF,3001000);assert(!g.active);
 g.receive(ON,4000000);g.receive(0xE0960603,4001000);assert(g.active);assert(g.started==4000000);
 g.receive(ON,4003000);assert(g.started==4003000);
 Guard wrap;wrap.receive(ON,0xfffffff0u);assert(!wrap.tick(uint32_t(0xfffffff0u+299999u)));assert(wrap.tick(uint32_t(0xfffffff0u+300000u)));
 // Each visible change is published exactly once: arm, the 10s status step, expiry, duplicates ignored.
 Guard p;uint32_t c=p.changes;p.receive(ON,0);assert(p.changes==++c);p.receive(ON,100);assert(p.changes==c);
 p.tick(5000);assert(p.changes==c);p.tick(10000);assert(p.changes==++c);p.tick(20000);assert(p.changes==c);
 assert(p.tick(300000));assert(p.changes==++c);p.manual_off();assert(p.changes==++c&&!p.active);
 // Recovery: never while a fallback is pending, only after the full offline limit, reset by reconnection.
 Recovery r;assert(!r.should_restart(true,false,0));assert(!r.should_restart(false,false,1000));
 assert(!r.should_restart(false,false,600999));assert(r.should_restart(false,false,601000));
 assert(!r.should_restart(false,true,900000));assert(!r.should_restart(true,false,900001));
 assert(!r.should_restart(false,false,900002));assert(!r.should_restart(false,false,1500001));assert(r.should_restart(false,false,1500002));
 Recovery w;w.should_restart(false,false,0xfffffff0u);assert(!w.should_restart(false,false,uint32_t(0xfffffff0u+599999u)));assert(w.should_restart(false,false,uint32_t(0xfffffff0u+600000u)));
 assert(sizeof(Guard)<=80);std::cout<<"State tests passed; Guard RAM "<<sizeof(Guard)<<" bytes on host\n";
}
