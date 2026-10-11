"""ComfyUI Cloud LTX 2.3 i2v helper (workflow copied from docs playbook; key parsed, never printed)."""
import json, re, time, sys, urllib.request, urllib.parse, uuid, mimetypes, os
DOC = '/home/roman-antony/local-gen-documentary/docs/CLAUDE_SESSION_STOCK_DOCUMENTARY_PROMPTS.md'
T = open(DOC).read()
KEY = re.search(r'comfyUI_API_KEY\W+([A-Za-z0-9_\-]+)', T).group(1)
BASE = 'https://cloud.comfy.org'

def _wf():
    i = T.index("--data '{", T.index('cloud.comfy.org')) + 8
    d = T[i:]; depth = 0
    for k, c in enumerate(d):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: break
    return json.loads(d[:k + 1])

def req(path, data=None, headers=None, method=None):
    h = {'X-API-Key': KEY}; h.update(headers or {})
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    return urllib.request.urlopen(r, timeout=120)

def upload(path):
    b = uuid.uuid4().hex; name = os.path.basename(path)
    body = (f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: {mimetypes.guess_type(name)[0] or "image/png"}\r\n\r\n').encode() + open(path, 'rb').read() + (f'\r\n--{b}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{b}--\r\n').encode()
    r = req('/api/upload/image', body, {'Content-Type': f'multipart/form-data; boundary={b}'})
    return json.loads(r.read())['name']

def submit(image, prompt, w=1280, h=720, secs=5, fps=25, seed=None, tag='ltx'):
    j = _wf(); P = j['prompt']
    P['269']['inputs']['image'] = upload(image)
    P['75']['inputs']['filename_prefix'] = f'video/{tag}'
    P['320:319']['inputs']['value'] = prompt
    P['320:312']['inputs']['value'] = w
    P['320:299']['inputs']['value'] = h
    P['320:300']['inputs']['value'] = fps
    P['320:301']['inputs']['value'] = secs
    if seed is not None: P['320:277']['inputs']['noise_seed'] = seed
    j['extra_data'] = {'api_key_comfy_org': KEY}
    r = req('/api/prompt', json.dumps(j).encode(), {'Content-Type': 'application/json'})
    return json.loads(r.read())['prompt_id']

def wait(pid, every=10, timeout=2400):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = json.loads(req(f'/api/job/{pid}/status').read())
        except Exception as e:
            s = {'status': f'err {e}'}
        st = s.get('status')
        if st in ('completed', 'success'): return s
        if st in ('failed', 'error', 'cancelled'): raise RuntimeError(s)
        time.sleep(every)
    raise TimeoutError(pid)

def fetch(pid, out):
    h = json.loads(req(f'/api/history_v2/{pid}').read())
    outs = h.get('outputs') or h.get(pid, {}).get('outputs', {})
    for n, o in outs.items():
        for k in ('images', 'videos', 'gifs'):
            for f in o.get(k, []):
                q = urllib.parse.urlencode({'filename': f['filename'], 'subfolder': f.get('subfolder', ''), 'type': f.get('type', 'output')})
                data = req('/api/view?' + q).read()
                if f['filename'].endswith(('.mp4', '.webm', '.mov')):
                    open(out, 'wb').write(data); return out
    raise RuntimeError(('no video', json.dumps(h)[:500]))
