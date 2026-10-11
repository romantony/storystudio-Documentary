"""Public-domain / open-licence archive images from Wikimedia Commons.
python3 -m docgen fetch-archive queries.json          download; writes build/period_assets.json and build/archive_sheet.jpg
python3 -m docgen fetch-archive --list "query text"   print the top candidates (title, width, licence) without downloading

queries.json: {"sumter": ["Bombardment of Fort Sumter 1861 Currier Ives", "second query"], "monitor": {"title": "File:Exact name.jpg"}}
Search results are often wrong (a 1909 parade came back for "plantation"). ALWAYS look at build/archive_sheet.jpg and
replace bad picks with an exact {"title": ...} before using the images."""
import json, os, re, sys, urllib.parse, urllib.request
from .common import ARCHIVE, UA, mkdirs
API = "https://commons.wikimedia.org/w/api.php?"
OK = re.compile(r"public domain|no restrictions|cc0|cc by(-sa)?[ -]\d|pd", re.I)
def get(params): return json.load(urllib.request.urlopen(urllib.request.Request(API + urllib.parse.urlencode(params), headers=UA), timeout=60))
def search(q, limit=8):
    r = get({"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrsearch": q + " filetype:bitmap", "gsrlimit": limit,
             "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 2400, "iiextmetadatafilter": "LicenseShortName|Artist"})
    return sorted(r.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
def by_title(t):
    r = get({"action": "query", "format": "json", "titles": t, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 2400, "iiextmetadatafilter": "LicenseShortName|Artist"})
    p = list(r["query"]["pages"].values())[0]; return p if "imageinfo" in p else None
def meta(p):
    ii = p["imageinfo"][0]; em = ii.get("extmetadata", {})
    return ii, em.get("LicenseShortName", {}).get("value", "?"), re.sub(r"<[^>]+>", "", em.get("Artist", {}).get("value", "")).strip()[:120]

def main(cmd, argv):
    if argv and argv[0] == "--list":
        for p in search(" ".join(argv[1:]), 10):
            ii, lic, art = meta(p); print(f"{p['title']} | {ii['width']}x{ii['height']} | {lic}")
        return
    if not argv: sys.exit(__doc__)
    Q = json.load(open(argv[0])); mkdirs(ARCHIVE, "build")
    PA = json.load(open("build/period_assets.json")) if os.path.exists("build/period_assets.json") else {}
    missing = []
    for k, q in Q.items():
        hit = None
        if isinstance(q, dict): hit = by_title(q["title"])
        else:
            for one in ([q] if isinstance(q, str) else q):
                hit = next((p for p in search(one) if meta(p)[0]["width"] >= 1000 and OK.search(meta(p)[1])), None)
                if hit: break
        if not hit: missing.append(k); print(k, "NOT FOUND"); continue
        ii, lic, art = meta(hit); dst = f"{ARCHIVE}/{k}.jpg"
        open(dst, "wb").write(urllib.request.urlopen(urllib.request.Request(ii.get("thumburl") or ii["url"], headers=UA), timeout=180).read())
        PA[k] = dict(path=dst, commons_title=hit["title"], license=lic, artist=art, source=ii.get("descriptionurl", ii["url"]), w=ii["width"], h=ii["height"],
                     needs_attribution=bool(re.search(r"\bBY\b", lic)))
        print(k, "|", hit["title"][5:75], "|", lic, flush=True)
    json.dump(PA, open("build/period_assets.json", "w"), indent=1, ensure_ascii=False)
    from .sheet import main as sheet; sheet("sheet", ["--archive", "--out", "build/archive_sheet.jpg"])
    if missing: print("missing:", missing); sys.exit(1)
