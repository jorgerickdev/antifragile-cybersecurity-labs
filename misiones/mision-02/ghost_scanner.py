import socket
import struct
import sys
import time

def checksum(msg):
    """Calcula el Checksum de Internet (RFC 1071) sobre bloques de 16 bits."""
    s = 0
    # Iterar de 2 en 2 bytes
    for i in range(0, len(msg), 2):
        if i + 1 < len(msg):
            w = (msg[i] << 8) + msg[i+1]
            s += w
        else:
            s += (msg[i] << 8)
    
    # Plegado de bits de acarreo
    s = (s >> 16) + (s & 0xffff)
    s += (s >> 16)
    s = ~s & 0xffff
    return s

def crear_cabecera_tcp(ip_origen, ip_destino, puerto_origen, puerto_destino, flag_type="SYN"):
    """Forja la cabecera TCP binaria de 20 bytes con su pseudo-cabecera IP para el Checksum."""
    seq = 4543261
    ack_seq = 0
    doff = 5  # Data Offset: 5 palabras de 32 bits = 20 bytes
    
    # Configuración de Banderas (Flags)
    fin = 1 if flag_type == "FIN" else 0
    syn = 1 if flag_type == "SYN" else 0
    rst = 1 if flag_type == "RST" else 0
    psh, ack, urg = 0, 0, 0
    
    offset_res = (doff << 4) + 0
    tcp_flags = fin + (syn << 1) + (rst << 2) + (psh << 3) + (ack << 4) + (urg << 5)
    window = 5840
    check = 0
    urg_ptr = 0

    # 1. Cabecera temporal con Checksum = 0
    tcp_header_temp = struct.pack('!HHLLBBHHH', 
                                  puerto_origen, puerto_destino, 
                                  seq, ack_seq, 
                                  offset_res, tcp_flags, 
                                  window, check, urg_ptr)

    # 2. Pseudo-Cabecera IP (12 bytes) requerida por el estándar TCP para el Checksum
    src_addr = socket.inet_aton(ip_origen)
    dst_addr = socket.inet_aton(ip_destino)
    placeholder = 0
    protocol = socket.IPPROTO_TCP
    tcp_length = len(tcp_header_temp)

    pseudo_header = struct.pack('!4s4sBBH', 
                                src_addr, dst_addr, 
                                placeholder, protocol, tcp_length)

    # 3. Calcular Checksum real sobre Pseudo-Cabecera + Cabecera TCP
    total_msg = pseudo_header + tcp_header_temp
    user_checksum = checksum(total_msg)

    # 4. Re-empaquetar la Cabecera TCP final con el Checksum correcto en Big-Endian
    tcp_header_final = struct.pack('!HHLLBBHHH', 
                                   puerto_origen, puerto_destino, 
                                   seq, ack_seq, 
                                   offset_res, tcp_flags, 
                                   window, user_checksum, urg_ptr)
                             
    return tcp_header_final

def escanear_puerto(target_ip, target_port, ip_origen="192.168.100.21", scan_type="SYN"):
    puerto_origen = 54321

    # Crear socket RAW para escuchar respuestas TCP del objetivo
    recv_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    recv_socket.settimeout(2.5)  # Esperar respuesta máximo 2.5 segundos

    # Crear socket RAW de inyección IP
    #send_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    send_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)

    # Forjar paquete y enviar
    tcp_header = crear_cabecera_tcp(ip_origen, target_ip, puerto_origen, target_port, flag_type=scan_type)
    send_socket.sendto(tcp_header, (target_ip, target_port))
    print(f"[+] Paquete {scan_type} inyectado hacia {target_ip}:{target_port}...")

    # Bucle de escucha e interpretación de respuesta
    try:
        inicio = time.time()
        while True:
            # Si se excede el tiempo
            if time.time() - inicio > 2.5:
                raise socket.timeout

            raw_data, addr = recv_socket.recvfrom(65565)
            
            # Filtrar solo paquetes provenientes de la IP objetivo
            if addr[0] == target_ip:
                # Extraer tamaño de la cabecera IP (IHL)
                ihl = (raw_data[0] & 0x0F) * 4
                
                # Desempaquetar puertos y banderas de la respuesta TCP
                src_port, dst_port, seq, ack, offset_res, flags = struct.unpack('!HHLLBB', raw_data[ihl:ihl+14])

                # Verificar que el paquete corresponde a nuestra prueba
                if src_port == target_port and dst_port == puerto_origen:
                    # Banderas evaluadas
                    is_syn_ack = (flags & 0x12) == 0x12  # SYN (0x02) + ACK (0x10)
                    is_rst = (flags & 0x04) == 0x04      # RST (0x04)

                    if is_syn_ack:
                        print(f"🟢 [RESPUESTA SYN-ACK] Puerto {target_port} en {target_ip} está ABIERTO.")
                        # Enviar RST inmediato para abortar la conexión y no dejar log de aplicación
                        rst_header = crear_cabecera_tcp(ip_origen, target_ip, puerto_origen, target_port, flag_type="RST")
                        send_socket.sendto(rst_header, (target_ip, target_port))
                        print("    └─ [ABORTADO] Se envió paquete RST para mantener el escaneo Stealth.")
                        return "OPEN"

                    elif is_rst:
                        print(f"🔴 [RESPUESTA RST] Puerto {target_port} en {target_ip} está CERRADO.")
                        return "CLOSED"

    except socket.timeout:
        if scan_type == "SYN":
            print(f"🟡 [TIMEOUT] Sin respuesta. El puerto {target_port} en {target_ip} está FILTRADO (Firewall / Drop).")
            return "FILTERED"
        elif scan_type == "FIN":
            print(f"👻 [RFC 793 SILENCIO] Sin respuesta en modo FIN. El puerto {target_port} en {target_ip} está ABIERTO/STEALTH.")
            return "OPEN|STEALTH"
    finally:
        send_socket.close()
        recv_socket.close()

if __name__ == '__main__':
    print("=" * 65)
    print("      GHOST SCANNER - Escáner Stealth Bare-Metal (Python RAW)")
    print("=" * 65)

    if len(sys.argv) < 2:
        print("Uso: sudo python3 ghost_scanner.py <IP>:<PUERTO> [SYN|FIN]")
        print("Ejemplo 1: sudo python3 ghost_scanner.py 192.168.100.13:8080")
        print("Ejemplo 2: sudo python3 ghost_scanner.py 192.168.100.13:8080 FIN")
        sys.exit(1)

    target_arg = sys.argv[1]
    scan_mode = sys.argv[2].upper() if len(sys.argv) > 2 else "SYN"

    if ":" in target_arg:
        target_ip, target_port = target_arg.split(":")
        target_port = int(target_port)
    else:
        target_ip = target_arg
        target_port = 8080

    # Ajusta esta IP si cambia tu eno1
    IP_LOCAL_UBUNTU = "192.168.100.21"

    escanear_puerto(target_ip, target_port, ip_origen=IP_LOCAL_UBUNTU, scan_type=scan_mode)