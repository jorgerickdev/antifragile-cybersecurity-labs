import socket
import struct
import sys

def main():
    # Validar argumento de puerto
    if len(sys.argv) < 2:
        print("Uso: sudo python3 sniffer.py <puerto>")
        sys.exit(1)
    filtro_puerto = int(sys.argv[1])

    try:
        conn = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
    except PermissionError:
        print("[-] Error: Se requieren privilegios de administrador (sudo).", file=sys.stderr)
        sys.exit(1)
    except AttributeError:
        print("[-] Error: AF_PACKET solo disponible en Linux.", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Sniffer activo... Escuchando tráfico en el puerto {filtro_puerto}")

    while True:
        try:
            raw_data, addr = conn.recvfrom(65535)
        except KeyboardInterrupt:
            print("\n[+] Sniffer detenido por el usuario.")
            break

        if len(raw_data) < 14:
            continue

        # Cabecera Ethernet
        eth_header = raw_data[:14]
        dest_mac, src_mac, eth_proto = struct.unpack('!6s6sH', eth_header)

        def format_mac(bytes_addr):
            return ':'.join(f'{b:02x}' for b in bytes_addr)

        # IPv4
        if eth_proto == 0x0800 and len(raw_data) >= 34:
            ip_header_raw = raw_data[14:34]
            ip_data = struct.unpack('!BBHHHBBH4s4s', ip_header_raw)

            version_ihl = ip_data[0]
            version = version_ihl >> 4
            ihl = (version_ihl & 0xF) * 4
            ttl = ip_data[5]
            protocol = ip_data[6]
            src_ip = socket.inet_ntoa(ip_data[8])
            dest_ip = socket.inet_ntoa(ip_data[9])

            proto_name = "OTRO"
            if protocol == 1:
                proto_name = "ICMP"
            elif protocol == 6:
                proto_name = "TCP"
            elif protocol == 17:
                proto_name = "UDP"

            src_port = dest_port = None

            # Extraer puertos si es TCP o UDP
            if protocol == 6 and len(raw_data) >= 14 + ihl + 20:
                tcp_header = raw_data[14+ihl:14+ihl+20]
                src_port, dest_port = struct.unpack('!HH', tcp_header[:4])
            elif protocol == 17 and len(raw_data) >= 14 + ihl + 8:
                udp_header = raw_data[14+ihl:14+ihl+8]
                src_port, dest_port = struct.unpack('!HH', udp_header[:4])

            # Filtrar por puerto
            if src_port == filtro_puerto or dest_port == filtro_puerto:
                print(f"\n[+] Trama Detectada:")
                print(f"    |- MAC Origen: {format_mac(src_mac)} -> MAC Destino: {format_mac(dest_mac)}")
                print(f"    |- IP Versión: {version} | Tamaño Cabecera: {ihl} bytes | TTL: {ttl}")
                print(f"    |- Protocolo: {proto_name} ({protocol})")
                print(f"    |- Ruta: {src_ip}:{src_port} -> {dest_ip}:{dest_port}")

if __name__ == "__main__":
    main()
