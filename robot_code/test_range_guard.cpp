// Run: c++ -std=c++11 robot_code/test_range_guard.cpp -o /tmp/test-range-guard && /tmp/test-range-guard
#include "LordBotJev/RangeGuard.h"
#include <assert.h>
#include <stdio.h>

int main() {
  assert(distanceFromEcho(0) == 0);
  assert(distanceFromEcho(173) == 0);
  assert(distanceFromEcho(174) == 30);
  assert(distanceFromEcho(2900) == 500);
  assert(distanceFromEcho(5800) == 1000);
  assert(distanceFromEcho(23200) == 4000);
  assert(distanceFromEcho(23201) == 0);
  assert(distanceFromEcho(UINT32_MAX) == 0);
  assert(rangeBlocksForward(500, 0, 50));
  assert(!rangeBlocksForward(501, 200, 50));
  assert(rangeBlocksForward(501, 201, 50));
  assert(rangeBlocksForward(0, 0, 50));
  assert(rangeBlocksForward(5000, 0, 50));
  assert(rangeBlocksForward(250, 0, 30));
  assert(!rangeBlocksForward(250, 0, 20));
  const uint32_t captured = UINT32_MAX - 49, now = 50;
  assert(!rangeBlocksForward(1000, uint32_t(now - captured), 50));
  puts("PASS: measured units, echo limits, 50 cm boundary, missing/stale echoes, calibration and timer wrap");
}
