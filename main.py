import json
import os
import time
import threading
import requests
from flask import Flask, render_template_string

app = Flask(__name__)

# ===================== 配置 =====================
ARIA2_RPC = os.getenv("ARIA2_RPC", "http://127.0.0.1:6800/jsonrpc")
ARIA2_SECRET = os.getenv("ARIA2_SECRET", "fight1314")
SAVE_PATH = "/download"
JSON_DIR = "./json/"
os.makedirs(JSON_DIR, exist_ok=True)

running_fetch = False
running_download = False
log = ["系统已就绪，等待操作..."]
downloaded_fsids = set()

# 导出文件
VIDEO_EXPORT_FILE = "./video_fsid_list.txt"
RECORD_FILE = "./downloaded.txt"

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

# ===================== Aria2 工具 =====================
def aria2_get_active_gids():
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "aria2.tellActive",
            "id": 1,
            "params": [f"token:{ARIA2_SECRET}"]
        }
        resp = requests.post(ARIA2_RPC, json=payload, timeout=5)
        active = resp.json().get("result", [])
        return {item.get("gid") for item in active}
    except Exception as e:
        add_log(f"⚠️ 获取active任务失败: {e}")
        return set()

def aria2_clear_completed():
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "aria2.purgeDownloadResult",
            "id": 1,
            "params": [f"token:{ARIA2_SECRET}"]
        }
        requests.post(ARIA2_RPC, json=payload, timeout=3)
    except:
        pass

def aria2_add_task(uri, filename, fsid):
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "aria2.addUri",
            "id": 1,
            "params": [
                f"token:{ARIA2_SECRET}",
                [uri],
                {"dir": SAVE_PATH, "out": filename}
            ]
        }
        res = requests.post(ARIA2_RPC, json=payload, timeout=3)
        return res.json().get("result")
    except:
        return None

# ===================== 获取相册列表 =====================
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
        need_thumbnail = cfg.get("need_thumbnail", 1)
        need_filter_hidden = cfg.get("need_filter_hidden", 0)

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://photo.baidu.com/",
            "Cookie": cookie
        }

        cursor = None
        page = 1
        date_data = {}
        empty_retry = 0

        while True:
            url = (f"https://photo.baidu.com/youai/file/v1/list"
                   f"?clienttype={clienttype}&bdstoken={bdstoken}"
                   f"&need_thumbnail={need_thumbnail}"
                   f"&need_filter_hidden={need_filter_hidden}")
            if cursor:
                url += f"&cursor={cursor}"

            res = None
            ok = False
            for _ in range(2):
                try:
                    res = requests.get(url, headers=headers, timeout=15)
                    if res.status_code == 200:
                        ok = True
                        break
                except:
                    time.sleep(1)
            if not ok:
                add_log("❌ 请求失败，停止抓取")
                break

            data = res.json()
            lst = data.get("list", [])
            next_cursor = data.get("cursor")
            add_log(f" 第{page}页")

            if not lst:
                empty_retry += 1
                if empty_retry >= 2:
                    add_log("✅ 全部抓取完成")
                    break
                time.sleep(2)
                continue
            empty_retry = 0

            for item in lst:
                path = item.get("path", "")
                fname = path[12:] if len(path) > 12 else path
                fsid = str(item.get("fsid", ""))
                dt = item.get("extra_info", {}).get("date_time", "")
                date = dt[:10].replace(":", "-") if len(dt) >= 10 else "unknown"
                if date not in date_data:
                    date_data[date] = []
                date_data[date].append({"fsid": fsid, "filename": fname})

            if not next_cursor:
                add_log("✅ 无下一页")
                break
            cursor = next_cursor
            page += 1
            time.sleep(1)

        for d, items in date_data.items():
            p = os.path.join(JSON_DIR, f"{d}.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        add_log(f" 共抓取 {page-1} 页")
    except Exception as e:
        add_log(f"❌ 错误：{e}")
    running_fetch = False

# ===================== 只下载图片，视频导出fsid =====================
def start_download():
    global running_download
    if running_download:
        add_log("⚠️ 正在下载中")
        return
    running_download = True
    add_log("✅ 开始【只下载图片，视频导出FSID】")

    # 清空导出文件
    with open(VIDEO_EXPORT_FILE, "w", encoding="utf-8") as f:
        f.write("fsid | 文件名\n")
        f.write("-" * 50 + "\n")

    try:
        files = sorted([f for f in os.listdir(JSON_DIR) if f.endswith(".json")])
        if not files:
            add_log("❌ 无文件")
            running_download = False
            return

        with open("settings.json", encoding="utf-8") as f:
            cfg = json.load(f)
        cookie = cfg["Cookie"]
        bdstoken = cfg["bdstoken"]
        clienttype = cfg["clienttype"]
        headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}

        aria2_clear_completed()

        for jf in files:
            if not running_download: break
            with open(os.path.join(JSON_DIR, jf), "r", encoding="utf-8") as f:
                items = json.load(f)

            for item in items:
                if not running_download: break
                fsid = item.get("fsid", "")
                name = item.get("filename", "")
                if not fsid or fsid in downloaded_fsids:
                    continue

                # ===================== 图片/视频判断 =====================
                is_image = name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))
                is_video = name.lower().endswith(('.mp4', '.mov', '.avi', '.flv', '.mkv', '.wmv', '.rmvb'))

                if is_video:
                    # 视频：导出fsid，跳过下载
                    add_log(f"️ 视频，已导出FSID: {name}")
                    with open(VIDEO_EXPORT_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{fsid} | {name}\n")
                    continue

                if not is_image:
                    add_log(f" 非图片非视频，跳过: {name}")
                    continue

                # ===================== 下载图片 =====================
                add_log(f"️ 处理图片: {name}")
                dlink = None
                for _ in range(2):
                    try:
                        api = f"https://photo.baidu.com/youai/file/v2/download?clienttype={clienttype}&bdstoken={bdstoken}&fsid={fsid}"
                        r = requests.get(api, headers=headers, timeout=8)
                        dlink = r.json().get("dlink")
                        if dlink:
                            break
                    except:
                        time.sleep(1)

                if dlink:
                    gid = aria2_add_task(dlink, name, fsid)
                    if gid:
                        while True:
                            active = aria2_get_active_gids()
                            if gid not in active:
                                break
                            time.sleep(2)
                        add_log(f"✅ 图片下载完成: {name}")
                        with open(RECORD_FILE, "a") as f:
                            f.write(f"{fsid}\n")
                        downloaded_fsids.add(fsid)
                        aria2_clear_completed()
                        time.sleep(1)
                        continue

                add_log(f"❌ 图片下载失败: {name}")
                time.sleep(1)

        add_log(" 所有任务处理完成！")
        add_log(f" 视频FSID已导出到: {VIDEO_EXPORT_FILE}")
    except Exception as e:
        add_log(f"❌ 异常：{e}")
    running_download = False

# ===================== Web面板 =====================
@app.route("/")
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>一刻相册 - 图片专用版</title>
    <style>
        body {background:#111;color:#fff;padding:20px;font-family:Arial}
        #log {background:#000;color:#0f0;height:420px;overflow:auto;padding:10px;margin:10px 0}
        button {padding:14px 30px;margin:10px;font-size:16px;background:#06c;color:#fff;border:none;border-radius:8px;cursor:pointer}
    </style>
</head>
<body>
    <h2> 一刻相册（只下载图片，视频导出FSID）</h2>
    <button onclick="fetchList()">获取相册列表</button>
    <button onclick="startDownload()">开始下载</button>
    <div id="log">日志加载中...</div>
    <script>
        function fetchList(){fetch("/fetch")}
        function startDownload(){fetch("/download")}
        function updateLog(){
            fetch("/log").then(r=>r.text()).then(t=>{
                document.getElementById("log").innerText = t;
                document.getElementById("log").scrollTop = 999999;
            })
        }
        updateLog();
        setInterval(updateLog,1000);
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
    app.run(host="0.0.0.0", port=7892, debug=False, threaded=True)
