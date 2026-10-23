import subprocess
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_cli_execution():
    # 1. create-api-key
    res_key = subprocess.run(
        [sys.executable, "-m", "app.cli", "create-api-key", "--name", "Pytest Key"],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert res_key.returncode == 0
    assert "API KEY CREATED SUCCESSFULLY" in res_key.stdout
    assert "sms_live_" in res_key.stdout

    # 2. create-pairing-code
    res_pair = subprocess.run(
        [sys.executable, "-m", "app.cli", "create-pairing-code", "--name", "Pytest Device"],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert res_pair.returncode == 0
    assert "DEVICE PAIRING CODE GENERATED" in res_pair.stdout
    assert "Pairing Code:" in res_pair.stdout

    # 3. list-api-keys
    res_lkeys = subprocess.run(
        [sys.executable, "-m", "app.cli", "list-api-keys"],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert res_lkeys.returncode == 0
    assert "Pytest Key" in res_lkeys.stdout

    # 4. list-devices
    res_ldevs = subprocess.run(
        [sys.executable, "-m", "app.cli", "list-devices"],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert res_ldevs.returncode == 0

    # 5. list-messages
    res_lmsgs = subprocess.run(
        [sys.executable, "-m", "app.cli", "list-messages"],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert res_lmsgs.returncode == 0
