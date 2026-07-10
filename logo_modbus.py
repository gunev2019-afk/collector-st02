from pymodbus.client import ModbusTcpClient


def _call_modbus(func, unit_id: int, **kwargs):
    """
    Совместимость с разными версиями pymodbus:
    где-то используется unit=, где-то slave=, где-то вообще без параметра.
    """
    try:
        return func(**kwargs, unit=unit_id)
    except TypeError:
        try:
            return func(**kwargs, slave=unit_id)
        except TypeError:
            return func(**kwargs)


class LogoModbus:
    def __init__(self, ip: str, port: int = 502, unit_id: int = 1, timeout: float = 5.0):
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.client = ModbusTcpClient(
            host=self.ip,
            port=self.port,
            timeout=self.timeout,
        )

    def connect(self):
        if not self.client.connect():
            raise RuntimeError(f"Не удалось подключиться к LOGO {self.ip}:{self.port}")

    def close(self):
        self.client.close()

    def read_input_registers(self, address: int, count: int = 1) -> list[int]:
        response = _call_modbus(
            self.client.read_input_registers,
            unit_id=self.unit_id,
            address=address,
            count=count,
        )

        if hasattr(response, "isError") and response.isError():
            raise RuntimeError(f"Ошибка чтения input registers: {response}")

        return list(response.registers)

    def read_ai_raw(self, ai_number: int) -> int:
        """
        AI1 -> address 0
        AI2 -> address 1
        AI3 -> address 2
        AI4 -> address 3
        """
        address = ai_number - 1
        values = self.read_input_registers(address=address, count=1)
        return int(values[0])

    def read_ai_voltage(self, ai_number: int) -> float:
        """
        LOGO обычно отдает 0...1000,
        где 1000 = 10.00 В.
        """
        raw = self.read_ai_raw(ai_number)
        return raw / 100.0

    def read_coils(self, address: int, count: int) -> list[bool]:
        response = _call_modbus(
            self.client.read_coils,
            unit_id=self.unit_id,
            address=address,
            count=count,
        )

        if hasattr(response, "isError") and response.isError():
            raise RuntimeError(f"Ошибка чтения coils: {response}")

        return list(response.bits[:count])

    def read_relays(self, start_address: int, count: int) -> dict[str, bool]:
        """
        Читает сразу блок реле.

        Например:
        start_address=8192, count=4

        Результат:
        {
            "Q1": True,
            "Q2": True,
            "Q3": False,
            "Q4": False
        }
        """
        states = self.read_coils(address=start_address, count=count)

        result = {}

        for index, state in enumerate(states):
            q_number = index + 1
            result[f"Q{q_number}"] = bool(state)

        return result