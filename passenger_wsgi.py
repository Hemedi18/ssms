"""
passenger_wsgi.py - Phusion Passenger entrypoint for cPanel / CloudLinux (Root Wrapper).
Supports cPanel configurations pointing to repository root or /backend.
Domain: sms.edusphere.co.tz
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

# Ensure backend directory is first in sys.path
if os.path.isdir(BACKEND_DIR) and BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Common cPanel binary paths
extra_bin_dirs = [
    "/home/eduspher/bin",
    "/home/eduspher/.local/bin",
]
current_path = os.environ.get("PATH", "")
for bdir in extra_bin_dirs:
    if os.path.isdir(bdir) and bdir not in current_path:
        current_path = f"{bdir}:{current_path}"
os.environ["PATH"] = current_path

# Import FastAPI ASGI app
from app.main import app

# Adapt ASGI application to WSGI for cPanel Phusion Passenger
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(app)
except ImportError:
    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = b'Please install a2wsgi in your cPanel virtualenv: pip install a2wsgi'
        response_headers = [
            ('Content-type', 'text/plain; charset=utf-8'),
            ('Content-Length', str(len(output)))
        ]
        start_response(status, response_headers)
        return [output]
