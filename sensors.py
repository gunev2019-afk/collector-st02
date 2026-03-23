# sensors.py

from typing import NamedTuple



def raw_to_volts(raw: int, raw_max: float, v_max: float) -> float:
    """
    НАША функция.
    Переводит сырое значение LOGO (0..raw_max) в вольты (0..v_max).
    """
    return (float(raw) / raw_max) * v_max


def convert_temp_ai(raw: int, raw_max: float, v_max: float) -> float:
    """
    1-й датчик: температура (0–10 В).
    Формула (твоя): T = V * 12 - 40.
    """
    volts = raw_to_volts(raw, raw_max, v_max)
    return volts * 12.0 - 40.0


def convert_humidity(raw: int, raw_max: float, v_max: float) -> float:
    """
    2-й датчик: влажность (0–10 В).
    Ты говорил: сырое (в Вольтах) * 10 = %.
    """ 
    volts = raw_to_volts(raw, raw_max, v_max)
    return volts * 10.0


def convert_temp_rtd(raw: int) -> float:
    """
    3-й датчик: PT100/PT1000 через AM2 RTD.
    Сейчас используем формулу, как в твоём скрипте:
        T = raw * 0.25 - 50
    """
    return raw * 0.25 - 50.0



