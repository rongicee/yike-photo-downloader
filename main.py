import json
import os
import time
import threading
import requests
from flask import Flask, render_template_string

app = Flask(__name__)

JSON_DIR = "./json/"
VIDEO_EXPORT_FILE = "./video_fsid_list.txt"
RECORD_FILE = "./downloaded.txt"
os.makedirs(JSON_DIR, exist_ok=True)

running_fetch = False
running_download = False
log = ["系统已就绪，等待操作..."]  # 初始化日志，避免空白卡住
downloaded_fsids = set()

if os.path.exists(RECORD_FILE):
    with open(RECORD_FILE, "r", encoding="utf-8") as f:
        downloaded_fsids = {line.strip() for line in f if line.strip()}

def add_log(msg):
    t = time.strftime("%H:%M:%S")
    line = f"[{t}] {msg}"
    log.append(line)
    print(line)
    if len(log) > 200:
        log.pop(0)

# ================================= Aria2 工具
def aria2_add_batch(uris, dir, filenames, fsids, cfg):
    try:
        rpc_url = cfg["aria2"]["rpc_url"]
        secret = cfg["aria2"]["secret"]
        gids = []
        for uri, fn, fsid in zip(uris, filenames, fsids):
            payload = {
                "jsonrpc": "2.0",
                "method": "aria2.addUri",
                "id": 1,
                "params": [f"token:{secret}", [uri], {"dir": dir, "out": fn}]
            }
            r = requests.post(rpc_url, json=payload, timeout=3)
            gid = r.json().get("result")
            if gid:
                gids.append(gid)
        return gids
    except Exception as e:
        add_log(f"⚠️ 添加Aria2任务失败: {e}")
        return []

def aria2_wait_batch(gids, cfg):
    try:
        rpc_url = cfg["aria2"]["rpc_url"]
        secret = cfg["aria2"]["secret"]
        while True:
            active = []
            for gid in gids:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "aria2.tellStatus",
                    "id": 1,
                    "params": [f"token:{secret}", gid]
                }
                r = requests.post(rpc_url, json=payload, timeout=3)
                st = r.json().get("result", {}).get("status")
                if st in ["active", "waiting", "paused"]:
                    active.append(gid)
            if not active:
                break
            time.sleep(2)
        return True
    except Exception as e:
        add_log(f"⚠️ 等待Aria2任务失败: {e}")
        return False

# ================================= 获取列表
def fetch_photo_list():
    global running_fetch
    if running_fetch:
        add_log("⚠️ 正在获取列表，请勿重复点击")
        return
    running_fetch = True
    add_log("✅ 开始获取相册列表")
    try:
        with open("settings.json", encoding="utf-8") as f:
            cfg = json.load(f)
        cookie = cfg["Cookie"]
        bdstoken = cfg["bdstoken"]
        clienttype = cfg.get("clienttype", 70)
        headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0", "Referer": "https://photo.baidu.com/"}
        cursor = None
        page = 1
        data_all = {}
        while True:
            url = f"https://photo.baidu.com/youai/file/v1/list?clienttype={clienttype}&bdstoken={bdstoken}"
            if cursor:
                url += f"&cursor={cursor}"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                add_log(f"❌ 获取列表失败，状态码：{res.status_code}")
                break
            j = res.json()
            lst = j.get("list", [])
            add_log(f"📄 第{page}页")
            for item in lst:
                path = item.get("path", "")
                name = path[12:] if len(path) > 12 else path
                fsid = str(item.get("fsid", ""))
                dt = item.get("extra_info", {}).get("date_time", "")[:10]
                if not dt:
                    dt = "unknown"
                if dt not in data_all:
                    data_all[dt] = []
                data_all[dt].append({"fsid": fsid, "filename": name})
            cursor = j.get("cursor")
            if not cursor:
                add_log("✅ 列表抓取完成")
                break
            page += 1
            time.sleep(1)
        for d, items in data_all.items():
            with open(os.path.join(JSON_DIR, f"{d}.json"), "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        add_log(f"🎉 共抓取 {page-1} 页数据")
    except Exception as e:
        add_log(f"❌ 抓取异常：{e}")
    running_fetch = False

# ================================= 下载：批量4张，只下图片，视频导出
def start_download():
    global running_download
    if running_download:
        add_log("⚠️ 已在运行，请勿重复点击")
        return
    running_download = True
    add_log("✅ 开始批量下载（每批4张图片）")
    try:
        with open("settings.json", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        add_log(f"❌ 读取 settings.json 失败: {e}")
        running_download = False
        return

    BATCH = cfg["download"]["batch_size"]
    SAVE = cfg["download"]["save_path"]
    cookie = cfg["Cookie"]
    bdstoken = cfg["bdstoken"]
    ct = cfg["clienttype"]
    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}

    with open(VIDEO_EXPORT_FILE, "w", encoding="utf-8") as f:
        f.write("fsid | filename\n")
        f.write("-" * 50 + "\n")

    tasks = []
    files = sorted([f for f in os.listdir(JSON_DIR) if f.endswith(".json")])
    for fn in files:
        with open(os.path.join(JSON_DIR, fn), encoding="utf-8") as f:
            items = json.load(f)
        for it in items:
            fsid = it.get("fsid", "")
            name = it.get("filename", "")
            if not fsid or fsid in downloaded_fsids:
                continue
            lower = name.lower()
            # 视频文件，导出fsid
            if lower.endswith(('.mp4','.mov','.avi','.mkv','.flv','.wmv','.rmvb')):
                add_log(f"📽️ 视频文件，已导出：{name}")
                with open(VIDEO_EXPORT_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{fsid} | {name}\n")
                continue
            # 非图片非视频文件，跳过
            if not lower.endswith(('.jpg','.jpeg','.png','.gif','.webp','.bmp')):
                add_log(f"📄 非图片文件，跳过：{name}")
                continue
            tasks.append((fsid, name))

    add_log(f"📦 待下载图片总数：{len(tasks)} 个")
    for i in range(0, len(tasks), BATCH):
        batch = tasks[i:i+BATCH]
        uris = []
        fns = []
        fids = []
        add_log(f"\n📌 开始第 {i//BATCH +1} 批（共 {len(batch)} 个文件）")
        for fsid, name in batch:
            try:
                url = f"https://photo.baidu.com/youai/file/v2/download?clienttype={ct}&bdstoken={bdstoken}&fsid={fsid}"
                dlink = requests.get(url, headers=headers, timeout=8).json().get("dlink")
                if dlink:
                    uris.append(dlink)
                    fns.append(name)
                    fids.append(fsid)
                    add_log(f"✅ 获取直链成功：{name}")
            except Exception as e:
                add_log(f"❌ 获取直链失败：{name}")
        if uris:
            gids = aria2_add_batch(uris, SAVE, fns, fids, cfg)
            if gids:
                add_log(f"⏳ 等待第 {i//BATCH +1} 批下载完成...")
                aria2_wait_batch(gids, cfg)
                for fsid in fids:
                    with open(RECORD_FILE, "a") as f:
                        f.write(f"{fsid}\n")
                    downloaded_fsids.add(fsid)
                add_log(f"✅ 第 {i//BATCH +1} 批下载完成")
        time.sleep(1)
    add_log("🎉 所有图片下载任务完成！")
    add_log(f"📁 视频FSID已导出到：{VIDEO_EXPORT_FILE}")
    running_download = False

# ================================= WEB（修复日志加载问题）
@app.route("/")
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>一刻相册 - 批量4张</title>
    <style>
        body {
            background: #111;
            color: #fff;
            padding: 20px;
            font-family: Arial, sans-serif;
        }
        #log {
            background: #000;
            color: #0f0;
            height: 420px;
            overflow: auto;
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
            white-space: pre-wrap;
        }
        button {
            padding: 14px 30px;
            margin: 10px;
            font-size: 16px;
            background: #06c;
            color: #fff;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <h2>📸 一刻相册 - 批量4张</h2>
    <button onclick="fetchList()">获取列表</button>
    <button onclick="startDownload()">开始下载</button>
    <div id="log">日志加载中...</div>

    <script>
        function fetchList() {
            fetch("/fetch");
        }
        function startDownload() {
            fetch("/download");
        }

        function updateLog() {
            fetch("/log")
                .then(r => r.text())
                .then(t => {
                    document.getElementById("log").innerText = t;
                    document.getElementById("log").scrollTop = document.getElementById("log").scrollHeight;
                })
                .catch(err => {
                    document.getElementById("log").innerText = "日志加载失败：" + err;
                });
        }

        // 关键修复：页面加载完成后立即执行一次日志更新
        updateLog();
        setInterval(updateLog, 1000);
    </script>
</body>
</html>
''')

@app.route("/log")
def showlog():
    return "\n".join(log)

@app.route("/fetch")
def rf():
    threading.Thread(target=fetch_photo_list, daemon=True).start()
    return "ok"

@app.route("/download")
def rd():
    threading.Thread(target=start_download, daemon=True).start()
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7989, debug=False)
