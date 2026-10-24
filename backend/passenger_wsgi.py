"""
passenger_wsgi.py - Phusion Passenger entrypoint for cPanel / CloudLinux.
Serves the SIM SMS Gateway FastAPI (ASGI) application via a2wsgi under Phusion Passenger WSGI.
Domain: sms.edusphere.co.tz
"""

import sys
import os

# Ensure backend directory is first in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Ensure common cPanel paths are in PATH
extra_bin_dirs = [
    "/home/eduspher/bin",
    "/home/eduspher/.local/bin",
]
current_path = os.environ.get("PATH", "")
for bdir in extra_bin_dirs:
    if os.path.isdir(bdir) and bdir not in current_path:
        current_path = f"{bdir}:{current_path}"
os.environ["PATH"] = current_path

# Import FastAPI ASGI application
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
