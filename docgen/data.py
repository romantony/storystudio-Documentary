"""Real data for the charts (FRED, BLS, EIA, IMF), as small JSON files a chart is drawn from. Never made up, never typed in from memory.

python3 -m docgen data fred <series_id> [--start 1960-01-01] [--end 2024-12-31] [--freq a] [--out data/<id>.json]
python3 -m docgen data bls <series_id> [--start 2000] [--end 2024]
python3 -m docgen data eia <route> [--facet key=value ...] [--freq annual] [--start 2000] [--end 2024] [--field value]
python3 -m docgen data imf <indicator> <country> [--start 1990] [--end 2024]     e.g. imf NGDP_RPCH USA (DataMapper, no key)
python3 -m docgen data file <csv> --title ... --source ... [--x col] [--y col]   a primary-source table you downloaded

Keys (env, never printed): FRED_API_KEY (required), EIA_API_KEY (required), BLS_API_KEY (optional, raises the limit); IMF needs none.
Output, default data/<source>_<id>.json:
  {"source": "FRED", "series_id": "CPIAUCSL", "title": "...", "units": "...", "url": "https://...", "points": [{"x": "1971-08", "y": 40.9}, ...]}
`url` is the page of the series, to cite in the description. Use the file in a chart: python3 -m docgen chart (docgen/chart.py).
--freq on FRED aggregates (a, q, m); thin a long series to 12-60 points before charting, the chart script does it for you."""
import csv, json, os, sys, urllib.parse, urllib.request
from .common import UA, key, mkdirs

def get(url, data=None):
    req = urllib.request.Request(url, data, {**UA, **({"Content-Type": "application/json"} if data else {})})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def fred(a):
    sid = a["pos"][0]; k = key("FRED_API_KEY")
    q = {"series_id": sid, "api_key": k, "file_type": "json", **{n: a[o] for o, n in (("start", "observation_start"), ("end", "observation_end"), ("freq", "frequency")) if a.get(o)}}
    if a.get("freq"): q["aggregation_method"] = "avg"
    obs = get("https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(q))["observations"]
    meta = get("https://api.stlouisfed.org/fred/series?" + urllib.parse.urlencode({"series_id": sid, "api_key": k, "file_type": "json"}))["seriess"][0]
    pts = [{"x": o["date"][:7] if a.get("freq") in ("m", None) and len(obs) < 800 else o["date"][:4], "y": float(o["value"])} for o in obs if o["value"] not in (".", "")]
    return {"source": "FRED, Federal Reserve Bank of St. Louis", "series_id": sid, "title": meta["title"], "units": meta.get("units", ""), "url": f"https://fred.stlouisfed.org/series/{sid}", "points": pts}

def bls(a):
    sid = a["pos"][0]; body = {"seriesid": [sid], "startyear": a.get("start") or "2000", "endyear": a.get("end") or "2024"}
    if os.environ.get("BLS_API_KEY"): body["registrationkey"] = os.environ["BLS_API_KEY"]
    r = get("https://api.bls.gov/publicAPI/v2/timeseries/data/", json.dumps(body).encode())
    if r.get("status") != "REQUEST_SUCCEEDED": sys.exit(f"bls: {r.get('message')}")
    s = r["Results"]["series"][0]["data"]
    pts = [{"x": f"{d['year']}-{d['period'][1:]}" if d["period"].startswith("M") and d["period"] != "M13" else d["year"], "y": float(d["value"])} for d in reversed(s) if d["value"] not in ("-", "")]
    return {"source": "U.S. Bureau of Labor Statistics", "series_id": sid, "title": s[0].get("seriesTitle") or sid, "units": "", "url": f"https://data.bls.gov/timeseries/{sid}", "points": pts}

def eia(a):
    route = a["pos"][0].strip("/"); k = key("EIA_API_KEY")
    q = [("api_key", k), ("frequency", a.get("freq") or "annual"), ("data[0]", a.get("field") or "value"), ("sort[0][column]", "period"), ("sort[0][direction]", "asc"), ("length", "5000")]
    q += [(f"facets[{f.split('=')[0]}][]", f.split("=", 1)[1]) for f in a.get("facet", [])]
    q += [(n, a[o]) for o, n in (("start", "start"), ("end", "end")) if a.get(o)]
    d = get(f"https://api.eia.gov/v2/{route}/data/?" + urllib.parse.urlencode(q))["response"]["data"]
    fld = a.get("field") or "value"
    return {"source": "U.S. Energy Information Administration", "series_id": route, "title": route.replace("/", " / "), "units": d[0].get("units", "") if d else "", "url": f"https://www.eia.gov/opendata/browser/{route}",
            "points": [{"x": r["period"], "y": float(r[fld])} for r in d if r.get(fld) not in (None, "")]}

def imf(a):
    ind, ctry = a["pos"][0], a["pos"][1]
    d = get(f"https://www.imf.org/external/datamapper/api/v1/{ind}/{ctry}")
    vals = d["values"][ind][ctry]; lab = d.get("indicators", {}).get(ind, {}) if isinstance(d.get("indicators"), dict) else {}
    lo, hi = int(a.get("start") or 0), int(a.get("end") or 9999)
    return {"source": "International Monetary Fund, World Economic Outlook", "series_id": f"{ind}/{ctry}", "title": lab.get("label") or ind, "units": lab.get("unit", ""),
            "url": f"https://www.imf.org/external/datamapper/{ind}@WEO/{ctry}", "points": [{"x": y, "y": float(v)} for y, v in sorted(vals.items()) if lo <= int(y) <= hi and v is not None]}

def from_file(a):
    rows = list(csv.DictReader(open(a["pos"][0]))); xc, yc = a.get("x") or list(rows[0])[0], a.get("y") or list(rows[0])[1]
    return {"source": a.get("source") or sys.exit("data file: --source is required"), "series_id": os.path.basename(a["pos"][0]), "title": a.get("title") or yc, "units": "",
            "url": a.get("url", ""), "points": [{"x": r[xc], "y": float(r[yc].replace(",", ""))} for r in rows if r[yc].strip() not in ("", "-")]}

SOURCES = {"fred": fred, "bls": bls, "eia": eia, "imf": imf, "file": from_file}

def parse_args(argv):
    a = {"pos": [], "facet": []}; i = 0
    while i < len(argv):
        if argv[i].startswith("--"):
            k = argv[i][2:]
            if k == "facet": a["facet"].append(argv[i + 1])
            else: a[k] = argv[i + 1]
            i += 2
        else: a["pos"].append(argv[i]); i += 1
    return a

def main(cmd, argv):
    if not argv or argv[0] not in SOURCES or len(argv) < 2: sys.exit(__doc__)
    src = argv[0]; a = parse_args(argv[1:]); res = SOURCES[src](a)
    if not res["points"]: sys.exit(f"data: no observations for {a['pos']}")
    out = a.get("out") or f"data/{src}_{a['pos'][0].replace('/', '_')}.json"
    mkdirs(os.path.dirname(out) or "."); json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({"file": out, "source": res["source"], "title": res["title"], "points": len(res["points"]), "first": res["points"][0], "last": res["points"][-1], "url": res["url"]}))
