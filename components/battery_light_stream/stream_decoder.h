#pragma once
#include <cstdint>

namespace battery_light_stream_core {
// Continuous pulse parser. Callback/buffer boundaries have no protocol meaning.
// Returns a timing-valid 32-bit code; the caller must apply the command whitelist.
class Decoder {
 public:
  void reset() { pending_ = glitch_ = 0; state_ = SEARCH; bits_ = code_ = 0; }
  uint32_t starts() const { return starts_; }
  uint32_t bits() const { return state_ == SEARCH ? 0 : bits_; }
  uint32_t push(int32_t value) {
    if (!value) { reset(); return 0; }
    if (value > 1000000) value = 1000000;
    if (value < -1000000) value = -1000000;
    if (!pending_) { pending_ = value; return 0; }
    if ((pending_ > 0) == (value > 0)) {
      // Merge an isolated <=150us opposite-polarity glitch, retaining elapsed time.
      int64_t sum = int64_t(pending_) + value - glitch_;
      pending_ = sum > 1000000 ? 1000000 : (sum < -1000000 ? -1000000 : int32_t(sum));
      glitch_ = 0;
      return 0;
    }
    if (value >= -150 && value <= 150 && !glitch_) { glitch_ = value; return 0; }
    if (glitch_) { reset(); pending_ = value; return 0; }
    uint32_t result = consume_(pending_);
    pending_ = value;
    return result;
  }
  // Called only after >=6ms of real stable input, beyond every in-frame pulse.
  uint32_t idle() {
    uint32_t result = pending_ && !glitch_ ? consume_(pending_) : 0;
    reset();
    return result;
  }
 private:
  enum State { SEARCH, GAP, HIGH, LOW, TRAILER } state_{SEARCH};
  int32_t pending_{0}, glitch_{0};
  uint32_t bits_{0}, code_{0}, bit_{0}, starts_{0};
  uint32_t consume_(int32_t p) {
    if (3300 <= p && p <= 4600) { ++starts_; state_ = GAP; bits_ = code_ = 0; return 0; }
    switch (state_) {
      case GAP:
        state_ = (-950 <= p && p <= -150) ? HIGH : SEARCH;
        break;
      case HIGH:
        if (350 <= p && p <= 900) bit_ = 0;
        else if (1250 <= p && p <= 2000) bit_ = 1;
        else { state_ = SEARCH; break; }
        state_ = LOW;
        break;
      case LOW:
        if (p < -950 || p > -150) { state_ = SEARCH; break; }
        code_ = (code_ << 1) | bit_;
        state_ = ++bits_ == 32 ? TRAILER : HIGH;
        break;
      case TRAILER:
        state_ = SEARCH;
        if (1250 <= p && p <= 3000) return code_;
        break;
      case SEARCH: break;
    }
    return 0;
  }
};
}
