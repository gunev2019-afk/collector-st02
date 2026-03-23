from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


def init_influx(url: str, token: str, org: str):
    """
    Инициализация клиента InfluxDB с увеличенными таймаутами.
    """

    client = InfluxDBClient(
        url=url,
        token=token,
        org=org,
        timeout=300,        # 30 секунд на ответ сервера
        connect_timeout=5_000  # 5 секунд на подключение
    )

    write_api = client.write_api(write_options=SYNCHRONOUS)

    return client, write_api


def write_measurements(
    client,
    write_api,
    bucket: str,
    org: str,
    name_location: str,
    tag_channel: str,
    name_value: str,
    value: float,
):
    """
    Записывает одно значение в InfluxDB.
      name_location — measurement (например "lab")
      tag_channel   — тег channel: "AI1", "AI2", "AI3"
      name_value    — имя поля: "температура", "влажность" и т.п.
      value         — числовое значение
    """
    point = (
        Point(name_location)
        .tag("channel", tag_channel)
        .field(name_value, float(value))
    )

    write_api.write(
        bucket=bucket,
        org=org,
        record=point,
    )


def close_influx(client):
    """
    Аккуратно закрывает соединение с InfluxDB.
    """
    client.close()
