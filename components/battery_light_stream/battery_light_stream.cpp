#include "battery_light_stream.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "guard.h"

namespace esphome::battery_light_stream {
static const char *const TAG = "battery_light_stream";
void StreamReceiver::setup() {
  // A second input reader on the RF pin; RMT learning/proxy remains available.
  pin_->setup();
  isr_pin_ = pin_->to_isr();
  last_level_ = isr_pin_.digital_read();
  last_edge_.store(micros());
  pin_->attach_interrupt(StreamReceiver::edge_, this, gpio::INTERRUPT_ANY_EDGE);
}
void IRAM_ATTR StreamReceiver::edge_(StreamReceiver *self) {
  uint32_t now = micros();
  uint32_t elapsed = now - self->last_edge_.exchange(now, std::memory_order_relaxed);
  bool level = self->isr_pin_.digital_read();
  bool previous = self->last_level_;
  self->last_level_ = level;
  self->edges_.fetch_add(1, std::memory_order_relaxed);
  if (level == previous) {
    self->discontinuities_.fetch_add(1, std::memory_order_relaxed);
    self->queue_.push(0);
    return;
  }
  int32_t width = elapsed > 1000000 ? 1000000 : int32_t(elapsed);
  self->queue_.push(previous ? width : -width);
}
void StreamReceiver::accept_(uint32_t code) {
  if (code && battery_guard::name(code)) { trace_.accepted(code); ++frames_; trigger_.trigger(code); }
}
void StreamReceiver::loop() {
  // Process valid history first; resynchronize at an ordered loss marker.
  for (uint32_t n = 0; n < CAPACITY; ++n) {
    int32_t pulse;
    if (!queue_.pop(pulse)) break;
    trace_.observe(pulse);
    uint32_t starts = decoder_.starts();
    uint32_t code = decoder_.push(pulse);  // Zero resets an incomplete candidate.
    if (decoder_.starts() != starts)
      trace_.begin(micros() / 1000, discontinuities_.load(std::memory_order_relaxed), queue_.overflows());
    accept_(code);
  }
  // Read the edge timestamp before the clock to avoid subtraction underflow
  // if an ISR lands between the two reads. Confirm it remained unchanged.
  uint32_t last_edge = last_edge_.load(std::memory_order_relaxed);
  uint32_t now = micros();
  if (queue_.empty() &&
      last_edge == last_edge_.load(std::memory_order_relaxed) && uint32_t(now - last_edge) >= 6000) {
    if (queue_.loss_pending()) {
      trace_.observe(0);
      decoder_.reset();
    } else {
      uint32_t starts = decoder_.starts();
      uint32_t code = decoder_.idle();
      if (decoder_.starts() != starts)
        trace_.begin(now / 1000, discontinuities_.load(std::memory_order_relaxed), queue_.overflows());
      accept_(code);
      trace_.idle();
    }
  }
}
void StreamReceiver::dump_config() {
  ESP_LOGCONFIG(TAG, "Continuous battery-light RF decoder: 2048-edge ring, exact command whitelist");
  LOG_PIN("  Shared RF input: ", pin_);
}
}
