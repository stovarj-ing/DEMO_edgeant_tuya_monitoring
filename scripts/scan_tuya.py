import socket, concurrent.futures

PORTS = [6666, 6667, 6668, 7000, 6996]
BASE = "192.168.1."

def scan(args):
    ip, port = args
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    r = None
    try:
        if s.connect_ex((ip, port)) == 0:
            r = (ip, port)
    except:
        pass
    finally:
        s.close()
    return r

targets = [(f"{BASE}{i}", p) for i in range(1, 255) for p in PORTS]
found = []
with concurrent.futures.ThreadPoolExecutor(max_workers=300) as ex:
    for res in ex.map(scan, targets):
        if res:
            found.append(res)
            print("ABIERTO:", res)

print("---")
if not found:
    print("Ninguno de los puertos Tuya abierto en la subred")
else:
    print("Hosts con puertos:", sorted(set(f[0] for f in found)))
