"""Quick test: find lesson URLs and page structure"""
import json, urllib.request, websocket, time

r = urllib.request.urlopen("http://127.0.0.1:9222/json")
pages = json.loads(r.read())
ws_url = None
for p in pages:
    if "sharplingo.cn" in p.get("url", ""):
        ws_url = p["webSocketDebuggerUrl"]
        break

ws = websocket.create_connection(ws_url, timeout=15)
msg_id = 0

def send(method, params=None):
    global msg_id
    msg_id += 1
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        d = json.loads(ws.recv())
        if d.get("id") == msg_id:
            return d.get("result", {})

def js(code):
    r = send("Runtime.evaluate", {"expression": code, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("value")

# Navigate to module 1 first
print("=== Navigating to module 1 ===")
send("Page.navigate", {"url": "https://sharplingo.cn/courses/60182ef4343d07c8ad9a2e73/module/663f25e1b826335d890c83e9/show"})
time.sleep(3)

# Get all links
links = js("""
(function() {
    const links = [];
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.href;
        const text = (a.textContent || '').trim().replace(/\\s+/g, ' ');
        if (text && text.length > 1) {
            links.push({url: href, title: text});
        }
    });
    return JSON.stringify(links);
})()
""")
all_links = json.loads(links)

# Filter
skip_titles = ["全部习题", "进入教室", "返回", "字母表"]
content_links = [l for l in all_links if l["title"] not in skip_titles and "德汉词典" not in l["title"]]

print(f"\nFound {len(content_links)} content links:")
for i, l in enumerate(content_links):
    print(f"  {i+1:02d}. [{l['title'][:60]}]")

# Try navigating to lesson 14 (La casa de Juan)
print("\n=== Testing lesson 14 (La casa de Juan) ===")
for l in content_links:
    if "La casa de Juan" in l["title"]:
        print(f"URL: {l['url']}")
        send("Page.navigate", {"url": l["url"]})
        time.sleep(3)
        print(f"Current URL: {js('window.location.href')}")
        print(f"Title: {js('document.title')}")
        body = js("document.body.innerText.substring(0, 800)")
        print(f"Body preview:\n{body}")
        break

ws.close()
print("\nDone.")
