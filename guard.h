#pragma once
#include <cstdint>
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
// Every visible field change bumps `changes`, so HA is sent each state once, when it happens.
struct Guard {
 bool active=false,seen=false;
 uint32_t started=0,last_seen=0,last_code=0,count=0,changes=0;
 const char *command="None",*status="Idle",*action="Boot: no timer restored";
 bool receive(uint32_t c,uint32_t now) {
  if(!name(c))return false;
  bool duplicate=seen&&c==last_code&&uint32_t(now-last_seen)<800;
  seen=true;last_code=c;last_seen=now;
  if(duplicate)return false;
  command=name(c);++count;++changes;
  if(c==ON){active=true;started=now;status="Awaiting timer selection";action="5-minute fallback armed";}
  else if(c==OFF){active=false;status="Idle";action="Power Off heard: fallback canceled";}
  else if(timer(c)){active=false;status="Native timer selected";action="Timer heard: fallback canceled";}
  return true;
 }
 uint32_t remaining(uint32_t now) const {if(!active)return 0;uint32_t elapsed=now-started;return elapsed>=300000?0:(300000-elapsed+999)/1000;}
 bool tick(uint32_t now) {
  if(!active)return false;
  if(uint32_t(now-started)>=300000){active=false;status="Off sent (unconfirmed)";action="Fallback expired: transmitting Power Off";++changes;return true;}
  if(uint32_t(now-started)>=10000&&status!=FALLBACK_COUNTING){status=FALLBACK_COUNTING;++changes;}
  return false;
 }
 void manual_off() {active=false;status="Off sent (unconfirmed)";action="Manual Power Off transmitted";++changes;}
 static constexpr const char *FALLBACK_COUNTING="Fallback counting down";
};
inline Guard instance;
// Restart only a device that has lost Home Assistant for `limit` ms while no fallback is pending,
// so recovery never cancels a scheduled Power Off. The countdown itself never needs the network.
struct Recovery {
 uint32_t limit=600000,offline_since=0;
 bool offline=false;
 bool should_restart(bool connected,bool fallback_active,uint32_t now) {
  if(connected){offline=false;return false;}
  if(!offline){offline=true;offline_since=now;return false;}
  return !fallback_active&&uint32_t(now-offline_since)>=limit;
 }
};
inline Recovery recovery;
inline uint32_t receiver_errors=0;
}
