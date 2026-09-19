#include "diagnostics.h"
#include <cassert>
#include <iostream>
#include <vector>
int main(){
 using namespace battery_guard;
 std::vector<int32_t>a{4000,-500};
 for(int b=31;b>=0;--b){a.push_back((ON>>b)&1?1600:500);a.push_back(-500);}a.push_back(1600);a.push_back(-6000);
 Diagnostics d;d.observe(a.data(),a.size(),42);assert(d.accepted_frames==1);assert(d.raw_bursts==1);
 char out[1536];d.request_dump();assert(d.next_dump(out,sizeof(out)));assert(std::strstr(out,"accepted"));assert(!d.next_dump(out,sizeof(out)));
 a[12]=1100;d.observe(a.data(),a.size(),43);assert(d.rejected_frames==1);assert(d.records[1].reason==4);
 for(int i=0;i<30;++i)d.observe(a.data(),a.size(),44+i);
 d.request_dump();int dumped=0;while(d.next_dump(out,sizeof(out))){assert(std::strstr(out,"timings_us"));++dumped;}assert(dumped==12);
 d.request_dump();for(int i=0;i<13;++i)d.observe(a.data(),a.size(),100+i);assert(d.next_dump(out,sizeof(out)));assert(std::strstr(out,"lost_sequence"));
 std::cout<<"Diagnostic ring tests passed; RAM "<<sizeof(Diagnostics)<<" bytes\n";
}
