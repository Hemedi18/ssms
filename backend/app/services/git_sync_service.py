"""
git_sync_service.py
DevOps & cPanel Git Live Synchronization Engine for SIM SMS Gateway.
Handles change detection, commit comparisons, one-click automated pulling,
and cPanel Phusion Passenger restarts.
"""

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# In-memory cache for status check to prevent hammering remote git
_git_status_cache: Optional[Dict[str, Any]] = None
_git_status_cache_time: float = 0
CACHE_TTL_SECONDS = 30


def find_git_root(start_dir: Optional[str] = None) -> Optional[str]:
    """Finds the root directory containing .git starting from start_dir."""
    if not start_dir:
        start_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cur = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _run_git_cmd(cmd_list: list, cwd: str, timeout: int = 15) -> Dict[str, Any]:
    """Safely executes a git command in cwd with timeout."""
    try:
        p = subprocess.run(
            cmd_list,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": p.returncode == 0,
            "stdout": (p.stdout or "").strip(),
            "stderr": (p.stderr or "").strip(),
            "returncode": p.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }


def get_git_sync_status(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Checks local commit against remote repository and returns diff status.
    Uses cached result if within CACHE_TTL_SECONDS unless force_refresh is True.
    """
    global _git_status_cache, _git_status_cache_time
    now = time.time()

    if not force_refresh and _git_status_cache and (now - _git_status_cache_time < CACHE_TTL_SECONDS):
        return _git_status_cache

    git_root = find_git_root()
    if not git_root:
        return {
            "success": False,
            "error": "Git repository root (.git) not found on this server",
            "has_update": False,
            "is_git_repo": False,
        }

    # 1. Determine active branch
    branch_res = _run_git_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    branch = branch_res["stdout"] if branch_res["success"] else "main"
    if not branch or branch == "HEAD":
        branch = "main"

    # 2. Local commit details
    local_hash_res = _run_git_cmd(["git", "rev-parse", "HEAD"], cwd=git_root)
    local_full = local_hash_res["stdout"] if local_hash_res["success"] else ""
    local_short = local_full[:7] if local_full else "unknown"

    local_subject_res = _run_git_cmd(["git", "log", "-1", "--format=%s"], cwd=git_root)
    local_subject = local_subject_res["stdout"] if local_subject_res["success"] else ""

    local_time_res = _run_git_cmd(["git", "log", "-1", "--format=%cd", "--date=relative"], cwd=git_root)
    local_time = local_time_res["stdout"] if local_time_res["success"] else ""

    # 3. Check remote commit via git ls-remote (fast, read-only)
    remote_full = ""
    remote_short = ""
    remote_subject = ""
    remote_res = _run_git_cmd(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=git_root, timeout=12)
    if remote_res["success"] and remote_res["stdout"]:
        first_line = remote_res["stdout"].splitlines()[0]
        remote_full = first_line.split()[0].strip()
        remote_short = remote_full[:7]

    # 4. Count commits behind / ahead
    ahead = 0
    behind = 0
    if remote_full and local_full and remote_full != local_full:
        # Fetch remote reference quietly to calculate rev-list accurately
        _run_git_cmd(["git", "fetch", "origin", branch, "--quiet"], cwd=git_root, timeout=15)
        count_res = _run_git_cmd(["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"], cwd=git_root, timeout=10)
        if count_res["success"] and count_res["stdout"]:
            try:
                parts = count_res["stdout"].split()
                if len(parts) >= 2:
                    ahead = int(parts[0])
                    behind = int(parts[1])
            except (ValueError, IndexError):
                pass

        remote_msg_res = _run_git_cmd(["git", "log", "-1", "--format=%s", f"origin/{branch}"], cwd=git_root)
        if remote_msg_res["success"]:
            remote_subject = remote_msg_res["stdout"]

    has_update = (behind > 0) or bool(remote_full and local_full and remote_full != local_full and ahead == 0)

    result = {
        "success": True,
        "is_git_repo": True,
        "branch": branch,
        "local_commit": local_short,
        "local_full_hash": local_full,
        "local_subject": local_subject,
        "local_time": local_time,
        "remote_commit": remote_short or local_short,
        "remote_full_hash": remote_full,
        "remote_subject": remote_subject,
        "ahead": ahead,
        "behind": behind,
        "has_update": has_update,
        "is_up_to_date": not has_update,
        "last_checked": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    }

    _git_status_cache = result
    _git_status_cache_time = now
    return result


def perform_git_sync() -> Dict[str, Any]:
    """
    Executes automated synchronization:
    1. git fetch origin <branch>
    2. git reset --hard origin/<branch>
    3. Reload cPanel Phusion Passenger via tmp/restart.txt
    """
    global _git_status_cache
    _git_status_cache = None  # Invalidate cache

    git_root = find_git_root()
    if not git_root:
        return {"success": False, "error": "Git repository root not found"}

    steps_log = []

    # Get active branch
    branch_res = _run_git_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    branch = branch_res["stdout"] if branch_res["success"] else "main"
    if not branch or branch == "HEAD":
        branch = "main"

    prev_res = _run_git_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=git_root)
    prev_commit = prev_res["stdout"] if prev_res["success"] else "unknown"

    # 1. Fetch remote
    fetch_res = _run_git_cmd(["git", "fetch", "origin", branch], cwd=git_root, timeout=30)
    steps_log.append({
        "step": f"git fetch origin {branch}",
        "success": fetch_res["success"],
        "output": fetch_res["stdout"] or fetch_res["stderr"],
    })
    if not fetch_res["success"]:
        return {
            "success": False,
            "error": f"Failed to fetch updates from remote: {fetch_res['stderr']}",
            "steps": steps_log,
        }

    # 2. Reset hard to remote branch
    reset_res = _run_git_cmd(["git", "reset", "--hard", f"origin/{branch}"], cwd=git_root, timeout=20)
    steps_log.append({
        "step": f"git reset --hard origin/{branch}",
        "success": reset_res["success"],
        "output": reset_res["stdout"] or reset_res["stderr"],
    })
    if not reset_res["success"]:
        return {
            "success": False,
            "error": f"Failed to align with remote branch: {reset_res['stderr']}",
            "steps": steps_log,
        }

    new_res = _run_git_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=git_root)
    new_commit = new_res["stdout"] if new_res["success"] else "unknown"

    # 3. Touch cPanel Phusion Passenger restart files
    restart_paths = [
        os.path.join(git_root, "tmp", "restart.txt"),
        os.path.join(git_root, "backend", "tmp", "restart.txt"),
    ]
    restarted = False
    for r_path in restart_paths:
        try:
            os.makedirs(os.path.dirname(r_path), exist_ok=True)
            with open(r_path, "w") as f:
                f.write(f"restarted at {datetime.now(timezone.utc).isoformat()}\n")
            restarted = True
        except Exception as e:
            logger.warning(f"Could not touch {r_path}: {e}")

    steps_log.append({
        "step": "touch tmp/restart.txt (cPanel Passenger reload)",
        "success": restarted,
        "output": "Passenger reload flag updated" if restarted else "Local file flag skipped",
    })

    return {
        "success": True,
        "message": f"Successfully updated from commit {prev_commit} to {new_commit} on {branch}. cPanel server reloaded.",
        "previous_commit": prev_commit,
        "new_commit": new_commit,
        "branch": branch,
        "steps": steps_log,
    }
