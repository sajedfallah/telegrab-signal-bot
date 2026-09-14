from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    os.chdir(ROOT)
    print("NEXUS Provider Panel preview: http://127.0.0.1:8091")
    ThreadingHTTPServer(("127.0.0.1", 8091), SimpleHTTPRequestHandler).serve_forever()
