#pragma once
#include "guard.h"
#include <cstdio>
#include <cstring>
namespace battery_guard {
// Fixed RAM ring: no flash writes, allocation, or changes to decoding/control.
struct DiagnosticRecord {
 uint32_t sequence=0, uptime_ms=0, code=0;
 uint16_t original_length=0, stored_length=0;
 uint8_t reason=0, bit=0;
 int16_t timings[160]{};
};
struct Diagnostics {
 static constexpr size_t CAPACITY=12;
 DiagnosticRecord records[CAPACITY]{};
 uint32_t sequence=0, raw_bursts=0, candidates=0, accepted_frames=0;
 uint32_t rejected_frames=0, receiver_errors=0, last_rx_ms=0, dump_next=0, dump_end=0;
 static const char *reason_name(uint8_t r) {
  const char *names[]={"accepted","truncated","leader","space","mark","trailer","unknown_code"};
  return r<7?names[r]:"unknown";
 }
 static uint8_t inspect(const int32_t *a,size_t n,uint32_t &code,uint8_t &bit) {
  if(n<67)return 1;
  size_t i=0;int32_t h=pulse(a,n,i),l=pulse(a,n,i);
  if(h<3300||h>4600||l>-150||l<-950)return 2;
  code=0;
  for(bit=0;bit<32;++bit){h=pulse(a,n,i);l=pulse(a,n,i);
   if(l < -950||l > -150)return 3;
   if(h>=350&&h<=900)code<<=1;
   else if(h>=1250&&h<=2000)code=(code<<1)|1;
   else return 4;
  }
  h=pulse(a,n,i);if(h<1250||h>3000)return 5;
  return name(code)?0:6;
 }
 void observe(const int32_t *a,size_t n,uint32_t now) {
  ++raw_bursts;last_rx_ms=now;
  for(size_t i=0;i+3<n;++i){
   // Broad candidate gate. HA separately retains all raw bursts, even without a leader.
   if(a[i]<3000||a[i]>5000||a[i+1]>=0||a[i+1]<-1200)continue;
   unsigned plausible=0;
   for(size_t j=i+2;j<n&&j<i+18;j+=2)if(a[j]>=250&&a[j]<=2200)++plausible;
   if(plausible<4)continue;
   auto &r=records[sequence%CAPACITY];r.sequence=++sequence;r.uptime_ms=now;
   r.original_length=static_cast<uint16_t>(n-i);r.stored_length=static_cast<uint16_t>((n-i)>160?160:n-i);
   r.bit=0;r.code=0;r.reason=inspect(a+i,n-i,r.code,r.bit);
   ++candidates;if(r.reason==0)++accepted_frames;else ++rejected_frames;
   for(size_t j=0;j<r.stored_length;++j){int32_t v=a[i+j];r.timings[j]=static_cast<int16_t>(v>32767?32767:v < -32768?-32768:v);}
  }
 }
 void request_dump(){dump_end=sequence;dump_next=sequence>CAPACITY?sequence-CAPACITY+1:1;}
 bool next_dump(char *out,size_t capacity) {
  if(!dump_next||dump_next>dump_end)return false;
  uint32_t wanted=dump_next++;const auto &r=records[(wanted-1)%CAPACITY];
  if(r.sequence!=wanted){std::snprintf(out,capacity,"BGDIAG {\"lost_sequence\":%lu}",static_cast<unsigned long>(wanted));return true;}
  int used=std::snprintf(out,capacity,"BGDIAG {\"sequence\":%lu,\"uptime_ms\":%lu,\"reason\":\"%s\",\"bit\":%u,\"code\":\"%08lX\",\"original_length\":%u,\"timings_us\":[",static_cast<unsigned long>(r.sequence),static_cast<unsigned long>(r.uptime_ms),reason_name(r.reason),r.bit,static_cast<unsigned long>(r.code),r.original_length);
  if(used<0||static_cast<size_t>(used)>=capacity)return false;
  size_t pos=static_cast<size_t>(used);
  for(size_t i=0;i<r.stored_length;++i){int wrote=std::snprintf(out+pos,capacity-pos,"%s%d",i?",":"",r.timings[i]);if(wrote<0||static_cast<size_t>(wrote)>=capacity-pos)return false;pos+=wrote;}
  if(capacity-pos<3)return false;std::memcpy(out+pos,"]}",3);return true;
 }
};
static_assert(sizeof(Diagnostics)<=4608,"Diagnostic ring must stay bounded");
inline Diagnostics diagnostics;
}
