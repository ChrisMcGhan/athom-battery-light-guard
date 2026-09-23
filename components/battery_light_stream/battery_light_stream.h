#pragma once
#include <atomic>
#include "esphome/core/component.h"
#include "esphome/core/gpio.h"
#include "esphome/core/automation.h"
#include "stream_decoder.h"
#include "edge_queue.h"
#include "edge_trace.h"

namespace esphome::battery_light_stream {
class StreamReceiver : public Component {
 public:
  void set_pin(InternalGPIOPin *pin) { pin_ = pin; }
  Trigger<uint32_t> *get_trigger() { return &trigger_; }
  void setup() override;
  void loop() override;
  void dump_config() override;
  void on_shutdown() override { pin_->detach_interrupt(); }
  float get_setup_priority() const override { return setup_priority::LATE; }
  uint32_t edges() const { return edges_.load(); }
  uint32_t overflows() const { return queue_.overflows(); }
  uint32_t discontinuities() const { return discontinuities_.load(); }
  uint32_t frames() const { return frames_; }
  uint32_t edge_traces() const { return trace_.count(); }
  bool next_edge_dump(char *out, size_t capacity) { return trace_.next_dump(out, capacity); }
 protected:
  static void IRAM_ATTR edge_(StreamReceiver *self);
  void accept_(uint32_t code);
  InternalGPIOPin *pin_{nullptr};
  ISRInternalGPIOPin isr_pin_;
  static constexpr uint32_t CAPACITY = 2048;
  battery_light_stream_core::EdgeQueue<CAPACITY> queue_;
  std::atomic<uint32_t> last_edge_{0};
  std::atomic<uint32_t> edges_{0}, discontinuities_{0};
  bool last_level_{false};  // ISR-owned after setup.
  uint32_t frames_{0};
  battery_light_stream_core::Decoder decoder_;
  battery_light_stream_core::EdgeTrace<> trace_;
  Trigger<uint32_t> trigger_;
};
static_assert(std::atomic<uint32_t>::is_always_lock_free, "ISR counters must be lock free");
static_assert(std::atomic<bool>::is_always_lock_free, "ISR flag must be lock free");
}
