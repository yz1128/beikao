"""
一条命令上线：重建 index.html → 上传 GitHub → 等 Pages 构建 → 打印链接。

前置：~/.git-credentials 里有 github.com 的 PAT（skill: static-site-publishing）。
用法：python tools/publish.py
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "yz1128/beikao"
BRANCH = "main"
PROXY = "http://127.0.0.1:7890"


def token():
    """从 ~/.git-credentials 取 github.com 的 PAT。"""
    path = os.path.expanduser("~/.git-credentials")
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if "github.com" not in line or not line.startswith("https://"):
            continue
        cred = line[len("https://"):].split("@")[0]   # user:token
        if ":" in cred:
            return cred.split(":", 1)[1]
    raise SystemExit("在 ~/.git-credentials 里找不到 github.com 的 token")


def api(url, method="GET", body=None, tok=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {tok}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    )
    with opener.open(req, timeout=90) as r:
        return json.loads(r.read().decode())


def main():
    tok = token()

    # 1. 重建
    build = os.path.join(ROOT, "tools", "build.py")
    if subprocess.call([sys.executable, build]) != 0:
        return 1

    # 2. 上传（Contents API，避开 git push 卡代理的老问题）
    local = os.path.join(ROOT, "index.html")
    content = base64.b64encode(open(local, "rb").read()).decode()
    base = f"https://api.github.com/repos/{REPO}/contents/index.html"
    sha = None
    try:
        sha = api(base + f"?ref={BRANCH}", tok=tok).get("sha")
    except Exception:
        pass
    body = {"message": "更新题库", "content": content, "branch": BRANCH}
    if sha:
        body["sha"] = sha
    res = api(base, method="PUT", body=body, tok=tok)
    if "content" not in res:
        print("上传失败：", res)
        return 1
    print(f"已上传 index.html（{os.path.getsize(local) / 1024:.0f} KB）")

    # 3. 等构建
    for _ in range(20):
        st = api(f"https://api.github.com/repos/{REPO}/pages/builds/latest", tok=tok)
        if st.get("status") not in ("building", "queued"):
            print("Pages 构建：", st.get("status"), st.get("error", {}).get("message") or "")
            break
        time.sleep(8)

    print("链接： https://yz1128.github.io/beikao/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
