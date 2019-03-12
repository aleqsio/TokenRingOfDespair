import sys
import json
import common
import socket
import uuid
import signal
import time
import struct
import random
import datetime
from faker import Faker

fake = Faker('pl_PL')

LOGGER_IP = ""
MULTIPLIER = 3 # for timeout token regen

[_, nodeDescription, ownPort, nextNode, hasToken, protocol] = sys.argv
[nextIp, nextPort] = nextNode.split(":")

if hasToken not in ["true", "false"]: raise Exception("hasToken not true/false")
if protocol not in ["tcp", "udp"]: raise Exception("protocol not tcp/udp")
protocol = common.ConnectionType.TCP if protocol == "tcp" else common.ConnectionType.UDP
hasToken = True if hasToken == "true" else False
timeout = 0.1
whitelist = ""
timeWhenLastTokenWentThrough = datetime.datetime.now()


def getOwnIp():
    return "localhost"
    # return socket.gethostbyname(socket.gethostname())  # maybe we should consider providing it as parameter


nextNode = (nextIp, int(nextPort))
nextNodeSocket = None
prevNodeSocket = None
prevNode = None
devicesInRing = dict()
currentNode = (getOwnIp(), int(ownPort))
messagesToSend = []
receivedMessages = []


def getCurrentNodeId():
    return currentNode[0] + ":" + str(currentNode[1])


def generateInitPacket():
    return {
        "type": common.PacketType.INIT.value,
        "initNodeDescription": nodeDescription,
        # we use ip:port tuple as ids rather than nodeDescription to allow us to dynamically add clients
        "initNodeAddress": getOwnIp() + ":" + ownPort,
        "nextNodeAddress": nextNode,
    }


def generateRandomMsg():
    if random.randrange(0, 4) == 0 and len(devicesInRing) > 0:
        messagesToSend.append((random.choice(list(devicesInRing.keys())),
                               fake.sentence(nb_words=6, variable_nb_words=True, ext_word_list=None)))


def setupUdpClient():
    global nextNodeSocket, prevNodeSocket
    nextNodeSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    prevNodeSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    prevNodeSocket.bind(currentNode)
    time.sleep(1)


def setupTcpClient():
    global nextNodeSocket, prevNode, prevNodeSocket

    prevNodeSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    prevNodeSocket.bind(currentNode)
    prevNodeSocket.listen()
    nextNodeSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    time.sleep(1)
    if hasToken:
        nextNodeSocket.connect(nextNode)
    prevNodeSocket, prevNode = prevNodeSocket.accept()
    if not hasToken:
        nextNodeSocket.connect(nextNode)


def send(dataDict):
    if random.randrange(0, 50000000) == 0:
        log("dropping the token")
        return  # to simulate network loss
    msg = json.dumps(dataDict).encode("utf8")

    if protocol == common.ConnectionType.UDP:
        nextNodeSocket.sendto(msg, nextNode)
    else:
        msgWithLen = struct.pack('>I', len(msg)) + msg
        nextNodeSocket.send(msgWithLen)


def recvLen(size):
    global prevNode
    data = b''
    while len(data) < size:
        packet = prevNodeSocket.recv(size - len(data))
        if not packet:
            return None
        data += packet
    return data


def receive():
    global timeWhenLastTokenWentThrough, prevNode
    prevNodeSocket.settimeout(timeout * MULTIPLIER * random.uniform(1,10)) #
    try:
        if protocol == common.ConnectionType.TCP:
            structLength = recvLen(4)
            if not structLength:
                return None
            length = struct.unpack('>I', structLength)[0]
            data = recvLen(length)
        else:
            data, prevNode = prevNodeSocket.recvfrom(2048)
        try:
            token = json.loads(data.decode("utf-8"))
        except ValueError:
            return None
        return token
    except socket.timeout:
        timeWhenLastTokenWentThrough = datetime.datetime.now()
        return "timeout"


def handleInitPacket(token):
    global currentNode
    if token["initNodeAddress"] == getCurrentNodeId():
        return None
    devicesInRing[token["initNodeAddress"]] = token["initNodeDescription"]
    log("discovered new device on network, have " + str(len(devicesInRing)) + " devices")
    if token["nextNodeAddress"] == getCurrentNodeId():
        currentNode = (token["initNodeAddress"].split(":")[0], int(token["initNodeAddress"].split(":")[1]))
    return token


def log(msg):
    print(getCurrentNodeId() + " says " + msg)


def updateTime():
    global timeout, timeWhenLastTokenWentThrough
    networkDelay = datetime.datetime.now() - timeWhenLastTokenWentThrough
    timeout = 0.8 * timeout + networkDelay.total_seconds()
    timeWhenLastTokenWentThrough = datetime.datetime.now()
    # log("updated timeout to " + str(timeout) + " s")


def handleToken(token):
    global whitelist

    if "updateWhitelist" in token:
        if token["generatedBy"] == getCurrentNodeId():
            token = getEmptyTokenFromToken(token)
        whitelist = token["tokenId"]
        log("update whitelist")
        return token
    if "msg" not in token:
        return fillTokenWithMsgIfAvailable(token)
    if token["senderId"] == getCurrentNodeId():
        log("a message did a roundtrip")
        return getEmptyTokenFromToken(token)
    if token["recipientId"] == getCurrentNodeId():
        receivedMessages.append((token["senderId"], token["msg"]))
        log("received msg " + token["msg"] + " from " + token["senderId"])
        return getEmptyTokenFromToken(token)
    return token


def generateToken():
    global whitelist
    token = {
        "type": common.PacketType.TOKEN.value,
        "tokenId": str(uuid.uuid4()),
        "updateWhitelist": True,
        "prevTokenId": whitelist,
        "generatedBy": getCurrentNodeId(),
    }
    whitelist = token["tokenId"]
    log("generating token")
    return token


def fillTokenWithMsgIfAvailable(token):
    if len(messagesToSend) == 0:
        return token
    msg = messagesToSend.pop()
    return {
        "type": common.PacketType.TOKEN.value,
        "tokenId": token["tokenId"],
        "senderId": getCurrentNodeId(),
        "recipientId": msg[0],
        "msg": msg[1]
    }


def getEmptyTokenFromToken(token):
    return {
        "type": common.PacketType.TOKEN.value,
        "tokenId": token["tokenId"]
    }


def exit_handler(a, b):
    nextNodeSocket.close()
    prevNodeSocket.close()


signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGTERM, exit_handler)


def mainLoop():
    token = receive()
    if token is None:
        return
    if token is "timeout":
        send(generateToken())
    else:
        updatedToken = None
        if token["type"] == common.PacketType.INIT.value:
            updatedToken = handleInitPacket(token)
            updateTime()
        if token["type"] == common.PacketType.TOKEN.value:
            if "updateWhitelist" not in token and token["tokenId"] != whitelist:
                log("ignored token not in whitelist")
                return
            updatedToken = handleToken(token)
            updateTime()
        if updatedToken:
            send(updatedToken)

    generateRandomMsg()


if protocol == common.ConnectionType.UDP:
    setupUdpClient()
else:
    setupTcpClient()
initPacket = generateInitPacket()
send(initPacket)

log("sent init msg")
if hasToken:
    send(generateToken())
while True:
    mainLoop()
