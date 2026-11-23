#!/usr/bin/env python3
"""
Tiny server for the WebXR STL/OBJ inspector.

Serves the folder this script lives in (index.html + models) and implements
api.php?action=list|upload|delete so uploaded .stl / .obj files are stored
right next to index.html.

  python3 server.py                 # http://localhost:8000
  python3 server.py --https         # https://<your-LAN-IP>:8443 (self-signed cert, for Quest over Wi-Fi)
  python3 server.py --https --cert my.crt --key my.key
"""
import argparse
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_EXT = (".stl", ".obj")
MAX_UPLOAD = 2 * 1024 ** 3  # 2 GB
CERT_DIR = os.path.join(ROOT, ".certs")


def safe_name(raw):
    name = os.path.basename((raw or "").replace("\\", "/"))
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .")
    stem, ext = os.path.splitext(name)
    if not stem or ext.lower() not in MODEL_EXT:
        return None
    return stem[:150] + ext.lower()


def unique_path(name):
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(ROOT, name), 1
    while os.path.exists(path):
        path = os.path.join(ROOT, f"{stem}_{n}{ext}")
        n += 1
    return path


def list_models():
    files = []
    for e in os.scandir(ROOT):
        if e.is_file() and e.name.lower().endswith(MODEL_EXT):
            st = e.stat()
            files.append({"name": e.name, "size": st.st_size, "mtime": int(st.st_mtime)})
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return files


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".stl": "model/stl", ".obj": "model/obj", ".js": "text/javascript", ".mjs": "text/javascript"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    # --- helpers ---
    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        u = urlparse(self.path)
        if u.path != "/api.php":
            return None, None
        return parse_qs(u.query).get("action", ["list"])[0], parse_qs(u.query)

    def hidden(self):
        # never serve dotfiles/dot-folders (e.g. .certs/key.pem) or this script
        parts = [p for p in unquote(urlparse(self.path).path).split("/") if p]
        return any(p.startswith(".") for p in parts) or (parts and parts[-1] == os.path.basename(__file__))

    # --- verbs ---
    def do_GET(self):
        action, _ = self.route()
        if action == "list":
            return self.send_json(200, {"ok": True, "files": list_models()})
        if action:
            return self.send_json(405, {"ok": False, "error": "use POST for " + action})
        if self.hidden():
            return self.send_error(404)
        return super().do_GET()

    def do_HEAD(self):
        if self.hidden():
            return self.send_error(404)
        return super().do_HEAD()

    def do_POST(self):
        action, qs = self.route()
        if action is None:
            return self.send_json(404, {"ok": False, "error": "not found"})
        name = safe_name(qs.get("name", [""])[0])
        if action == "upload":
            return self.upload(name)
        if action == "delete":
            if not name:
                return self.send_json(400, {"ok": False, "error": "bad file name"})
            path = os.path.join(ROOT, name)
            if not os.path.isfile(path):
                return self.send_json(404, {"ok": False, "error": "no such file"})
            os.remove(path)
            return self.send_json(200, {"ok": True, "name": name})
        return self.send_json(400, {"ok": False, "error": "unknown action"})

    def upload(self, name):
        if not name:
            return self.send_json(400, {"ok": False, "error": "only .stl and .obj files are allowed"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return self.send_json(411, {"ok": False, "error": "empty upload"})
        if length > MAX_UPLOAD:
            return self.send_json(413, {"ok": False, "error": "file too large"})
        fd, tmp = tempfile.mkstemp(dir=ROOT, prefix=".upload-", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as out:
                left = length
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        raise IOError("connection closed during upload")
                    out.write(chunk)
                    left -= len(chunk)
            final = unique_path(name)
            os.replace(tmp, final)
            os.chmod(final, 0o644)
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            return self.send_json(500, {"ok": False, "error": str(e)})
        saved = os.path.basename(final)
        self.log_message("saved upload %s (%d bytes)", saved, length)
        return self.send_json(200, {"ok": True, "name": saved})


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def ensure_cert(ip):
    cert, key = os.path.join(CERT_DIR, "cert.pem"), os.path.join(CERT_DIR, "key.pem")
    if os.path.exists(cert) and os.path.exists(key):
        return cert, key
    os.makedirs(CERT_DIR, exist_ok=True)
    san = f"subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{ip}"
    cmd = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
           "-days", "825", "-subj", "/CN=webxr-stl-obj-viewer", "-addext", san]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit("Could not create a self-signed certificate with openssl (%s).\n"
                 "Install openssl, or pass your own with --cert/--key." % e)
    print("Created self-signed certificate in", CERT_DIR)
    return cert, key


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int)
    ap.add_argument("--https", action="store_true", help="serve over HTTPS (required by Quest when not on localhost)")
    ap.add_argument("--cert")
    ap.add_argument("--key")
    a = ap.parse_args()
    port = a.port or (8443 if a.https else 8000)
    ip = lan_ip()
    httpd = ThreadingHTTPServer((a.host, port), Handler)
    scheme = "http"
    if a.https:
        cert, key = (a.cert, a.key) if a.cert and a.key else ensure_cert(ip)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    print(f"Serving {ROOT}")
    print(f"  This PC : {scheme}://localhost:{port}/")
    print(f"  Quest   : {scheme}://{ip}:{port}/" + ("" if a.https else "   (needs --https, or adb reverse to use localhost)"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
