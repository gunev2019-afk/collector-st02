import os
import time
import datetime as dt
import signal
import sys
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pymodbus.client import ModbusTcpClient

# Нормальный вывод юникода в логах контейнера
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)


# ================== НАСТРОЙКИ ==================
URL     = os.getenv("INFLUX_URL", "http://influxdb:8086")
ORG     = os.getenv("INFLUX_ORG", "iot")
BUCKET  = os.getenv("INFLUX_BUCKET", "telemetry")
TOKEN   = os.environ.get("INFLUX_TOKEN")  # ОБЯЗАТЕЛЬНО

# По умолчанию теперь LOGO_1
STATION     = os.getenv("SIM_STATION", "LOGO_1")

LOGO_IP     = os.getenv("LOGO_IP")
MODBUS_PORT = int(os.getenv("LOGO_PORT", "502"))
UNIT_ID     = int(os.getenv("UNIT_ID", "1"))

# Адреса input-регистров для трёх датчиков
# Можно переопределить через переменные окружения при желании
TEMP_AI_ADDR   = int(os.getenv("TEMP_AI_ADDR", "0"))  # 1-й датчик: температура (0–10 В)
HUM_AI_ADDR    = int(os.getenv("HUM_AI_ADDR",  "1"))  # 2-й датчик: влажность (0–10 В)
TEMP_RTD_ADDR  = int(os.getenv("TEMP_RTD_ADDR", "2"))  # 3-й датчик: PT100/PT1000 (AM2 RTD)

# Масштаб «raw → вольты» для обычных AI (0..1000 -> 0..10 В)
RAW_MAX  = float(os.getenv("RAW_MAX", "1000"))
V_MAX    = float(os.getenv("V_MAX", "10"))

# Опрос раз в 1 секунду по умолчанию
POLL_SEC = float(os.getenv("POLL_SEC", "1"))

# ================== СЛУЖЕБНОЕ ==================
running = True

def handle_exit(signum, frame):
    global running
    print("\nПолучен сигнал завершения, останавливаюсь...")
    running = False

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def read_ir(client, address=0, count=1, unit=UNIT_ID):
    """Универсальное чтение Input Registers для разных версий pymodbus."""
    try:
        return client.read_input_registers(address=address, count=count, unit=unit)
    except TypeError:
        try:
            return client.read_input_registers(address=address, count=count, slave=unit)
        except TypeError:
            return client.read_input_registers(address=address, count=count)


def raw_to_volts(raw: int) -> float:
    """Перевод значения LOGO (0..RAW_MAX) в вольты (0..V_MAX) для обычных AI."""
    return (float(raw) / RAW_MAX) * V_MAX


# ====== ПЕРЕСЧЁТ ТРЁХ ДАТЧИКОВ В ФИЗИЧЕСКИЕ ВЕЛИЧИНЫ ======

def convert_temp_ai(raw: int) -> float:
    """
    1-й датчик температуры (0–10 В):
    температура = V * 12 - 40
    """
    volts = raw_to_volts(raw)
    return volts * 12.0 - 40.0  # °C


def convert_humidity(raw: int) -> float:
    """
    2-й датчик: влажность (0–10 В):
    сырое значение (вольты) * 10 = %
    """
    volts = raw_to_volts(raw)
    return volts * 10.0  # %


def convert_temp_rtd(raw: int) -> float:
    """
    3-й датчик: PT100/PT1000 через AM2 RTD.
    Типовая формула:
        T(°C) = raw * 0.25 - 50
    """
    return raw * 0.25 - 50.0


# ================== ОСНОВНОЙ ЦИКЛ ==================
if not TOKEN:
    raise SystemExit("Error: INFLUX_TOKEN not set!")

client_influx = InfluxDBClient(url=URL, token=TOKEN, org=ORG, timeout=30)
write_api = client_influx.write_api(write_options=SYNCHRONOUS)
client_modbus = ModbusTcpClient(LOGO_IP, port=MODBUS_PORT, timeout=5)

print(
    f"Starting LOGO! monitor (IP: {LOGO_IP}, Unit: {UNIT_ID}, "
    f"Temp_AI={TEMP_AI_ADDR}, Hum_AI={HUM_AI_ADDR}, Temp_RTD={TEMP_RTD_ADDR}, "
    f"InfluxDB: {URL}, bucket={BUCKET}, station={STATION}, poll={POLL_SEC}s)"
)

while running:
    try:
        if not client_modbus.connect():
            print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] Ошибка подключения к LOGO!")
            time.sleep(POLL_SEC)
            continue

        # Читаем три канала
        resp_temp_ai  = read_ir(client_modbus, address=TEMP_AI_ADDR,  count=1, unit=UNIT_ID)
        resp_hum_ai   = read_ir(client_modbus, address=HUM_AI_ADDR,   count=1, unit=UNIT_ID)
        resp_temp_rtd = read_ir(client_modbus, address=TEMP_RTD_ADDR, count=1, unit=UNIT_ID)

        # Проверка на ошибки
        if (hasattr(resp_temp_ai, "isError") and resp_temp_ai.isError()) \
           or (hasattr(resp_hum_ai, "isError") and resp_hum_ai.isError()) \
           or (hasattr(resp_temp_rtd, "isError") and resp_temp_rtd.isError()):
            print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] Modbus ошибка при чтении одного из каналов")
        else:
            raw_temp_ai  = int(resp_temp_ai.registers[0])
            raw_hum_ai   = int(resp_hum_ai.registers[0])
            raw_temp_rtd = int(resp_temp_rtd.registers[0])

            # пересчёт в физические величины
            temp_ai_c    = convert_temp_ai(raw_temp_ai)
            humidity_pct = convert_humidity(raw_hum_ai)
            temp_rtd_c   = convert_temp_rtd(raw_temp_rtd)

            # ====== ПИШЕМ ТРИ ОТДЕЛЬНЫХ ИЗМЕРЕНИЯ (ТАБЛИЦЫ) ======
            point_temp_ai = (
                Point("temperature_ai")          # отдельное измерение для 1-го датчика
                .tag("station", STATION)
                .tag("channel", "AI1")           # по порядку: первый датчик
                .field("температура", float(temp_ai_c))
            )

            point_humidity = (
                Point("humidity")                # отдельное измерение для влажности
                .tag("station", STATION)
                .tag("channel", "AI2")           # второй датчик
                .field("value_pct", float(humidity_pct))
            )

            point_temp_rtd = (
                Point("temperature_rtd")         # отдельное измерение для RTD
                .tag("station", STATION)
                .tag("channel", "AI3")           # третий датчик
                .field("температура", float(temp_rtd_c))
            )

            # можно писать список сразу из трёх точек
            write_api.write(bucket=BUCKET, org=ORG, record=[point_temp_ai, point_humidity, point_temp_rtd])

            # Лог в консоль
            print(
                f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] "
                f"T_AI={temp_ai_c:6.2f} °C (AI1, raw={raw_temp_ai}) | "
                f"H={humidity_pct:6.2f} % (AI2, raw={raw_hum_ai}) | "
                f"T_RTD={temp_rtd_c:6.2f} °C (AI3, raw={raw_temp_rtd})"
            )

    except Exception as e:
        print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] ERROR: {repr(e)}")
    finally:
        client_modbus.close()
        time.sleep(POLL_SEC)

print("Скрипт завершил работу")
client_influx.close()
