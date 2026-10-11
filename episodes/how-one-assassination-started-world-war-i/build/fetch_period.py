import json, os, urllib.parse, urllib.request
UA = {"User-Agent": "local-gen-doc/1.0 (github.com/romantony/storystudio-Documentary)"}
M = {1:("Sarajevo market 1914","Sarajevo market 1914.png"),
2:("Berlin 1914 street","Berlin (1914) (14597068158)"),
4:("Belgrade 1914","Belgrade decorated for the reception"),
5:("HMS Dreadnought 1906","HMS Dreadnought 1906.jpg"),
6:("Balkan War 1912 soldiers","BASA-1153K-1-8-41"),
7:("Nedeljko Cabrinovic","Čabrinović, Ilić, Princip.jpg"),
8:("Dragutin Dimitrijevic Apis","Dragutin Dimitrijevic Apis 1915"),
9:("Franz Ferdinand Sarajevo 1914","Franz Ferdinand & Sophie at Sarajevo Station"),
10:("Franz Ferdinand Sarajevo 1914","Leave Sarajevo Guildhall in a Car"),
11:("Gavrilo Princip arrest 1914","Arrest of a suspect in Sarajevo.jpg"),
12:("Paris crowd August 1914 mobilisation","Lecture des affiches 1914"),
13:("Franz Joseph 1914","Emperor Franz Joseph I of Austria and Archduke"),
15:("Russian soldiers 1914","The Russian army from within (1914)"),
16:("German soldiers train 1914","Long Trains Of Supplies Accompanying the German Armies"),
17:("Helmuth von Moltke the Younger","The Kaiser William II and Count von Moltke"),
18:("German soldiers marching 1914","German soldiers marching toward Albert, France LCCN2005697193.jpg"),
19:("British recruits 1914 enlisting","British Response to the Outbreak of War August 1914"),
20:("crowd Berlin August 1914","Crowd cheers the Kaiser at the Berliner Stadtschloss"),
21:("trench warfare World War I photograph","Cheshire Regiment trench Somme 1916"),
22:("Gallipoli 1915","ANZAC Mudros harbourl 1915"),
23:("Ypres ruins 1917","Chateau Wood Ypres 1917")}
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))
out = {}
for n, (q, key) in M.items():
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({"action":"query","format":"json","generator":"search","gsrnamespace":6,"gsrsearch":q+" filetype:bitmap","gsrlimit":30,"prop":"imageinfo","iiprop":"url|size|extmetadata","iiurlwidth":2880,"iiextmetadatafilter":"LicenseShortName|Artist|Credit"})
    pages = get(u).get("query", {}).get("pages", {})
    hit = next((p for p in pages.values() if key.lower() in p["title"].lower()), None)
    if not hit: print(n, "NOT FOUND", key); continue
    ii = hit["imageinfo"][0]; lic = ii["extmetadata"].get("LicenseShortName", {}).get("value", "?")
    url = ii.get("thumburl") or ii["url"]
    dst = f"images_period/p{n:02d}.jpg"
    req = urllib.request.Request(url, headers=UA)
    open(dst, "wb").write(urllib.request.urlopen(req, timeout=120).read())
    out[n] = dict(scene=n, path=dst, commons_title=hit["title"], license=lic, source=ii["descriptionurl"] if "descriptionurl" in ii else ii["url"])
    print(n, "ok", hit["title"][5:60], "|", lic, flush=True)
json.dump(out, open("build/period_assets.json", "w"), indent=1)
