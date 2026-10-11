import json, os, re, urllib.parse, urllib.request
UA = {"User-Agent": "local-gen-doc/1.0 (github.com/romantony/storystudio-Documentary)"}
Q = {"sumter": ["Bombardment of Fort Sumter 1861 Currier Ives", "Fort Sumter bombardment 1861 lithograph"],
 "divided": ["Slave states free states 1861 map Civil War", "United States 1861 map free states slave states Confederacy"],
 "plantation": ["Slaves cotton plantation Georgia photograph 1860s", "Enslaved people cotton field photograph"],
 "lincoln": ["Abraham Lincoln 1860 Brady portrait", "Abraham Lincoln O-77 portrait 1860"],
 "bullrun": ["First Battle of Bull Run Currier Ives", "Battle of Bull Run 1861 painting"],
 "industrial": ["Union railroad Civil War locomotive photograph", "USMRR Civil War railroad photograph"],
 "antietam": ["Antietam dead Confederate Dunker Church Gardner photograph", "Battle of Antietam dead photograph Alexander Gardner"],
 "brady": ["Mathew Brady portrait photographer", "Mathew Brady studio Civil War photographer"],
 "emancipation": ["Emancipation Proclamation 1863 document", "Emancipation Proclamation signing painting Carpenter"],
 "usct": ["United States Colored Troops soldier photograph Civil War", "African American soldier Union Army photograph"],
 "gettysburg": ["Gettysburg battlefield 1863 photograph O'Sullivan", "Harvest of Death Gettysburg"],
 "address": ["Abraham Lincoln Gettysburg Address photograph November 1863", "Lincoln Gettysburg November 19 1863 photograph"],
 "grant": ["Ulysses S. Grant Civil War photograph 1864", "General Grant Brady portrait 1864"],
 "richmond": ["Richmond ruins 1865 photograph", "Ruins of Richmond Virginia 1865 Gardner"],
 "ford": ["Ford's Theatre 1865 photograph", "Lincoln assassination 1865 Currier Ives"],
 "reconstruction": ["Freedmen's Bureau school 1866", "Freedmen school Reconstruction era engraving Harper's"],
 "federal": ["United States Capitol 1863 dome construction photograph", "Capitol building dome Civil War photograph"],
 "wwi": ["Petersburg trenches 1865 photograph Civil War", "Fort Mahone trenches Petersburg photograph"],
 "appomattox": ["Surrender of Lee at Appomattox Courthouse painting", "McLean House Appomattox Court House 1865 photograph"],
 "atlanta": ["Atlanta ruins 1864 photograph Barnard", "Atlanta Georgia ruined depot 1864 Sherman photograph"]}
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
