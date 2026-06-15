#!/usr/bin/env python
"""
极简版：扒取 sharplingo.cn 课程页面全部文本，保存到 原生教材/。
不做内容过滤，后续由 agent 按 教材提取规范.md 处理。
"""
import json, os, re, sys, time, urllib.request, urllib.error, websocket

CHROME_HTTP = "http://127.0.0.1:9222"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "原生教材")

# 用户已手动扒好的
EXISTING = {
    # 用户手动扒的
    "01-04","01-05","01-06","01-07","01-08","01-09","01-10","01-11","01-12","01-13","01-14",
    # 模块1 已扒（语法课）
    "01-01","01-02","01-03","01-16","01-17","01-18","01-21","01-22","01-23","01-24","01-25","01-26",
    # 模块2 已扒（语法课）
    "02-01","02-02","02-03","02-04","02-07","02-08","02-11","02-12","02-13","02-14",
    "02-17","02-18","02-19","02-20","02-23","02-24","02-27","02-28","02-29","02-30","02-33","02-34","02-35",
}

MODULES = {
    "01": "https://sharplingo.cn/courses/60182ef4343d07c8ad9a2e73/module/663f25e1b826335d890c83e9/show",
    "02": "https://sharplingo.cn/courses/60182ef4343d07c8ad9a2e73/module/66cd90ee8a23e70015fe9584/show",
}

# 这些不是课程内容，跳过
SKIP = {"SHARP LINGO","进入教室","返回","播放器","外语广播","笔记","收藏夹",
        "学习记录","我的账户","设置","退出登录","评论区","习题列表","全部习题",
        "注册","从OSS复制数据","Arty老师","Katharina老师","查看更多",
        "服务简介","常见问题","服务条款","隐私政策","Cookie政策",
        "Sign up with Facebook","Sign up with Google","Sign up with Wechat",
        "Log in with Facebook","Log in with Google","忘记了您的密码？","需要确认邮件地址？"}
SKIP_CONTAINS = ["词典","搜笔记","搜语法","网安备","ICP备","Sign up","Log in"]


def connect():
    with urllib.request.urlopen(f"{CHROME_HTTP}/json") as resp:
        pages = json.loads(resp.read().decode())
    for p in pages:
        if "sharplingo.cn" in p.get("url",""):
            return p["webSocketDebuggerUrl"]
    for p in pages:
        if p.get("type")=="page":
            return p["webSocketDebuggerUrl"]
    sys.exit("No page")

class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0
    def send(self, m, p=None):
        self._id+=1
        self.ws.send(json.dumps({"id":self._id,"method":m,"params":p or {}}))
        while True:
            d=json.loads(self.ws.recv())
            if d.get("id")==self._id:
                return d.get("result",{})
    def js(self, c):
        r=self.send("Runtime.evaluate",{"expression":c,"returnByValue":True,"awaitPromise":True})
        return r.get("result",{}).get("value")
    def nav(self, u):
        self.send("Page.navigate",{"url":u})
        time.sleep(5)  # article 页面加载较慢，多等1秒
    def close(self):
        try: self.ws.close()
        except: pass


def get_lesson_links(cdp, module_url):
    """从模块页面提取课程链接"""
    cdp.nav(module_url)
    links = json.loads(cdp.js("""
    (function(){
        var r=[];
        document.querySelectorAll('a[href]').forEach(function(a){
            r.push({url:a.href,title:(a.textContent||'').trim().replace(/\\s+/g,' ')});
        });
        return JSON.stringify(r);
    })()
    """))
    # 过滤
    out=[]
    seen=set()
    for l in links:
        t=l["title"]; u=l["url"]
        if not t or len(t)<2: continue
        if t in SKIP: continue
        if any(k in t for k in SKIP_CONTAINS): continue
        if u in seen: continue
        seen.add(u)
        out.append(l)
    return out


def dump_page(cdp):
    """直接把整个 body 文本扒下来"""
    return cdp.js("document.body.innerText")


def get_num(cdp):
    """从页面提取课程号（多处查找）"""
    # 1. 查找整个 body 中的 "模块XX - 第XX讲"
    t = cdp.js("document.body.innerText")
    m = re.search(r'模块\d+\s*[-–—]\s*第\s*(\d+)\s*讲', t)
    if m: return int(m.group(1))
    # 2. 查找 "第XX讲"
    m = re.search(r'第\s*(\d+)\s*讲', t)
    if m: return int(m.group(1))
    # 3. 查页面 title
    title = cdp.js("document.title")
    m = re.search(r'第\s*(\d+)\s*讲', title)
    if m: return int(m.group(1))
    return None


def main():
    print("Sharplingo Scraper (dump mode)\n")
    ws = connect()
    cdp = CDP(ws)
    print(f"Connected. Current: {cdp.js('window.location.href')[:100]}")

    for mn, mu in MODULES.items():
        print(f"\n{'='*60}\nModule {mn}\n{'='*60}")
        lessons = get_lesson_links(cdp, mu)
        print(f"Found {len(lessons)} links")

        for i, l in enumerate(lessons):
            t = l['title'][:60]
            try:
                cdp.nav(l['url'])
                num = get_num(cdp)
                if num is None:
                    print(f"  [{i+1}] SKIP (no lesson number): {t}")
                    continue
                fn = f"{mn}-{num:02d}"
                if fn in EXISTING:
                    print(f"  [{i+1}] SKIP (exists): {fn}.txt")
                    continue

                raw = dump_page(cdp)
                path = os.path.join(OUTPUT_DIR, fn+".txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(raw)
                lines = len(raw.split("\n"))
                print(f"  [{i+1}] OK: {fn}.txt ({lines} lines) - {t}")
            except Exception as e:
                print(f"  [{i+1}] ERR: {t} - {e}")
                try: cdp.close()
                except: pass
                cdp.__init__(connect())

    cdp.close()
    print(f"\nDone! -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
