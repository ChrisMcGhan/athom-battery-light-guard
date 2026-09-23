#include "guard.h"
#include "components/battery_light_stream/stream_decoder.h"
#include <iostream>
#include <vector>
int main() {
  size_t n;
  while (std::cin >> n) {
    battery_light_stream_core::Decoder decoder;
    for (size_t i=0;i<n;++i) {
      int32_t p; std::cin >> p;
      uint32_t code = p == 0 ? (decoder.reset(), 0u) : decoder.push(p);
      if (battery_guard::name(code)) std::cout << std::hex << code << ' ' << std::dec;
    }
    uint32_t code=decoder.idle();
    if (battery_guard::name(code)) std::cout << std::hex << code << ' ' << std::dec;
    std::cout << '\n';
  }
}
