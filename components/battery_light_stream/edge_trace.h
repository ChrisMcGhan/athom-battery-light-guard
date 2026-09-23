#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace battery_light_stream_core {
// Main-loop-only diagnostic recorder. It observes, but never changes, decoder input.
// The decoder's leader transition starts a bounded trace, including raw history.
// Records are drained outside the receive loop. Only accepted frames and traces that
// reached MinBits valid data bits are reported: ambient noise rarely forms more than two.
template<uint32_t Capacity = 4, uint32_t Pulses = 128, uint32_t MinBits = 4> class EdgeTrace {
 public:
  static_assert(Pulses >= 16, "Trace must hold its pre-leader history");
  struct Record {
    uint32_t sequence{0}, uptime_ms{0}, code{0};
    uint32_t discontinuities{0}, overflows{0};
    uint16_t length{0};
    uint8_t bits{0};
    const char *end{"idle"};
    int16_t pulses[Pulses]{};
  };

  void observe(int32_t pulse) {
    if (pulse == 0) {
      finish("edge_loss");
      history_count_ = history_write_ = 0;
      return;
    }
    int16_t stored = pulse > 32767 ? 32767 : (pulse < -32768 ? -32768 : int16_t(pulse));
    history_[history_write_] = stored;
    history_write_ = (history_write_ + 1) % HISTORY;
    if (history_count_ < HISTORY) ++history_count_;
    if (!active_) return;
    if (current_.length == Pulses) { finish("limit"); return; }
    current_.pulses[current_.length++] = stored;
    if (current_.length == Pulses) finish("limit");
  }

  void begin(uint32_t uptime_ms, uint32_t discontinuities, uint32_t overflows) {
    finish("next_leader");
    active_ = true;
    current_ = Record{};
    current_.uptime_ms = uptime_ms;
    current_.discontinuities = discontinuities;
    current_.overflows = overflows;
    for (uint8_t i = 0; i < history_count_; ++i) {
      current_.pulses[current_.length++] = history_[(history_write_ + HISTORY - history_count_ + i) % HISTORY];
    }
  }

  void accepted(uint32_t code) { if (active_) current_.code = code; }
  void progress(uint32_t bits) { if (active_ && bits > current_.bits) current_.bits = static_cast<uint8_t>(bits); }
  void idle() { finish("idle"); }
  uint32_t count() const { return sequence_; }

  // Emits at most one reportable trace per call. Overwritten traces become one summary
  // line instead of one line each, so a slow drain can never fall permanently behind.
  bool next_dump(char *out, size_t capacity) {
    uint32_t oldest = sequence_ > Capacity ? sequence_ - Capacity + 1 : 1;
    if (next_ < oldest) {
      std::snprintf(out, capacity, "BGEDGE {\"lost_sequences\":[%lu,%lu]}",
                    static_cast<unsigned long>(next_), static_cast<unsigned long>(oldest - 1));
      next_ = oldest;
      return true;
    }
    const Record *found = nullptr;
    while (next_ <= sequence_ && !found) {
      const Record &r = records_[(next_++ - 1) % Capacity];
      if (r.code || r.bits >= MinBits) found = &r;
    }
    if (!found) return false;
    const Record &r = *found;
    int used = std::snprintf(out, capacity,
        "BGEDGE {\"sequence\":%lu,\"uptime_ms\":%lu,\"end\":\"%s\",\"code\":\"%08lX\",\"bits\":%u,\"discontinuities\":%lu,\"overflows\":%lu,\"timings_us\":[",
        static_cast<unsigned long>(r.sequence), static_cast<unsigned long>(r.uptime_ms), r.end,
        static_cast<unsigned long>(r.code), static_cast<unsigned>(r.bits), static_cast<unsigned long>(r.discontinuities),
        static_cast<unsigned long>(r.overflows));
    if (used < 0 || static_cast<size_t>(used) >= capacity) return false;
    size_t pos = static_cast<size_t>(used);
    for (uint16_t i = 0; i < r.length; ++i) {
      int wrote = std::snprintf(out + pos, capacity - pos, "%s%d", i ? "," : "", r.pulses[i]);
      if (wrote < 0 || static_cast<size_t>(wrote) >= capacity - pos) return false;
      pos += static_cast<size_t>(wrote);
    }
    if (capacity - pos < 3) return false;
    std::memcpy(out + pos, "]}", 3);
    return true;
  }

 private:
  void finish(const char *end) {
    if (!active_) return;
    current_.end = end;
    current_.sequence = ++sequence_;
    records_[(sequence_ - 1) % Capacity] = current_;
    active_ = false;
  }
  Record records_[Capacity]{};
  Record current_{};
  uint32_t sequence_{0}, next_{1};
  static constexpr uint8_t HISTORY = 16;
  int16_t history_[HISTORY]{};
  uint8_t history_write_{0}, history_count_{0};
  bool active_{false};
};
}
