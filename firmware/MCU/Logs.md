# Performance Optimization Analysis for 6502 Bus Monitor on ESP32

## 1. Overview

This document details a critical performance optimization applied to the `6502_monitor` firmware. The project's goal is to use an ESP32 to monitor and interact with the bus of a 6502 processor running at 1.79 MHz. The optimization addresses a timing issue that prevented the ESP32 from correctly responding to the 6502's memory read cycles.

## 2. The Timing Problem

A 6502 processor running at 1.79 MHz has a clock cycle of approximately 558 nanoseconds. The `PHI2` clock signal is high for roughly half of this period, giving a critical time window of about **279 nanoseconds** for any device on the bus to respond.

When the 6502 performs a read operation (`R/W` line is high), it expects the data to be stable on the data bus *before* the falling edge of the `PHI2` clock. The ESP32, when emulating a memory-mapped device, must perform the following steps within this 279 ns window:
1.  Detect the `PHI2` rising edge.
2.  Read the address bus to identify the memory location being accessed.
3.  If it's a recognized address for a read operation:
    a. Change the ESP32's data bus pins from `INPUT` to `OUTPUT`.
    b. Write the correct data byte to the bus.

### The Bottleneck: `gpio_config()`

The original implementation used the `set_data_bus_direction()` function to change the GPIO pin direction.

**Original (Slow) Implementation:**
```c
static inline void set_data_bus_direction(gpio_mode_t mode) {
    gpio_config_t io_conf;
    io_conf.pin_bit_mask = (...);
    io_conf.mode = mode;
    // ... other settings ...
    gpio_config(&io_conf);
}
```

The `gpio_config()` function from the ESP-IDF is a general-purpose utility designed for pin initialization (e.g., in the `setup()` function). It is not optimized for high-speed state changes. Its execution time is in the order of **several microseconds (µs)**.

This is far too slow for the required 279 nanosecond (ns) window. The 6502 would have already proceeded to the next instruction before the ESP32 could even place the data on the bus, leading to bus contention or the 6502 reading incorrect/floating values.

## 3. The Solution: Direct Register Manipulation

The fix involves replacing the slow `gpio_config()` call with direct writes to the GPIO peripheral's registers. The ESP32 provides registers specifically for atomically setting or clearing the direction of multiple GPIOs in a single CPU cycle.

**Optimized (Fast) Implementation:**
```c
static inline void set_data_bus_direction(gpio_mode_t mode) {
    const uint32_t pin_mask = (...);

    if (mode == GPIO_MODE_OUTPUT) {
        GPIO.enable_w1ts = pin_mask; // Set pins to OUTPUT
    } else {
        GPIO.enable_w1tc = pin_mask; // Set pins to INPUT
    }
}
```
- `GPIO.enable_w1ts` (Write 1 To Set): Sets the corresponding bits in the GPIO enable register, turning the pins into outputs.
- `GPIO.enable_w1tc` (Write 1 To Clear): Clears the corresponding bits, turning the pins back into inputs (high-impedance).

This operation takes only **a few nanoseconds**, leaving ample time within the 279 ns window to perform the data write.

## 4. Timing & Logic Diagrams

### Timing Diagram

This diagram illustrates the time constraints. Time flows from top to bottom.

```
Time (ns)
    |
    |
  0 +----------------+
    | PHI2 goes HIGH |
    |                |           <-- 6502 Address Bus is now stable
    |                |           <-- ESP32 reads Address and R/W
    |                |
 50 +----------------+ . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
    |                |           <-- ESP32 starts processing
    |                |
    |                |           <-- Fast Method: `GPIO.enable_w1ts` completes (~10-20 ns)
    |                |           <-- Fast Method: `write_data_bus` completes (~10-20 ns)
    |                |           <-- DATA IS READY AND STABLE ON BUS
    |                |
279 +----------------+
    | PHI2 goes LOW  |           <-- 6502 latches the data from the bus
    |                |
    |                |
    |                |
    |                |
    |                |
    |                |
3000+ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    |                |           <-- Slow Method: `gpio_config` MIGHT complete here (e.g., 3 µs = 3000 ns)
    |                |           <-- TIMING WINDOW MISSED BY A HUGE MARGIN
    |                |
558 +----------------+
    | Cycle End      |
    |
```

### Flowchart of the `MonitorTask` Read Logic

```
+-----------------------------+
| Start: Wait for PHI2 HIGH   |
+-----------------------------+
             |
             v
+-----------------------------+
| Read Address Bus & R/W Line |
+-----------------------------+
             |
             v
+-----------------------------+
| Is it a READ from our space?|--[No]--> (End of this cycle's work)
+-----------------------------+
             |
            [Yes]
             |
             v
+-----------------------------+
| Change Data Bus to OUTPUT   |
|-----------------------------|
|  - OLD: gpio_config() ~3µs  |
|  - NEW: GPIO.enable_w1ts <20ns |
+-----------------------------+
             |
             v
+-----------------------------+
| Write Data to Bus           |
+-----------------------------+
             |
             v
+-----------------------------+
| Wait for PHI2 LOW           |
+-----------------------------+
             |
             v
+-----------------------------+
| Change Data Bus to INPUT    |
+-----------------------------+
             |
             v
      (Cycle Complete)

```

## 5. Conclusion

The replacement of `gpio_config()` with direct register writes is a fundamental fix that addresses a critical performance bottleneck. This change ensures that the ESP32 can reliably serve data to the 6502 bus within the strict timing requirements of the 1.79 MHz clock, moving the operation time from microseconds down to nanoseconds.
