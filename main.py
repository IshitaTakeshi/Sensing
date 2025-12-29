import time
import sys
import qwiic_ism330dhcx  # ライブラリ名が変更されています

def run_example():
    print("\nSparkFun 6DoF - ISM330DHCX Example\n")

    # センサーの初期化
    my_imu = qwiic_ism330dhcx.QwiicISM330DHCX()

    # 接続確認
    if my_imu.is_connected() == False:
        print("センサーが見つかりません。配線とアドレス(0x6B)を確認してください。")
        sys.exit(1)
    
    # 初期化開始
    my_imu.begin()
    print("センサー接続成功！")

    # 初期設定
    # 加速度範囲: 4g, ジャイロ範囲: 500dps
    my_imu.set_accel_full_scale(my_imu.kXlFs4g)
    my_imu.set_gyro_full_scale(my_imu.kGyroFs500dps)

    # データ出力レート設定 (例: 104Hz)
    my_imu.set_accel_data_rate(my_imu.kXlOdr104Hz)
    my_imu.set_gyro_data_rate(my_imu.kGyroOdr104Hz)

    print("計測を開始します (Ctrl+C で停止)...")

    try:
        while True:
            # データが準備できているか確認
            if my_imu.check_accel_status() and my_imu.check_gyro_status():
                # データの読み取り
                accel_data = my_imu.get_accel()
                gyro_data = my_imu.get_gyro()

                # 取得した値を使いやすい変数に入れる
                a_x = accel_data.xData
                a_y = accel_data.yData
                a_z = accel_data.zData

                g_x = gyro_data.xData / 1000.0 # mdps(ミリ度/秒)を dpsに変換
                g_y = gyro_data.yData / 1000.0
                g_z = gyro_data.zData / 1000.0

                # 表示 (加速度は mg, ジャイロは dps)
                print(f"Accel[mg]: {a_x:6.1f}, {a_y:6.1f}, {a_z:6.1f} | Gyro[dps]: {g_x:6.1f}, {g_y:6.1f}, {g_z:6.1f}")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n停止しました")
        sys.exit(0)

if __name__ == '__main__':
    run_example()
