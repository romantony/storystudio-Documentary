import importlib, sys
CMDS = {"status": "status", "fetch-archive": "fetch_archive", "queue": "queue_assets", "tts": "narration", "timings": "narration",
        "assemble": "assemble_long", "short": "build_short", "card": "cards", "thumb": "thumb", "metadata": "metadata",
        "sheet": "sheet", "upload": "upload", "overlay": "overlay", "thumbnail": "thumbnail", "analyst": "analysts", "rubric": "analysts"}
if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
    sys.exit("usage: python3 -m docgen <" + "|".join(CMDS) + "> [args]   (run from the run folder)")
cmd = sys.argv[1]
importlib.import_module(f"docgen.{CMDS[cmd]}").main(cmd, sys.argv[2:])
