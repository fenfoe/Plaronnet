import os
import re
import ssl
import time
import shutil
import socket
import concurrent.futures
from datetime import datetime
 
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from cryptography import x509
from cryptography.hazmat.backends import default_backend
 

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    80: "HTTP", 443: "HTTPS", 554: "RTSP", 3306: "MySQL", 3389: "RDP",
    5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB",
    8080: "HTTP-Alt",
}
 
# Keep a reference to the real socket class so we can restore it after toggling Tor off.
_REAL_SOCKET = socket.socket
 
 
def set_tor_enabled(enabled: bool):
    """Route subsequent socket connections through Tor's local SOCKS proxy,
    or restore normal direct sockets."""
    if enabled:
        import socks  # PySocks
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
        socket.socket = socks.socksocket
    else:
        socket.socket = _REAL_SOCKET
 
 
def grab_banner(ip, port, connect_timeout=1.0, read_timeout=1.0):
    """Connect and grab whatever the service sends first (or a HEAD
    response for HTTP-ish ports). connect_timeout and read_timeout are
    separate: connect_timeout matters most for filtered/firewalled ports
    (which silently drop packets and force the full wait), read_timeout
    matters most for open ports that don't greet immediately."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(connect_timeout)
        s.connect((ip, port))
        banner = ""
        try:
            s.settimeout(read_timeout)
            data = s.recv(1024)
            banner = data.decode(errors="ignore").strip()
        except socket.timeout:
            pass
        if port in (80, 8080) and not banner:
            try:
                s.send(b"HEAD / HTTP/1.0\r\n\r\n")
                data = s.recv(1024)
                banner = data.decode(errors="ignore").strip()
            except Exception:
                pass
        s.close()
        return banner
    except Exception:
        return None
 
 
# ---------------------------------------------------------------------------
# Passive fingerprinting: parse what the service already tells us.
# No packet crafting / OS-guessing — just banners, headers, and certs.
# ---------------------------------------------------------------------------
 
VERSION_PATTERNS = {
    22: re.compile(r"SSH-\d\.\d-(\S+)"),                         # SSH-2.0-OpenSSH_8.9p1
    21: re.compile(r"^220[- ](.+)"),                              # FTP welcome banner
    25: re.compile(r"^220[- ](.+)"),                              # SMTP welcome banner
    23: re.compile(r"(.+)"),                                      # Telnet: whatever it prints
}
 
 
def fingerprint_banner(port, banner):
    """Extract a version/product string from a raw banner using known
    per-protocol patterns. Returns None if nothing recognizable."""
    if not banner:
        return None
    pattern = VERSION_PATTERNS.get(port)
    if not pattern:
        return None
    m = pattern.search(banner.splitlines()[0] if banner else "")
    return m.group(1).strip() if m else None
 
 
def get_tls_cert_info(ip, port, timeout=4):
    """Fetch and parse the TLS certificate presented on connect. Purely
    passive — same as what your browser sees on the handshake, just
    without a GET request. Returns a dict or None on failure."""
    try:
        pem = ssl.get_server_certificate((ip, port), timeout=timeout)
        cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            sans = san_ext.value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            sans = []
        not_after = cert.not_valid_after_utc.isoformat() if hasattr(cert, "not_valid_after_utc") \
            else cert.not_valid_after.isoformat()
        return {
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "not_after": not_after,
            "sans": sans,
            "serial": str(cert.serial_number),
        }
    except Exception:
        return None
 
 
WEB_PORTS = {80: "http", 443: "https", 8080: "http"}
 
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
 
 
def extract_title(html: str):
    match = TITLE_RE.search(html)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()[:150]
    return None
 
 
def save_page_snapshot(ip, port, session_dir, timeout=4):
    """Fetch the full page for a web port and save it to a temp file in
    session_dir. Returns (file_path, title, headers_dict) — file_path/title
    are None on failure, headers_dict is {} on failure.
    Files here are meant to be short-lived: the caller deletes session_dir
    once the scan finishes."""
    scheme = WEB_PORTS.get(port, "http")
    url = f"{scheme}://{ip}:{port}/"
    try:
        r = requests.get(url, timeout=timeout, verify=False)
        html = r.text
        headers = dict(r.headers)
    except Exception:
        return None, None, {}
 
    os.makedirs(session_dir, exist_ok=True)
    fname = os.path.join(session_dir, f"{ip.replace(':', '_')}_{port}_{int(time.time()*1000)}.html")
    try:
        with open(fname, "w", encoding="utf-8", errors="ignore") as f:
            f.write(html)
    except OSError:
        return None, extract_title(html), headers
 
    return fname, extract_title(html), headers
 
 
def scan_target(ip, port, session_dir=None, connect_timeout=1.0, read_timeout=1.0):
    """Scan exactly one (ip, port). Returns an entry dict if the port is
    open, or None if it's closed/filtered/unreachable."""
    banner = grab_banner(ip, port, connect_timeout=connect_timeout, read_timeout=read_timeout)
    if banner is None:
        return None
    entry = {
        "service_guess": COMMON_PORTS.get(port, "unknown"),
        "banner": banner,
        "version": fingerprint_banner(port, banner),
        "timestamp": datetime.utcnow().isoformat(),
    }
    if port in WEB_PORTS and session_dir:
        html_path, title, headers = save_page_snapshot(ip, port, session_dir)
        entry["html_path"] = html_path
        entry["page_title"] = title
        entry["http_server"] = headers.get("Server")
        entry["x_powered_by"] = headers.get("X-Powered-By")
        if not entry["version"]:
            entry["version"] = headers.get("Server")
    if port == 443:
        entry["tls"] = get_tls_cert_info(ip, port)
    return entry
 
 
def scan_host(ip, ports, session_dir=None, connect_timeout=1.0, read_timeout=1.0, max_workers=None):
    """Scan every port for a single host CONCURRENTLY (a thread per port,
    capped at max_workers) instead of one at a time — this is the main
    speedup for a single-host detailed scan."""
    results = {}
    workers = max_workers or min(len(ports), 25)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(workers, 1)) as ex:
        futures = {
            ex.submit(scan_target, ip, port, session_dir, connect_timeout, read_timeout): port
            for port in ports
        }
        for future in concurrent.futures.as_completed(futures):
            port = futures[future]
            entry = future.result()
            if entry is not None:
                results[port] = entry
    return {"ip": ip, "open_ports": results}
 
 
def scan_many(targets, ports, session_dir=None, connect_timeout=1.0, read_timeout=1.0,
              max_workers=100, on_host_done=None):
    """Scan many hosts' ports through a SINGLE flat thread pool instead of
    nesting a per-host pool inside a per-target pool.
 
    Calls on_host_done(host_result) as soon as ALL of a given host's
    ports have finished.
 
    Returns the full list of per-host results at the end.
    """
    tasks = [(ip, port) for ip in targets for port in ports]
    if not tasks:
        return []
    pending = {ip: len(ports) for ip in targets}
    per_host = {ip: {} for ip in targets}
    all_results = []
 
    workers = max(1, min(max_workers, len(tasks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(scan_target, ip, port, session_dir, connect_timeout, read_timeout): (ip, port)
            for ip, port in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            ip, port = futures[future]
            try:
                entry = future.result()
            except Exception:
                entry = None
            if entry is not None:
                per_host[ip][port] = entry
            pending[ip] -= 1
            if pending[ip] == 0:
                host_result = {"ip": ip, "open_ports": per_host[ip]}
                all_results.append(host_result)
                if on_host_done:
                    on_host_done(host_result)
    return all_results
 
 
def expand_targets(raw: str):
    """Accepts comma/space/newline separated hosts or IPs, plus simple
    'base.octet-start-end' ranges like 192.168.1.1-10."""
    targets = []
    for chunk in raw.replace(",", " ").split():
        if "-" in chunk and chunk.count(".") == 3:
            base, rng = chunk.rsplit(".", 1)
            if "-" in rng:
                start, end = rng.split("-")
                for i in range(int(start), int(end) + 1):
                    targets.append(f"{base}.{i}")
                continue
        targets.append(chunk)
    return targets

