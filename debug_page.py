"""Debug: analyze page HTML structure to find content container"""
import json, urllib.request, websocket, time

r = urllib.request.urlopen("http://127.0.0.1:9222/json")
pages = json.loads(r.read())
ws_url = None
for p in pages:
    if "sharplingo.cn" in p.get("url", ""):
        ws_url = p["webSocketDebuggerUrl"]
        break

ws = websocket.create_connection(ws_url, timeout=15)
msg_id = [0]

def send(method, params=None):
    msg_id[0] += 1
    ws.send(json.dumps({"id": msg_id[0], "method": method, "params": params or {}}))
    while True:
        d = json.loads(ws.recv())
        if d.get("id") == msg_id[0]:
            if "error" in d:
                print(f"  CDP err: {d['error']}")
            return d.get("result", {})

def js(code):
    r = send("Runtime.evaluate", {"expression": code, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("value")

# Navigate to lesson 14
print("Navigating to La casa de Juan...")
send("Page.navigate", {"url": "https://sharplingo.cn/courses/show-article/663f25e1b826335d890c83e9/664809d1804db40015839c4a/664809d1804db40015839c47"})
time.sleep(4)

print("\n=== HTML structure (main containers) ===")
html_info = js("""
(function() {
    const info = {};
    // Find all major containers
    const containers = document.querySelectorAll('div[class], section[class], article[class], main[class]');
    const candidates = [];
    containers.forEach(el => {
        const cls = el.className || '';
        const tag = el.tagName;
        const textLen = (el.textContent || '').trim().length;
        if (textLen > 100 && textLen < 10000 && !candidates.some(c => c.cls === cls && c.tag === tag)) {
            candidates.push({tag, cls: cls.substring(0, 80), textLen, textPreview: el.textContent.trim().substring(0, 120)});
        }
    });
    // Sort by text length descending
    candidates.sort((a,b) => b.textLen - a.textLen);
    return JSON.stringify(candidates.slice(0, 15));
})()
""")
print(html_info[:2000])

print("\n=== Full body text (first 1500 chars) ===")
body = js("document.body.innerText.substring(0, 1500)")
print(body)

ws.close()
