#pragma once
#include <stdint.h>

constexpr uint16_t MAX_DISTANCE_AGE_MS = 200;

inline uint16_t distanceFromEcho(uint32_t pulseUs) {
  // Kit sensor: retain measured echoes from 3 cm through 4 m only.
  return pulseUs >= 174 && pulseUs <= 23200 ? pulseUs * 10 / 58 : 0;
}

inline bool rangeBlocksForward(uint16_t mm, uint32_t ageMs, uint16_t cutoffCm) {
  return mm < 30 || mm > 4000 || ageMs > MAX_DISTANCE_AGE_MS || mm <= cutoffCm * 10;
}
