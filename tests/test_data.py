"""The data fetchers against canned API replies (no network, no keys), and the chart command. Run: python3 tests/test_data.py"""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
os.environ.update(FRED_API_KEY="k", EIA_API_KEY="k")
from docgen import data
def check(name, ok, info=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {info}"))
    if not ok: sys.exit(1)
def fake(url, body=None):
    if "series/observations" in url: return {"observations": [{"date": "1971-07-01", "value": "40.5"}, {"date": "1971-08-01", "value": "."}, {"date": "1971-09-01", "value": "40.8"}]}
    if "stlouisfed.org/fred/series?" in url: return {"seriess": [{"title": "Consumer Price Index", "units": "Index"}]}
    if "bls.gov" in url: return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [{"year": "2001", "period": "M02", "value": "3"}, {"year": "2001", "period": "M01", "value": "2"}]}]}}
    if "eia.gov" in url: assert "facets%5Bduoarea%5D%5B%5D=NUS" in url, url; return {"response": {"data": [{"period": "2001", "value": "20.5", "units": "dollars per barrel"}]}}
    if "imf.org" in url: return {"values": {"NGDP_RPCH": {"USA": {"1990": 1.9, "1991": -0.1, "2030": 2}}}, "indicators": {"NGDP_RPCH": {"label": "Real GDP growth", "unit": "Annual percent change"}}}
data.get = fake
f = data.fred({"pos": ["CPIAUCSL"]}); check("fred: missing values skipped, title and url set", [p["y"] for p in f["points"]] == [40.5, 40.8] and f["title"] == "Consumer Price Index" and f["url"].endswith("/CPIAUCSL"), f)
b = data.bls({"pos": ["X"]}); check("bls: oldest first", [p["x"] for p in b["points"]] == ["2001-01", "2001-02"], b)
e = data.eia({"pos": ["petroleum/pri/spt"], "facet": ["duoarea=NUS"]}); check("eia: facets passed, values read", e["points"] == [{"x": "2001", "y": 20.5}] and e["units"].startswith("dollars"), e)
i = data.imf({"pos": ["NGDP_RPCH", "USA"], "end": "2024"}); check("imf: range applied", [p["x"] for p in i["points"]] == ["1990", "1991"] and i["title"] == "Real GDP growth", i)
d = tempfile.mkdtemp(); json.dump(f | {"points": [{"x": str(1960 + k), "y": k * 2.0} for k in range(10)]}, open(f"{d}/x.json", "w"))
env = dict(os.environ, PYTHONPATH=ROOT, DOCGEN_REMOTION=os.path.join(ROOT, "remotion"))
if os.path.isdir(os.path.join(ROOT, "remotion", "bundle")):
    r = subprocess.run([sys.executable, "-m", "docgen", "chart", "t", "--data", "x.json", "--title", "T", "--seconds", "3"], cwd=d, env=env, capture_output=True, text=True)
    check("chart renders a clip and a still", r.returncode == 0 and os.path.exists(f"{d}/shorts/assets/ltx_chart_t.mp4") and os.path.exists(f"{d}/shorts/assets/chart_t.png"), r.stderr[-500:])
r = subprocess.run([sys.executable, "-m", "docgen", "chart", "t", "--data", "x.json", "--title", "T", "--highlight", "1900"], cwd=d, env=env, capture_output=True, text=True)
check("a highlight that is not in the data is refused", r.returncode != 0 and "not an x value" in r.stderr, r.stderr)
print("\nALL CHECKS PASSED")
