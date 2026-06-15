import json, urllib.request, websocket, time, re

r = urllib.request.urlopen("http://127.0.0.1:9222/json")
pages = json.loads(r.read())
ws_url = None
for p in pages:
    u = p.get("url","")
    if "sharplingo.cn" in u and "classroom" not in u and "study" not in u:
        ws_url = p["webSocketDebuggerUrl"]
        print(f"Using: {u[:100]}")
        break
if not ws_url:
    for p in pages:
        if "sharplingo.cn" in p.get("url",""):
            ws_url = p["webSocketDebuggerUrl"]
            break

ws = websocket.create_connection(ws_url, timeout=15)
mid = [0]
def send(m, p=None):
    mid[0]+=1
    ws.send(json.dumps({"id":mid[0],"method":m,"params":p or {}}))
    while True:
        d = json.loads(ws.recv())
        if d.get("id") == mid[0]:
            return d.get("result",{})
def js(c):
    return send("Runtime.evaluate",{"expression":c,"returnByValue":True,"awaitPromise":True}).get("result",{}).get("value")

# Navigate to article
url = "https://sharplingo.cn/courses/show-article/663f25e1b826335d890c83e9/664809d1804db40015839c4a/664809d1804db40015839c47"
print(f"Nav: {url}")
send("Page.navigate",{"url":url})
time.sleep(6)

print(f"Actual: {js('window.location.href')}")
print(f"Title: {js('document.title')}")

body = js("document.body.innerText")
print(f"Body len: {len(body)}")

# Search for lesson number
for pattern in [r'模块\d+\s*[-–—]\s*第\s*(\d+)\s*讲', r'第\s*(\d+)\s*讲']:
    m = re.search(pattern, body)
    if m:
        print(f"MATCH [{pattern}]: lesson {m.group(1)}")
        break
else:
    # Show relevant lines
    for line in body.split("\n"):
        s = line.strip()
        if "模块" in s or "讲" in s or "第" in s:
            print(f"LINE: [{s[:120]}]")

print("\n--- First 1500 chars ---")
print(body[:1500])
ws.close()
