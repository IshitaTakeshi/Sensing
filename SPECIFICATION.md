# Raspberry Pi 4B: High-Precision GNSS/PPS Synchronized IMU Data Acquisition System Construction Report

## 1. System Overview

This system utilizes a Raspberry Pi 4B to achieve nanosecond-level system time synchronization using the PPS signal from a ZED-F9P (GNSS). Using this synchronized time as a reference, it acquires data from an ISM330DHCX (IMU) synchronized via hardware interrupts.

| Item | Specification | Notes |
| --- | --- | --- |
| **Device** | Raspberry Pi 4 Model B | Rev 1.5 |
| **OS** | Debian GNU/Linux 13 (trixie) | Kernel 6.12.x (aarch64) |
| **GNSS** | u-blox ZED-F9P | Connected via UART (NMEA) + PPS |
| **IMU** | STMicroelectronics ISM330DHCX | Connected via SPI + INT signal |

---

## 2. Hardware Connection

The system uses **UART5** for GNSS communication and **SPI0** for IMU communication.

### 2.1 GNSS Module (ZED-F9P)

| Function | GPIO | Physical Pin | Module Pin | Notes |
| --- | --- | --- | --- | --- |
| **UART5 TX** | GPIO 12 | **32** | RX1 | Command transmission |
| **UART5 RX** | GPIO 13 | **33** | TX1 | NMEA data reception |
| **PPS Input** | GPIO 18 | **12** | PPS | Pulse Per Second (Active High) |
| Power | - | 1 | 3.3V |  |
| GND | - | 6 | GND |  |

*Note: The ZED-F9P UART interface is configured to communicate at a baud rate of 38400 bps.*

### 2.2 IMU Module (ISM330DHCX)

| Function | GPIO | Physical Pin | Module Pin | Notes |
| --- | --- | --- | --- | --- |
| **SPI0 MOSI** | GPIO 10 | **19** | SDA | Data Input |
| **SPI0 MISO** | GPIO 9 | **21** | SDO | Data Output |
| **SPI0 SCLK** | GPIO 11 | **23** | SCL | Clock |
| **SPI0 CE0** | GPIO 8 | **24** | CS | Chip Select |
| **Interrupt** | GPIO 25 | **22** | INT1 | Data Ready Signal (Active High) |
| Power | - | 17 | 3V3 |  |
| GND | - | 9 | GND |  |

*Hardware Configuration:*
- **Accelerometer:** Full Scale = ±2g, ODR = 104 Hz
- **Gyroscope:** Full Scale = ±2000 dps, ODR = 104 Hz

*(Note: While the configuration setting is named ±2000 dps, the true clipping limit is ~±2293.7 dps based on the typical sensitivity of 70 mdps/LSB.)*

---

## 3. OS Configuration (`/boot/firmware/config.txt`)

Enable the necessary interfaces to match the physical wiring.

```ini
[all]
# Basic Interfaces
dtparam=spi=on
enable_uart=1

# Enable UART5 (for GNSS) and PPS (on GPIO 18)
dtoverlay=uart5
dtoverlay=pps-gpio,gpiopin=18

```

*Note: A reboot is required after modifying this file.*

---

## 4. Time Synchronization (Stratum 1 NTP)

The system synchronizes the OS clock to the GNSS PPS signal with nanosecond-level precision.

### 4.1 GPSD Configuration (`/etc/default/gpsd`)

`gpsd` handles only the NMEA data from the UART device. The PPS signal is handled directly by Chrony.

```shell
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/ttyAMA5"
GPSD_OPTIONS="-n"

```

### 4.2 Chrony Configuration (`/etc/chrony/chrony.conf`)

Configure Chrony to read the PPS device (`/dev/pps0`) directly.

```conf
# NMEA Data (via GPSD Shared Memory: for seconds alignment)
refclock SHM 0 refid GPS precision 1e-1 offset 0.2 delay 0.2

# PPS Signal (Direct Kernel Access: for nanosecond precision)
refclock PPS /dev/pps0 refid PPS lock GPS

```

### 4.3 Verification

Run `chronyc sources -v`.

* Ensure the **PPS** line has a `*` (Current Best) status.
* Ensure the **Last sample** offset is in the **ns** (nanosecond) or low **us** range.

---

## 5. Software Dependencies & Permissions

### 5.1 System Packages
Install the required system services for GNSS/PPS handling and headers for GPIO hardware access:
```shell
sudo apt-get update
sudo apt-get install -y gpsd chrony pps-tools libgpiod-dev
```

### 5.2 User Permissions
Ensure the executing user is part of the required hardware groups to access UART, SPI, and GPIO interfaces without root privileges:
```shell
sudo usermod -aG dialout,spi,gpio $USER
```
*(Note: You must log out and log back in, or reboot, for group changes to take effect.)*

### 5.3 Python Environment
This project utilizes `uv` for fast dependency management. To set up the environment and install required packages (`gpiod`, `spidev`, etc.):
```shell
uv sync
```
