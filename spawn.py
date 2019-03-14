import time, subprocess, signal
import random

processes = []
protocol = "tcp"
offset = 5100 + random.randrange(0,
                                 100) * 10
# to avoid issues with https://stackoverflow.com/questions/12458019/shutting-down-sockets-properly
count = 10
for i in range(count):
    p = subprocess.Popen(
        "".join(
            ["python client.py client", str(i), " ", str(i + offset), " localhost:", str((i + 1) % count + offset), " ",
             "true " if i == 0 else "false ", protocol]), shell=True)
    processes.append(p)

time.sleep(3)

p = subprocess.Popen(
        "".join(
            ["python client.py client", str(count), " ", str(count + offset), " localhost:", str(offset), " ",
             "true " if i == 0 else "false ", protocol]), shell=True)
processes.append(p)


def exit_handler(a, b):
    for p in processes:
        p.terminate()


signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGTERM, exit_handler)

while True:
    continue
