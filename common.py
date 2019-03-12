from enum import Enum


class ConnectionType(Enum):
    UDP = 0
    TCP = 1


class PacketType(Enum):
    INIT = 0
    TOKEN = 1
