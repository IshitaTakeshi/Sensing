import spidev
import time
import struct
import sys

# ==============================================================================
# 1. 定数定義
#    Reference: https://cdn.sparkfun.com/assets/d/4/6/d/f/ism330dhcx_Datasheet.pdf
# ==============================================================================
SPI_READ_BIT = 0x80 
SPI_WRITE_BIT = 0x00

REG_WHO_AM_I = 0x0F
REG_CTRL1_XL = 0x10
REG_CTRL2_G  = 0x11
REG_CTRL3_C  = 0x12
REG_CTRL7_G  = 0x16  # 追加: ジャイロ設定の確認用
REG_OUTX_L_G = 0x22

DEVICE_ID = 0x6B 

class ISM330DHCX:
    def __init__(self, bus=0, device=0):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 5000000 
        self.spi.mode = 0

        # 物理量変換係数 (Datasheet Page 16, Table 3 & 4)
        self.accel_sensitivity = 0.061  # FS +/-2g -> 0.061 mg/LSB
        self.gyro_sensitivity = 70.0    # FS +/-2000dps -> 70 mdps/LSB

        # ゼロ点補正用オフセット
        self.gyro_offset = [0.0, 0.0, 0.0] 

    def _read_byte(self, reg_addr):
        tx_data = [reg_addr | SPI_READ_BIT, 0x00]
        rx_data = self.spi.xfer2(tx_data)
        return rx_data[1]

    def _write_byte(self, reg_addr, data):
        tx_data = [reg_addr | SPI_WRITE_BIT, data]
        self.spi.xfer2(tx_data)

    def _read_block(self, start_reg_addr, length):
        tx_data = [start_reg_addr | SPI_READ_BIT] + [0x00] * length
        rx_data = self.spi.xfer2(tx_data)
        return rx_data[1:]

    def debug_dump_regs(self):
        """
        [デバッグ用] 重要なレジスタの生値を表示
        """
        print("\n--- Register Debug Dump ---")
        regs = {
            "WHO_AM_I (0x0F)": REG_WHO_AM_I,
            "CTRL1_XL (0x10)": REG_CTRL1_XL,
            "CTRL2_G  (0x11)": REG_CTRL2_G,
            "CTRL3_C  (0x12)": REG_CTRL3_C,
            "CTRL7_G  (0x16)": REG_CTRL7_G
        }
        for name, addr in regs.items():
            val = self._read_byte(addr)
            print(f"{name}: 0x{val:02X}")
        print("---------------------------\n")

    def begin(self):
        who_am_i = self._read_byte(REG_WHO_AM_I)
        if who_am_i != DEVICE_ID:
            print(f"Error: Device ID 0x{who_am_i:02X} (Expected 0x{DEVICE_ID:02X})")
            return False

        # Reset
        self._write_byte(REG_CTRL3_C, 0x01)
        time.sleep(0.1)

        # BDU=1, IF_INC=1
        self._write_byte(REG_CTRL3_C, 0x44)

        # Accel: 104Hz, 2g (0x40)
        self._write_byte(REG_CTRL1_XL, 0x40)
        
        # Gyro: 104Hz, 2000dps (0x4C)
        # 参照: Datasheet Page 48. FS[1:0] = 11 for 2000dps
        self._write_byte(REG_CTRL2_G, 0x4C)

        # CTRL7_G (Page 52): High Performance Modeを確認
        # Bit 7 (G_HM_MODE): 0 = High Performance (Default), 1 = Low Power
        # Bit 6 (HP_EN_G): 0 = HPF Disabled (Default)
        # デフォルト 0x00 でOKだが、念のため書き込み
        self._write_byte(REG_CTRL7_G, 0x00)

        time.sleep(0.1)
        return True

    def calibrate_gyro(self, samples=100):
        """
        [修正] 起動時に静止状態の誤差を計測してオフセットとする
        """
        print(f"キャリブレーション中... ({samples}サンプル取得)")
        sum_x, sum_y, sum_z = 0.0, 0.0, 0.0
        
        for _ in range(samples):
            # オフセット適用前の生の物理量を取得したいので内部メソッドを呼ぶか、
            # ここで簡易的に計算
            _, gyro = self.read_raw_values() 
            sum_x += gyro[0]
            sum_y += gyro[1]
            sum_z += gyro[2]
            time.sleep(0.01)
        
        self.gyro_offset[0] = sum_x / samples
        self.gyro_offset[1] = sum_y / samples
        self.gyro_offset[2] = sum_z / samples
        
        print(f"キャリブレーション完了: Offset [dps] X:{self.gyro_offset[0]:.3f}, Y:{self.gyro_offset[1]:.3f}, Z:{self.gyro_offset[2]:.3f}")

    def read_raw_values(self):
        """
        オフセット適用前の物理量を取得
        """
        raw_bytes = self._read_block(REG_OUTX_L_G, 12)
        raw_data = struct.unpack('<hhhhhh', bytes(raw_bytes))
        
        # Gyro (dps)
        gx = raw_data[0] * self.gyro_sensitivity / 1000.0
        gy = raw_data[1] * self.gyro_sensitivity / 1000.0
        gz = raw_data[2] * self.gyro_sensitivity / 1000.0
        
        # Accel (g)
        ax = raw_data[3] * self.accel_sensitivity / 1000.0
        ay = raw_data[4] * self.accel_sensitivity / 1000.0
        az = raw_data[5] * self.accel_sensitivity / 1000.0
        
        return (ax, ay, az), (gx, gy, gz)

    def read_data(self):
        """
        オフセット補正済みのデータを取得
        """
        (ax, ay, az), (gx, gy, gz) = self.read_raw_values()
        
        # キャリブレーション値を引く
        gx -= self.gyro_offset[0]
        gy -= self.gyro_offset[1]
        gz -= self.gyro_offset[2]
        
        return (ax, ay, az), (gx, gy, gz)

    def debug_print_raw_hex(self):
        """
        [デバッグ用] 変換前のRawデータをHexで表示
        """
        raw_bytes = self._read_block(REG_OUTX_L_G, 6) # Gyroのみ6バイト
        # Python 3.8+ for hex() with separator
        hex_str = ' '.join(f'{b:02X}' for b in raw_bytes)
        raw_val = struct.unpack('<hhh', bytes(raw_bytes))
        print(f"[DEBUG Raw Hex] {hex_str} -> Raw Int: {raw_val}")

if __name__ == "__main__":
    sensor = ISM330DHCX(bus=0, device=0)
    
    if not sensor.begin():
        sys.exit(1)
    
    # デバッグ: 設定レジスタの確認
    sensor.debug_dump_regs()
    
    # 修正: キャリブレーション実行
    sensor.calibrate_gyro()

    print("計測開始 (Ctrl+C で停止)...")
    print("Accel (g) [X, Y, Z] | Gyro (dps) [X, Y, Z] | [Debug Info]")
    print("-" * 70)

    try:
        while True:
            # 補正済みデータ
            (ax, ay, az), (gx, gy, gz) = sensor.read_data()
            
            print(f"A: {ax:6.3f} {ay:6.3f} {az:6.3f} | G: {gx:7.2f} {gy:7.2f} {gz:7.2f}", end="")
            
            # 5回に1回くらい生Hexを表示してデバッグ（不要ならコメントアウト）
            # sensor.debug_print_raw_hex()
            print() # 改行
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nStopped.")
        sensor.spi.close()
