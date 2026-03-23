import os
import pandas as pd
import requests
from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta,timezone
from zoneinfo import ZoneInfo
from openpyxl import load_workbook

# ================== НАСТРОЙКИ InfluxDB ==================

INFLUX_URL    = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_ORG    = os.getenv("INFLUX_ORG", "iot")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "telemetry")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN")

if not INFLUX_TOKEN:
    raise SystemExit("INFLUX_TOKEN не задан в переменных окружения!")

STATION   = os.getenv("STATION", "LOGO_1")          # тег station
TIMEZONE  = os.getenv("TIMEZONE", "Europe/Moscow")  # часовой пояс
WINDOW    = os.getenv("WINDOW", "30m")              # размер окна (30m, 1h и т.п.)

tz = ZoneInfo(TIMEZONE)

# Берём текущий момент в UTC и переводим в локальный часовой пояс (например, Europe/Moscow)
now_utc = datetime.now(timezone.utc)
end_time = now_utc.astimezone(tz)
start_time = end_time - timedelta(hours=24)

caption_text = (
    f"Отчёт за сутки:\n"
    f"с {start_time:%Y-%m-%d %H:%M}\n"
    f"по {end_time:%Y-%m-%d %H:%M}"
)

# Имя временного файла отчёта (внутри контейнера)
OUTPUT_FILE = f"/tmp/report_{STATION}_{start_time:%Y-%m-%d_%H-%M}__{end_time:%Y-%m-%d_%H-%M}.xlsx"


# ================== НАСТРОЙКИ TELEGRAM ==================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# список chat_id через запятую, например: "5649..., -1001234567890"
RAW_CHAT_IDS       = os.getenv("TELEGRAM_CHAT_IDS") or ""

# превращаем строку в список, убираем пробелы и пустые
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================

def flux_agg(meas: str, field: str, fn: str) -> str:
    """
    Строит Flux-запрос для одного параметра.

      meas  – имя measurement (например "temperature_ai")
      field – имя поля  ("температура" или "value_pct")
      fn    – агрегирующая функция: "last" (факт), "max" (максимум), "min" (минимум)
    """
    # Берём последние 24 часа
    return f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "{meas}")
  |> filter(fn: (r) => r._field == "{field}")
  |> filter(fn: (r) => r.station == "{STATION}")
  |> aggregateWindow(every: {WINDOW}, fn: {fn}, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
'''


def tables_to_df(tables, colname: str) -> pd.DataFrame:
    """
    Превращает ответ InfluxDB (query_api.query(...)) в DataFrame
    с двумя колонками: _time и colname.
    """
    rows = []
    for table in tables:
        for r in table.records:
            rows.append({
                "_time": r.get_time(),
                colname: r.get_value()
            })

    if not rows:
        return pd.DataFrame(columns=["_time", colname])

    df = pd.DataFrame(rows)
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    df = df.sort_values("_time").reset_index(drop=True)
    return df


def send_via_telegram(filepath: str):
    """
    Отправляем Excel-файл в Telegram каждому chat_id из TELEGRAM_CHAT_IDS.
    Файл должен существовать на момент вызова.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("[WARN] TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_IDS не заданы. Файл только сохранён локально (но мы его потом удалим).")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            with open(filepath, "rb") as f:
                files = {"document": (os.path.basename(filepath), f)}
                data = {"chat_id": chat_id, "caption": caption_text}
                resp = requests.post(url, data=data, files=files)

            if resp.status_code == 200:
                print(f"[OK] Файл отправлен в Telegram (chat_id={chat_id})")
            else:
                print(f"[ERR] Telegram ответил {resp.status_code} для chat_id={chat_id}: {resp.text}")

        except Exception as e:
            print(f"[ERR] Ошибка при отправке в chat_id={chat_id}: {e}")


# ================== ОСНОВНАЯ ЛОГИКА ==================

def main():
    # Подключаемся к InfluxDB
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()

    # --------- 1. ФАКТИЧЕСКИЕ ЗНАЧЕНИЯ (last) ---------
    t1_fact_tables = query_api.query(
        flux_agg("temperature_ai", "температура", "last")
    )
    df_t1_fact = tables_to_df(t1_fact_tables, "T_AI1")

    h_fact_tables = query_api.query(
        flux_agg("humidity", "value_pct", "last")
    )
    df_h_fact = tables_to_df(h_fact_tables, "VL_AI2")

    t3_fact_tables = query_api.query(
        flux_agg("temperature_rtd", "температура", "last")
    )
    df_t3_fact = tables_to_df(t3_fact_tables, "T_AI3")

    # --------- 2. МАКСИМУМЫ (max) ЗА ОКНО ---------
    t1_max_tables = query_api.query(
        flux_agg("temperature_ai", "температура", "max")
    )
    df_t1_max = tables_to_df(t1_max_tables, "MAX_T_AI1")

    h_max_tables = query_api.query(
        flux_agg("humidity", "value_pct", "max")
    )
    df_h_max = tables_to_df(h_max_tables, "MAX_VL_AI2")

    t3_max_tables = query_api.query(
        flux_agg("temperature_rtd", "температура", "max")
    )
    df_t3_max = tables_to_df(t3_max_tables, "MAX_T_AI3")

    # --------- 3. МИНИМУМЫ (min) ЗА ОКНО ---------
    t1_min_tables = query_api.query(
        flux_agg("temperature_ai", "температура", "min")
    )
    df_t1_min = tables_to_df(t1_min_tables, "MIN_T_AI1")

    h_min_tables = query_api.query(
        flux_agg("humidity", "value_pct", "min")
    )
    df_h_min = tables_to_df(h_min_tables, "MIN_VL_AI2")

    t3_min_tables = query_api.query(
        flux_agg("temperature_rtd", "температура", "min")
    )
    df_t3_min = tables_to_df(t3_min_tables, "MIN_T_AI3")

    # --------- 4. СКЛЕЙКА ВСЕГО ПО ВРЕМЕНИ ---------
    df = (
        df_t1_fact
        .merge(df_h_fact,  on="_time", how="outer")
        .merge(df_t3_fact, on="_time", how="outer")
        .merge(df_t1_max,  on="_time", how="outer")
        .merge(df_h_max,   on="_time", how="outer")
        .merge(df_t3_max,  on="_time", how="outer")
        .merge(df_t1_min,  on="_time", how="outer")
        .merge(df_h_min,   on="_time", how="outer")
        .merge(df_t3_min,  on="_time", how="outer")
    )

    # --------- 5. ВРЕМЯ И ФОРМАТ ---------
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    df["_time"] = df["_time"].dt.tz_convert(TIMEZONE)
    df = df.sort_values("_time").reset_index(drop=True)

    df["Дата и время"] = df["_time"].dt.strftime("%Y-%m-%d %H:%M")

    # --------- 6. ВЫБИРАЕМ КОЛОНКИ В НУЖНОМ ПОРЯДКЕ ---------
    df = df[
        [
            "Дата и время",
            "T_AI1",
            "VL_AI2",
            "T_AI3",
            "MAX_T_AI1",
            "MAX_VL_AI2",
            "MAX_T_AI3",
            "MIN_T_AI1",
            "MIN_VL_AI2",
            "MIN_T_AI3",
        ]
    ]

    # --------- 7. СОХРАНЯЕМ В EXCEL (ВРЕМЕННО) ---------
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    df.to_excel(OUTPUT_FILE, index=False)

    # Подгоняем ширину колонок
    wb = load_workbook(OUTPUT_FILE)
    ws = wb.active

    column_widths = {
        "A": 20,   # Дата и время
        "B": 12,   # T_AI1
        "C": 12,   # VL_AI2
        "D": 12,   # T_AI3
        "E": 14,   # MAX_T_AI1
        "F": 14,   # MAX_VL_AI2
        "G": 14,   # MAX_T_AI3
        "H": 14,   # MIN_T_AI1
        "I": 14,   # MIN_VL_AI2
        "J": 14,   # MIN_T_AI3
    }

    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    wb.save(OUTPUT_FILE)

    print(f"[OK] Временный файл сохранён: {OUTPUT_FILE}")

    # --------- 8. ОТПРАВЛЯЕМ В TELEGRAM ---------
    send_via_telegram(OUTPUT_FILE)

    # --------- 9. УДАЛЯЕМ ФАЙЛ ---------
    try:
        os.remove(OUTPUT_FILE)
        print(f"[OK] Временный файл удалён: {OUTPUT_FILE}")
    except FileNotFoundError:
        print(f"[WARN] Файл уже отсутствует: {OUTPUT_FILE}")
    except Exception as e:
        print(f"[ERR] Не удалось удалить файл {OUTPUT_FILE}: {e}")

    client.close()


if __name__ == "__main__":
    main()
