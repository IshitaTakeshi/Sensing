# Sensing

I2C sensor communication project for Raspberry Pi.

## Features

- ISM330DHCX 6DoF IMU sensor support
- Real-time accelerometer and gyroscope data reading
- I2C communication interface

## Requirements

- Python 3.x
- SparkFun ISM330DHCX sensor connected via I2C

## Installation

```bash
uv sync
```

## Usage

```bash
uv run main.py
```

The program will continuously display sensor readings:
- Accelerometer data in mg (milligravity)
- Gyroscope data in dps (degrees per second)

Press Ctrl+C to stop.

## Hardware Setup

Connect the ISM330DHCX sensor to your Raspberry Pi via I2C:
- VCC → 3.3V
- GND → Ground
- SDA → GPIO 2 (SDA)
- SCL → GPIO 3 (SCL)

Default I2C address: 0x6B
