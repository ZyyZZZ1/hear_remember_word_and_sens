"""Debug lecture page structure"""
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
            return d.get("result", {})

def js(code):
    r = send("Runtime.evaluate", {"expression": code, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("value")

# Navigate to lesson 13 (grammar - lecture type)
print("Navigating to lesson 13 (介词a的用法 - grammar)...")
send("Page.navigate", {"url": "https://sharplingo.cn/courses/show-lecture/663f25e1b826335d890c83e9/66935016da2f0300157c811d/66935016da2f0300157c811b"})
time.sleep(4)

print("\n=== Full body text (first 2000 chars) ===")
body = js("document.body.innerText.substring(0, 2000)")
print(body)

print("\n\n=== Now navigate to lesson 3 (不定冠词和定冠词 - grammar) ===")
send("Page.navigate", {"url": "https://sharplingo.cn/courses/show-lecture/663f25e1b826335d890c83e9/663f269fb826335d890c8467/663f269fb826335d890c8465"})
time.sleep(4)
body2 = js("document.body.innerText.substring(0, 2000)")
print(body2)

ws.close()
