# main.py

import os
import time
import datetime as dt
import signal
import sys

import logo_modbus
import sensors
import influx_writer

# ---------- НОРМАЛЬНЫЙ ВЫВОД ЮНИКОДА ----------
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# ===== НАСТРОЙКИ ИЗ ОКРУЖЕНИЯ (для контейнера) =====
INFLUX_URL    = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_ORG    = os.getenv("INFLUX_ORG", "iot")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "telemetry")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN")

# на VPS эти переменные уже заданы в docker-compose
LOGO_IP     = os.getenv("LOGO_IP", "192.168.1.10")
MODBUS_PORT = int(os.getenv("LOGO_PORT", "502"))
UNIT_ID     = int(os.getenv("UNIT_ID", "1"))

ADDR_1 = int(os.getenv("ADDR_1", "0"))  # AI1
ADDR_2 = int(os.getenv("ADDR_2", "1"))  # AI2
ADDR_3 = int(os.getenv("ADDR_3", "2"))  # AI3
ADDR_4 = int(os.getenv("ADDR_4", "3"))  # AI4
ADDR_5 = int(os.getenv("ADDR_5", "4"))  # AI5
ADDR_6 = int(os.getenv("ADDR_6", "5"))  # AI5

RAW_MAX  = float(os.getenv("RAW_MAX", "1000"))
V_MAX    = float(os.getenv("V_MAX", "10"))

POLL_SEC = float(os.getenv("POLL_SEC", "1.0"))

# флаг: писать ли в Influx
WRITE_TO_INFLUX = True   # в контейнере True; если нужно, на ПК можешь поставить False

running = True


def handle_exit(signum, frame):
    global running
    print("\nПолучен сигнал завершения, останавливаюсь...")
    running = False


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def main():
    print(
        f"Starting modular LOGO reader (IP: {LOGO_IP}, Unit: {UNIT_ID}, "
        f"AI1={ADDR_1}, AI2={ADDR_2}, AI3={ADDR_3}, poll={POLL_SEC}s)"
    )

    # инициализируем Influx только если надо писать
    if WRITE_TO_INFLUX:
        if not INFLUX_TOKEN:
            raise SystemExit("Error: INFLUX_TOKEN не задан, а WRITE_TO_INFLUX=True")
        client, write_api = influx_writer.init_influx(
            url=INFLUX_URL,
            token=INFLUX_TOKEN,
            org=INFLUX_ORG,
        )
    else:
        client, write_api = None, None

    while running:
        try:
            # --- 1) Чтение сырых данных с трёх каналов LOGO ---
            raw_AI1 = logo_modbus.read_AI1(
                ip=LOGO_IP,
                port=MODBUS_PORT,
                unit_id=UNIT_ID,
                addr_AI1=ADDR_1,
                timeout=5.0,
            )

            raw_AI2 = logo_modbus.read_AI2(
                ip=LOGO_IP,
                port=MODBUS_PORT,
                unit_id=UNIT_ID,
                addr_AI2=ADDR_2,
                timeout=5.0,
            )

            raw_AI3 = logo_modbus.read_AI3(
                ip=LOGO_IP,
                port=MODBUS_PORT,
                unit_id=UNIT_ID,
                addr_AI3=ADDR_3,
                timeout=5.0,
            )

            raw_AI4 = logo_modbus.read_AI4(
                ip=LOGO_IP,
                port=MODBUS_PORT,
                unit_id=UNIT_ID,
                addr_AI4=ADDR_4,
                timeout=5.0,
            )

            raw_AI5 = logo_modbus.read_AI5(
                ip=LOGO_IP,
                port=MODBUS_PORT,
                unit_id=UNIT_ID,
                addr_AI5=ADDR_5,
                timeout=5.0,
            )

            raw_AI6 = logo_modbus.read_AI6(
                ip=LOGO_IP,
                port=MODBUS_PORT,
                unit_id=UNIT_ID,
                addr_AI6=ADDR_6,
                timeout=5.0,
            )

            # --- 2) Конвертация в физические значения ---
            ready_AI1 = sensors.convert_temp_ai(
                raw=raw_AI1,
                raw_max=RAW_MAX,
                v_max=V_MAX,
            )

            ready_AI2 = sensors.convert_humidity(
                raw=raw_AI2,
                raw_max=RAW_MAX,
                v_max=V_MAX,
            )

            ready_AI3 = sensors.convert_temp_rtd(
                raw=raw_AI3,
            )

            ready_AI4 = sensors.convert_temp_rtd(
                raw=raw_AI4,
            )

            ready_AI5 = sensors.convert_temp_rtd(
                raw=raw_AI5,
            )

            ready_AI6 = sensors.convert_temp_rtd(
                raw=raw_AI6,
            )

            # --- 3) Лог в консоль ---
            now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"[{now_str}] "
                f"AI1={ready_AI1:6.2f} °C | "
                f"AI2={ready_AI2:6.2f} % | "
                f"AI3={ready_AI3:6.2f} °C "
                f"AI4={ready_AI4:6.2f} °C "
                f"AI5={ready_AI5:6.2f} °C "
                f"AI6={ready_AI6:6.2f} °C "
            )

            # --- 4) Запись в Influx (если включено) ---
            if WRITE_TO_INFLUX and client is not None:
                try:
                    influx_writer.write_measurements(
                        client=client,
                        write_api=write_api,
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        name_location="lab",
                        tag_channel="AI1",
                        name_value="температура",
                        value=ready_AI1,
                    )

                    influx_writer.write_measurements(
                        client=client,
                        write_api=write_api,
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        name_location="lab",
                        tag_channel="AI2",
                        name_value="влажность",
                        value=ready_AI2,
                    )

                    influx_writer.write_measurements(
                        client=client,
                        write_api=write_api,
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        name_location="lab",
                        tag_channel="AI3",
                        name_value="температура",
                        value=ready_AI3,
                    )

                    influx_writer.write_measurements(
                        client=client,
                        write_api=write_api,
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        name_location="lab",
                        tag_channel="AI4",
                        name_value="температура",
                        value=ready_AI4,
                    )

                    influx_writer.write_measurements(
                        client=client,
                        write_api=write_api,
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        name_location="lab",
                        tag_channel="AI5",
                        name_value="температура",
                        value=ready_AI5,
                    )

                    influx_writer.write_measurements(
                        client=client,
                        write_api=write_api,
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        name_location="lab",
                        tag_channel="AI6",
                        name_value="температура",
                        value=ready_AI6,
                    )
                except Exception as e:
                    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] ERROR write Influx: {repr(e)}")

        except Exception as e:
            print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] ERROR MAIN: {repr(e)}")

        time.sleep(POLL_SEC)

    if WRITE_TO_INFLUX and client is not None:
        influx_writer.close_influx(client)
    print("Скрипт завершил работу")


if __name__ == "__main__":
    main()
