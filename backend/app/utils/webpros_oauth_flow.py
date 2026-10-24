#!/usr/bin/env python3
"""
webpros_oauth_flow.py
Local OAuth authorization listener and token exchanger for WebPros MCP.
"""

import os
import sys
import json
import time
import base64
import hashlib
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

CLIENT_ID = "Hf3QmY8LpRs2KaV7NxTwJe6CgUz9BdMiP4vXnLq1Zo"
PORT = 64474
REDIRECT_URI = f"http://localhost:{PORT}/callback"
AUTH_ENDPOINT = "https://login.webpros.com/oauth2/auth"
TOKEN_ENDPOINT = "https://login.webpros.com/oauth2/token"
MCP_CONFIG_PATH = "/home/hacker/.gemini/config/mcp_config.json"
TOKEN_CACHE_PATH = "/home/hacker/.gemini/config/webpros_tokens.json"

# Generate PKCE verifier & challenge
code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).decode().rstrip("=")
state_token = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet default logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/callback", "/oauth/callback", "/"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        if error or not code:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h3>OAuth Authorization Failed: {error or 'No code provided'}</h3>".encode())
            return

        # Exchange authorization code for tokens
        token_payload = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        }).encode()

        try:
            req = urllib.request.Request(
                TOKEN_ENDPOINT,
                data=token_payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Antigravity-WebPros-MCP/1.0",
                },
            )
            with urllib.request.urlopen(req) as resp:
                token_data = json.loads(resp.read().decode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h3>Token exchange failed: {e}</h3>".encode())
            return

        # Save tokens
        access_token = token_data.get("access_token")
        with open(TOKEN_CACHE_PATH, "w") as f:
            json.dump(token_data, f, indent=2)

        # Update mcp_config.json with active Authorization header
        if os.path.exists(MCP_CONFIG_PATH):
            try:
                with open(MCP_CONFIG_PATH, "r") as f:
                    cfg = json.load(f)
                if "mcpServers" in cfg:
                    cfg["mcpServers"]["webpros-mcp"] = {
                        "type": "http",
                        "url": "https://mcp.webpros.com/api/mcp",
                        "serverUrl": "https://mcp.webpros.com/api/mcp",
                        "headers": {
                            "Authorization": f"Bearer {access_token}"
                        },
                        "oauth": {
                            "clientId": CLIENT_ID,
                            "callbackPort": PORT
                        }
                    }
                    with open(MCP_CONFIG_PATH, "w") as f:
                        json.dump(cfg, f, indent=2)
            except Exception as ex:
                sys.stderr.write(f"Warning: could not update mcp_config.json: {ex}\n")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>WebPros Authorization Success</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 40px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); text-align: center; max-width: 480px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
            h2 { color: #10b981; margin-top: 0; }
            p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
            .badge { display: inline-block; background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 12px; margin-bottom: 16px; }
          </style>
        </head>
        <body>
          <div class="card">
            <span class="badge">&#10003; AUTHENTICATED</span>
            <h2>WebPros cPanel MCP Connected!</h2>
            <p>Your WebPros / cPanel authorization token has been securely acquired and saved to Antigravity.</p>
            <p>You can now close this browser tab and return to the assistant.</p>
          </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
        sys.stderr.write("SUCCESS: WebPros MCP Token successfully acquired and saved!\n")

        # Schedule server shutdown
        import threading
        threading.Thread(target=lambda: (time.sleep(1), self.server.shutdown())).start()


def get_auth_url():
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid offline_access email profile mcp",
        "redirect_uri": REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state_token,
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


if __name__ == "__main__":
    auth_url = get_auth_url()
    print("=================================================================")
    print("WEBPROS CPANEL MCP AUTHORIZATION")
    print("=================================================================")
    print("Please open the following authorization URL in your browser:")
    print()
    print(auth_url)
    print()
    print("Listening on http://localhost:64474/oauth/callback...")
    print("=================================================================")
    sys.stdout.flush()

    server = HTTPServer(("0.0.0.0", PORT), OAuthCallbackHandler)
    server.serve_forever()
