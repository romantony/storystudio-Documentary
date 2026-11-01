"""Wait for background work in one command instead of checking on it turn after turn (each check resends the whole session).
python3 -m docgen wait <file> [<file> ...] [--pid N ...] [--timeout 540]

Returns as soon as every file exists ("ready"), or when a --pid process has exited while a file is still missing ("exited": read its
log), or at --timeout seconds ("waiting": run the same command again). The default timeout stays under the Bash tool's 10 minutes."""
import json, os, sys, time

def alive(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    try:                                                    # a finished child of this shell is a zombie until reaped
        with open(f"/proc/{pid}/stat") as f: return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except Exception: return True

def main(cmd, argv):
    files, pids, timeout, i = [], [], 540.0, 0
    while i < len(argv):
        a = argv[i]
        if a == "--pid": pids.append(int(argv[i + 1])); i += 2
        elif a == "--timeout": timeout = float(argv[i + 1]); i += 2
        else: files.append(a); i += 1
    if not files: sys.exit(__doc__)
    t0 = time.time()
    while True:
        missing = [f for f in files if not os.path.exists(f)]
        if not missing: print(json.dumps({"result": "ready", "files": files, "seconds": round(time.time() - t0)})); return
        gone = [p for p in pids if not alive(p)]
        if pids and len(gone) == len(pids):
            print(json.dumps({"result": "exited", "missing": missing, "seconds": round(time.time() - t0)})); sys.exit(1)
        if time.time() - t0 >= timeout:
            print(json.dumps({"result": "waiting", "missing": missing, "seconds": round(time.time() - t0)})); sys.exit(2)
        time.sleep(3)
