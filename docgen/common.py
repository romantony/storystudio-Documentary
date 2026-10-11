"""Shared helpers: keys from the environment, paths relative to the run folder (the current directory)."""
import json, os, re, subprocess, sys

ASSETS = os.environ.get("DOCGEN_ASSET_DIR", "shorts/assets")      # generated images, clips, voices, music
ARCHIVE = os.environ.get("DOCGEN_ARCHIVE_DIR", "images_period")   # downloaded archive images
UA = {"User-Agent": os.environ.get("DOCGEN_USER_AGENT", "docgen/1.0 (documentary toolkit)")}

# Fallback for local use only: a reference document that holds the keys. Not used in the container.
_DOC_PATTERNS = {"RUNPOD_API_KEY": r"rpa_[A-Za-z0-9_-]+", "GEMINI_API_KEY": r"AIza[A-Za-z0-9_-]{20,}",
                 "COMFY_API_KEY": r"comfyUI_API_KEY\W+([A-Za-z0-9_\-]+)"}

def key(name):
    """API key by env var name. Never print the return value."""
    v = os.environ.get(name)
    if v: return v
    doc = os.environ.get("DOCGEN_KEYS_DOC")
    if doc and os.path.exists(doc) and name in _DOC_PATTERNS:
        m = re.search(_DOC_PATTERNS[name], open(doc).read())
        if m: return m.group(m.lastindex or 0)
    sys.exit(f"missing {name} (set it in the environment)")

def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]))

def find_image(name):
    """An image by asset id or path: archive jpg first, then generated png."""
    if os.path.exists(name) and os.path.isfile(name): return name
    for p in (f"{ARCHIVE}/{name}.jpg", f"{ARCHIVE}/{name}.png", f"{ASSETS}/{name}.png", f"{ASSETS}/{name}.jpg"):
        if os.path.exists(p): return p
    return None

def load_script():
    d = json.load(open("script/script.json"))
    d.setdefault("slug", os.path.basename(os.getcwd()))
    return d

def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def mkdirs(*ds):
    for d in ds: os.makedirs(d, exist_ok=True)
