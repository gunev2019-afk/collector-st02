from pymodbus.client import ModbusTcpClient


def read_input_registers(ip: str,
                         port: int,
                         unit_id: int,
                         address: int,
                         count: int = 1,
                         timeout: float = 5.0) -> list[int]:

    client = ModbusTcpClient(ip, port=port, timeout=timeout)

    if not client.connect():
        client.close()
        raise RuntimeError(f"Не удалось подключиться к LOGO по адресу {ip}:{port}")

    try:
        # читаем input registers, учитывая разные версии pymodbus
        try:
            resp = client.read_input_registers(address=address, count=count, unit=unit_id)
        except TypeError:
            try:
                resp = client.read_input_registers(address=address, count=count, slave=unit_id)
            except TypeError:
                resp = client.read_input_registers(address=address, count=count)

        if hasattr(resp, "isError") and resp.isError():
            raise RuntimeError(f"Modbus ошибка: {resp}")

        return list(resp.registers)

    finally:
        client.close()


def read_AI1(ip: str,
                 port: int,
                 unit_id: int,
                 addr_AI1: int,
                 timeout: float = 5.0) -> int:

    raws = read_input_registers(
        ip=ip,
        port=port,
        unit_id=unit_id,
        address=addr_AI1,
        count=1,
        timeout=timeout,
    )
    return int(raws[0])


def read_AI2(ip: str,
                 port: int,
                 unit_id: int,
                 addr_AI2: int,
                 timeout: float = 5.0) -> int:
 
    raws = read_input_registers(
        ip=ip,
        port=port,
        unit_id=unit_id,
        address=addr_AI2,
        count=1,
        timeout=timeout,
    )
    return int(raws[0])


def read_AI3(ip: str,
                 port: int,
                 unit_id: int,
                 addr_AI3: int,
                 timeout: float = 5.0) -> int:
   
    raws = read_input_registers(
        ip=ip,
        port=port,
        unit_id=unit_id,
        address=addr_AI3,
        count=1,
        timeout=timeout,
    )
    return int(raws[0])

def read_AI4(ip: str,
                 port: int,
                 unit_id: int,
                 addr_AI4: int,
                 timeout: float = 5.0) -> int:
   
    raws = read_input_registers(
        ip=ip,
        port=port,
        unit_id=unit_id,
        address=addr_AI4,
        count=1,
        timeout=timeout,
    )
    return int(raws[0])

def read_AI5(ip: str,
                 port: int,
                 unit_id: int,
                 addr_AI5: int,
                 timeout: float = 5.0) -> int:
   
    raws = read_input_registers(
        ip=ip,
        port=port,
        unit_id=unit_id,
        address=addr_AI5,
        count=1,
        timeout=timeout,
    )
    return int(raws[0])

def read_AI6(ip: str,
                 port: int,
                 unit_id: int,
                 addr_AI6: int,
                 timeout: float = 5.0) -> int:
   
    raws = read_input_registers(
        ip=ip,
        port=port,
        unit_id=unit_id,
        address=addr_AI6,
        count=1,
        timeout=timeout,
    )
    return int(raws[0])
