import socket, concurrent.futures, sys

def scan(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        if s.connect_ex((ip, 6668)) == 0:
            return ip
    except:
        pass
    finally:
        s.close()
    return None

ips = [f"192.168.1.{i}" for i in range(1, 255)]
open_ports = []
with concurrent.futures.ThreadPoolExecutor(max_workers=200) as ex:
    for result in ex.map(scan, ips):
        if result:
            open_ports.append(result)
            print("PUERTO 6668 ABIERTO:", result)

if not open_ports:
    print("No se encontro ningun puerto 6668 abierto en 192.168.1.0/24")
