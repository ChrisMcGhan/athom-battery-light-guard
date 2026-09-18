#pragma once
#include <cstdint>
#include <cstddef>
namespace battery_guard {
constexpr uint32_t ON=0xE0960107, OFF=0xE0961811;
inline const char *name(uint32_t c) {
 switch(c) {
 case ON:return "Power On";case OFF:return "Power Off";
 case 0xE0960304:return "Color Plus";case 0xE0960500:return "Color Minus";
 case 0xE0960603:return "White";case 0xE096080E:return "Warm";
 case 0xE096090F:return "Motion On";case 0xE0960B0C:return "Motion Off";
 case 0xE0960C09:return "Timer 15";case 0xE0960E0B:return "Timer 30";
 case 0xE0960F0A:return "Timer 60";case 0xE096111F:return "Timer 120";
 default:return nullptr;
 }
}
inline bool timer(uint32_t c) {return c==0xE0960C09||c==0xE0960E0B||c==0xE0960F0A||c==0xE096111F;}
// Scan complete received frames, including frames embedded in noisy RF bursts.
// Fold isolated <=150us opposite-polarity glitches into the surrounding pulse.
// Work on the input directly: no extra capture buffer or heap allocation.
inline int32_t pulse(const int32_t *a,size_t n,size_t &i) {
 if(i>=n)return 0;
 int32_t value=a[i++];
 while(i+1<n && ((value>0 && a[i]<0 && a[i]>=-150 && a[i+1]>0) ||
                 (value<0 && a[i]>0 && a[i]<=150 && a[i+1]<0))) {
  value += a[i+1]-a[i];i+=2;
 }
 return value;
}
inline uint32_t frame(const int32_t *a,size_t n,size_t i) {
 if(i+67>n)return 0;
 int32_t leader=pulse(a,n,i),gap=pulse(a,n,i);
 if(leader<3300||leader>4600||gap>-150||gap<-950)return 0;
 uint32_t c=0;
 for(size_t j=0;j<32;j++) {
  int32_t h=pulse(a,n,i),l=pulse(a,n,i);
  if(l < -950||l > -150)return 0;
  if(h>=350&&h<=900)c<<=1;
  else if(h>=1250&&h<=2000)c=(c<<1)|1;
  else return 0;
 }
 int32_t trailer=pulse(a,n,i);
 if(trailer<1250||trailer>3000)return 0;
 return name(c)?c:0;
}
struct Guard {
 bool active=false,seen=false;
 uint32_t started=0,last_seen=0,last_code=0,count=0;
 const char *command="None",*status="Idle",*action="Boot: no timer restored";
 bool receive(uint32_t c,uint32_t now) {
  if(!name(c))return false;
  bool duplicate=seen&&c==last_code&&uint32_t(now-last_seen)<800;
  seen=true;last_code=c;last_seen=now;
  if(duplicate)return false;
  command=name(c);++count;
  if(c==ON){active=true;started=now;status="Awaiting timer selection";action="5-minute fallback armed";}
  else if(c==OFF){active=false;status="Idle";action="Power Off heard: fallback canceled";}
  else if(timer(c)){active=false;status="Native timer selected";action="Timer heard: fallback canceled";}
  return true;
 }
 uint32_t remaining(uint32_t now) const {if(!active)return 0;uint32_t elapsed=now-started;return elapsed>=300000?0:(300000-elapsed+999)/1000;}
 bool tick(uint32_t now) {
  if(!active)return false;
  if(uint32_t(now-started)>=300000){active=false;status="Off sent (unconfirmed)";action="Fallback expired: transmitting Power Off";return true;}
  if(uint32_t(now-started)>=10000)status="Fallback counting down";
  return false;
 }
};
inline Guard instance;
}
