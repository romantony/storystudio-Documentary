import json, os, re, urllib.parse, urllib.request
UA = {"User-Agent": "local-gen-doc/1.0 (github.com/romantony/storystudio-Documentary)"}
Q = {"coronation": ["Jacques-Louis David Coronation of Napoleon", "Sacre de Napoléon David"],
 "trafalgar": ["Battle of Trafalgar Turner painting", "Battle of Trafalgar Clarkson Stanfield"],
 "austerlitz": ["Bataille d'Austerlitz Gérard painting", "Battle of Austerlitz Gérard"],
 "moscow": ["Moscow fire 1812 painting Smirnov", "Napoleon Moscow fire 1812 Kremlin painting"],
 "borodino": ["Battle of Borodino Louis-François Lejeune", "Borodino 1812 painting"],
 "leipzig": ["Battle of Leipzig 1813 painting", "Völkerschlacht bei Leipzig painting Sauerweid"],
 "waterloo": ["Battle of Waterloo painting Wellington Napoleon Hillingford", "Waterloo 1815 painting Old Guard"],
 "elba": ["Napoleon Fontainebleau abdication painting Delaroche", "Napoleon abdication 1814 Fontainebleau"],
 "hundred_days": ["Napoleon returns from Elba 1815 painting Grenoble", "Retour de l'île d'Elbe Napoléon painting"],
 "sthelena": ["Napoleon on Saint Helena painting", "Napoleon St Helena Rock painting"],
 "vienna": ["Congress of Vienna Isabey painting", "Wiener Kongress Isabey"],
 "versailles": ["Proclamation of the German Empire Anton von Werner", "Kaiserproklamation Versailles Werner"],
 "reforms": ["Napoleon crossing the Alps David painting", "Bonaparte franchissant le Grand-Saint-Bernard"],
 "louisiana": ["Louisiana Purchase Napoleon treaty signing painting", "Louisiana Purchase Ceremony New Orleans 1803"],
 "legend": ["Tomb of Napoleon Les Invalides", "Napoleon tombeau Invalides"],
 "gillray": ["Gillray Little Boney", "Gillray Napoleon caricature"],
 "code": ["Code Napoleon 1804 original edition", "Code civil des Français 1804"]}
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))
out = {}
for key, qs in Q.items():
    hit = None
    for q in qs:
        u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({"action":"query","format":"json","generator":"search","gsrnamespace":6,"gsrsearch":q+" filetype:bitmap","gsrlimit":8,"prop":"imageinfo","iiprop":"url|size|extmetadata","iiurlwidth":2400,"iiextmetadatafilter":"LicenseShortName|Artist|Credit"})
        pages = sorted(get(u).get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        for p in pages:
            ii = p["imageinfo"][0]; lic = ii["extmetadata"].get("LicenseShortName", {}).get("value", "?")
            if ii["width"] >= 1200 and re.search(r"public domain|pd|cc0|cc by(-sa)? ", lic.lower() + " "): hit = (p, ii, lic); break
        if hit: break
    if not hit: print(key, "NOT FOUND"); continue
    p, ii, lic = hit; dst = f"images_period/{key}.jpg"
    open(dst, "wb").write(urllib.request.urlopen(urllib.request.Request(ii.get("thumburl") or ii["url"], headers=UA), timeout=120).read())
    out[key] = dict(path=dst, commons_title=p["title"], license=lic, source=ii.get("descriptionurl", ii["url"]), w=ii["width"], h=ii["height"])
    print(key, "|", p["title"][5:70], "|", lic, flush=True)
json.dump(out, open("build/period_assets.json", "w"), indent=1)
