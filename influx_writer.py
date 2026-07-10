from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


class InfluxWriter:
    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
    ):
        self.org = org
        self.bucket = bucket

        self.client = InfluxDBClient(
            url=url,
            token=token,
            org=org,
        )

        self.write_api = self.client.write_api(
            write_options=SYNCHRONOUS
        )

    def write_value(
        self,
        station: str,
        layer: str,
        sensor: str,
        parameter: str,
        value: float,
    ) -> None:
        """
        Записывает один параметр.

        parameter должен быть:
        humidity или temperature
        """

        if parameter not in ("humidity", "temperature"):
            raise ValueError(
                f"Неизвестный параметр для InfluxDB: {parameter}"
            )

        point = (
            Point(station)
            .tag("layer", layer)
            .tag("sensor", sensor)
            .field(parameter, float(value))
        )

        self.write_api.write(
            bucket=self.bucket,
            org=self.org,
            record=point,
        )

    def close(self) -> None:
        self.client.close()