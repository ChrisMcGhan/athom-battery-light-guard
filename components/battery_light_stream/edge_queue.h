#pragma once
#include <atomic>
#include <cstdint>

namespace battery_light_stream_core {
// Single ISR producer, main-loop consumer. Zero is an ordered loss marker.
// A later error must never erase an earlier, fully captured command.
template<uint32_t Capacity> class EdgeQueue {
 public:
  void push(int32_t pulse) {
    if (gap_pending_.load(std::memory_order_relaxed)) {
      if (!put_(0)) return;
      gap_pending_.store(false, std::memory_order_release);
    }
    if (!put_(pulse)) {
      gap_pending_.store(true, std::memory_order_release);
      overflows_.fetch_add(1, std::memory_order_relaxed);
    }
  }
  bool pop(int32_t &pulse) {
    uint32_t read=read_.load(std::memory_order_relaxed);
    if (read==write_.load(std::memory_order_acquire)) return false;
    pulse=ring_[read];
    read_.store((read+1)&(Capacity-1),std::memory_order_release);
    return true;
  }
  bool empty() const { return read_.load(std::memory_order_relaxed)==write_.load(std::memory_order_acquire); }
  bool loss_pending() const { return gap_pending_.load(std::memory_order_acquire); }
  uint32_t overflows() const { return overflows_.load(std::memory_order_relaxed); }
 private:
  static_assert(Capacity>=2 && (Capacity&(Capacity-1))==0,"Queue capacity must be a power of two");
  int32_t ring_[Capacity]{};
  std::atomic<uint32_t> write_{0},read_{0},overflows_{0};
  std::atomic<bool> gap_pending_{false};
  bool put_(int32_t pulse) {
    uint32_t write=write_.load(std::memory_order_relaxed),next=(write+1)&(Capacity-1);
    if(next==read_.load(std::memory_order_acquire)) return false;
    ring_[write]=pulse;
    write_.store(next,std::memory_order_release);
    return true;
  }
};
}
