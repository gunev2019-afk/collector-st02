import os
import time
from datetime import datetime

from logo_modbus import LogoModbus
from influx_writer import InfluxWriter


# ============================================================
# Настройки из docker-compose.yml
# ============================================================

LOGO_IP = os.getenv("LOGO_IP", "192.168.2.10")
LOGO_PORT = int(os.getenv("LOGO_PORT", "502"))
UNIT_ID = int(os.getenv("UNIT_ID", "1"))

RELAY_START_ADDRESS = int(
    os.getenv("RELAY_START_ADDRESS", "8192")
)
RELAY_COUNT = int(
    os.getenv("RELAY_COUNT", "12")
)

READ_INTERVAL_SEC = float(
    os.getenv("POLL_SEC", "10")
)
RELAY_STABLE_DELAY_SEC = float(
    os.getenv("RELAY_STABLE_DELAY_SEC", "0.5")
)

STATION = os.getenv("STATION", "st02")

INFLUX_URL = os.getenv(
    "INFLUX_URL",
    "http://influxdb:8086",
)
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "iot")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "msk")


# ============================================================
# Карта реле, датчиков, слоев и аналоговых входов
# ============================================================

CHANNELS = {
    # Слой 1
    # S1: Q1 — влажность, Q2 — температура
    # S2: Q3 — влажность, Q4 — температура

    "Q1": {
        "sensor": "S1",
        "layer": "layer1",
        "parameter": "humidity",
        "ai": 1,
    },
    "Q2": {
        "sensor": "S1",
        "layer": "layer1",
        "parameter": "temperature",
        "ai": 2,
    },
    "Q3": {
        "sensor": "S2",
        "layer": "layer1",
        "parameter": "humidity",
        "ai": 1,
    },
    "Q4": {
        "sensor": "S2",
        "layer": "layer1",
        "parameter": "temperature",
        "ai": 2,
    },

    # Слой 2
    # S3: Q5 — влажность, Q6 — температура
    # S4: Q7 — влажность, Q8 — температура

    "Q5": {
        "sensor": "S3",
        "layer": "layer2",
        "parameter": "humidity",
        "ai": 3,
    },
    "Q6": {
        "sensor": "S3",
        "layer": "layer2",
        "parameter": "temperature",
        "ai": 4,
    },
    "Q7": {
        "sensor": "S4",
        "layer": "layer2",
        "parameter": "humidity",
        "ai": 3,
    },
    "Q8": {
        "sensor": "S4",
        "layer": "layer2",
        "parameter": "temperature",
        "ai": 4,
    },

    # Слой 3
    # S5: Q9 — влажность, Q10 — температура
    # S6: Q11 — влажность, Q12 — температура

    "Q9": {
        "sensor": "S5",
        "layer": "layer3",
        "parameter": "humidity",
        "ai": 3,
    },
    "Q10": {
        "sensor": "S5",
        "layer": "layer3",
        "parameter": "temperature",
        "ai": 4,
    },
    "Q11": {
        "sensor": "S6",
        "layer": "layer3",
        "parameter": "humidity",
        "ai": 3,
    },
    "Q12": {
        "sensor": "S6",
        "layer": "layer3",
        "parameter": "temperature",
        "ai": 4,
    },
}


def read_stable_relays(
    logo: LogoModbus,
) -> dict[str, bool] | None:
    """
    Дважды читает Q1-Q12.

    Если реле изменились между чтениями,
    текущий цикл считается нестабильным.
    """

    relays_1 = logo.read_relays(
        RELAY_START_ADDRESS,
        RELAY_COUNT,
    )

    time.sleep(RELAY_STABLE_DELAY_SEC)

    relays_2 = logo.read_relays(
        RELAY_START_ADDRESS,
        RELAY_COUNT,
    )

    if relays_1 != relays_2:
        return None

    return relays_2


def print_relays(
    relays: dict[str, bool],
) -> None:
    print("Реле:")

    for relay_name, state in relays.items():
        print(
            f"{relay_name}: "
            f"{'ON' if state else 'OFF'}"
        )


def get_active_channels(
    relays: dict[str, bool],
) -> list[dict]:
    """
    Формирует список каналов,
    реле которых сейчас включены.
    """

    active_channels = []

    for relay_name, channel in CHANNELS.items():
        if relays.get(relay_name, False):
            active_channels.append(
                {
                    "relay": relay_name,
                    "sensor": channel["sensor"],
                    "layer": channel["layer"],
                    "parameter": channel["parameter"],
                    "ai": channel["ai"],
                }
            )

    return active_channels


def find_conflicting_ai(
    active_channels: list[dict],
) -> set[int]:
    """
    Возвращает номера AI, на которых одновременно
    активны два или более канала.

    Конфликт блокирует только конкретный AI,
    а не весь цикл.
    """

    channels_by_ai: dict[int, list[dict]] = {}

    for channel in active_channels:
        ai_number = channel["ai"]

        if ai_number not in channels_by_ai:
            channels_by_ai[ai_number] = []

        channels_by_ai[ai_number].append(channel)

    conflicting_ai = set()

    for ai_number, channels in channels_by_ai.items():
        if len(channels) > 1:
            conflicting_ai.add(ai_number)

            relay_names = ", ".join(
                channel["relay"]
                for channel in channels
            )

            print(
                f"КОНФЛИКТ AI{ai_number}: "
                f"активны {relay_names}. "
                f"Каналы AI{ai_number} пропущены."
            )

    return conflicting_ai


def convert_value(
    parameter: str,
    raw: int,
) -> float:
    """
    Перевод RAW в физическое значение.
    """

    if parameter == "humidity":
        return raw / 10.0

    if parameter == "temperature":
        return raw/10.0 * 12 - 40.0

    raise ValueError(
        f"Неизвестный параметр: {parameter}"
    )


def process_cycle(
    logo: LogoModbus,
    influx: InfluxWriter,
) -> None:
    """
    Выполняет один полный цикл чтения и записи.
    """

    print("=" * 60)
    print(
        datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    relays_before = read_stable_relays(logo)

    if relays_before is None:
        print(
            "Реле переключаются. "
            "Цикл пропущен."
        )
        return

    print_relays(relays_before)
    print()

    active_channels_before = get_active_channels(
        relays_before
    )

    if not active_channels_before:
        print(
            "Активные каналы не найдены. "
            "Цикл пропущен."
        )
        return

    conflicting_ai = find_conflicting_ai(
        active_channels_before
    )

    valid_channels = [
        channel
        for channel in active_channels_before
        if channel["ai"] not in conflicting_ai
    ]

    if not valid_channels:
        print(
            "Все активные каналы находятся "
            "в конфликте. Запись не выполняется."
        )
        return

    values_to_write = []

    for channel in valid_channels:
        relay = channel["relay"]
        sensor = channel["sensor"]
        layer = channel["layer"]
        parameter = channel["parameter"]
        ai_number = channel["ai"]

        raw = logo.read_ai_raw(ai_number)

        value = convert_value(
            parameter=parameter,
            raw=raw,
        )

        values_to_write.append(
            {
                "relay": relay,
                "sensor": sensor,
                "layer": layer,
                "parameter": parameter,
                "ai": ai_number,
                "raw": raw,
                "value": value,
            }
        )

    relays_after = logo.read_relays(
        RELAY_START_ADDRESS,
        RELAY_COUNT,
    )

    active_channels_after = get_active_channels(
        relays_after
    )

    if (
        relays_before != relays_after
        or active_channels_before
        != active_channels_after
    ):
        print(
            "Реле изменились во время чтения AI. "
            "Все данные текущего цикла отброшены."
        )
        return

    for item in values_to_write:
        relay = item["relay"]
        sensor = item["sensor"]
        layer = item["layer"]
        parameter = item["parameter"]
        ai_number = item["ai"]
        raw = item["raw"]
        value = item["value"]

        print(
            f"{relay} → {parameter} → "
            f"{layer} → {sensor} → "
            f"AI{ai_number} raw={raw}, "
            f"value={value:.2f}"
        )

        try:
            influx.write_value(
                station=STATION,
                layer=layer,
                sensor=sensor,
                parameter=parameter,
                value=value,
            )

            print(
                f"Записано в InfluxDB: "
                f"{parameter} / {layer} / {sensor}"
            )

        except Exception as error:
            print(
                f"Ошибка записи {relay} "
                f"в InfluxDB: {error}"
            )

            # Ошибка одного канала не прерывает
            # обработку остальных каналов.
            continue


def create_logo() -> LogoModbus:
    """
    Создает и открывает соединение с LOGO.
    """

    logo = LogoModbus(
        ip=LOGO_IP,
        port=LOGO_PORT,
        unit_id=UNIT_ID,
        timeout=10.0,
    )

    logo.connect()

    return logo


def main() -> None:
    logo = None

    influx = InfluxWriter(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
        bucket=INFLUX_BUCKET,
    )

    while True:
        try:
            if logo is None:
                print(
                    f"Подключаюсь к LOGO "
                    f"{LOGO_IP}:{LOGO_PORT}..."
                )

                logo = create_logo()

                print("LOGO подключен")

            process_cycle(
                logo=logo,
                influx=influx,
            )

            time.sleep(READ_INTERVAL_SEC)

        except KeyboardInterrupt:
            print("\nОстановка программы")
            break

        except Exception as error:
            print(
                f"Ошибка связи или чтения LOGO: "
                f"{error}"
            )
            print(
                "Программа продолжает работу. "
                "Переподключаюсь к LOGO..."
            )

            try:
                if logo is not None:
                    logo.close()
            except Exception:
                pass

            logo = None

            time.sleep(READ_INTERVAL_SEC)

    try:
        if logo is not None:
            logo.close()
            print("Соединение с LOGO закрыто")
    except Exception:
        pass

    try:
        influx.close()
        print("Соединение с InfluxDB закрыто")
    except Exception:
        pass


if __name__ == "__main__":
    main()