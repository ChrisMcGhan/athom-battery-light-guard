#include "guard.h"
#include <cassert>
#include <iostream>
#include <vector>
using namespace battery_guard;
int main(int argc,char**) {
 if(argc>1){size_t n;while(std::cin>>n){std::vector<int32_t>a(n);for(auto &v:a)std::cin>>v;for(size_t i=0;i+67<=n;i++){auto c=frame(a.data(),n,i);if(c)std::cout<<std::hex<<c<<' ';}std::cout<<'\n';}return 0;}
 Guard g;assert(!g.tick(1000));assert(g.receive(ON,1000));assert(g.remaining(1000)==300);
 assert(!g.receive(ON,1100));assert(g.started==1000);assert(!g.tick(11000));assert(g.active);
 assert(!g.tick(300999));assert(g.tick(301000));assert(!g.tick(301001));
 for(uint32_t t:{0xE0960C09u,0xE0960E0Bu,0xE0960F0Au,0xE096111Fu}){g.receive(ON,1000000);g.receive(t,1020000);assert(!g.active);assert(!g.tick(2000000));}
 g.receive(ON,3000000);g.receive(OFF,3001000);assert(!g.active);
 g.receive(ON,4000000);g.receive(0xE0960603,4001000);assert(g.active);assert(g.started==4000000);
 g.receive(ON,4003000);assert(g.started==4003000);
 Guard wrap;wrap.receive(ON,0xfffffff0u);assert(!wrap.tick(uint32_t(0xfffffff0u+299999u)));assert(wrap.tick(uint32_t(0xfffffff0u+300000u)));
 assert(sizeof(Guard)<=80);std::cout<<"State tests passed; Guard RAM "<<sizeof(Guard)<<" bytes on host\n";
}
