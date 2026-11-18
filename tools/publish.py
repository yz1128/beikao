"""
一条命令上线：重建 index.html → 上传 GitHub → 等 Pages 构建 → 打印链接。

用 curl 走系统代理发请求：本机 urllib 经代理会 SSL EOF，curl 稳定。
前置：~/.git-credentials 里有 github.com 的 PAT（见 skill static-site-publishing）。
用法：python tools/publish.py
"""
import base64
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "yz1128/beikao"
BRANCH = "main"
PROXY = None


def pick_proxy():
    """代理开着就走代理，关着就直连——本机 FlClash 时常关闭，不能写死。"""
    for candidate in ("http://127.0.0.1:7890",):
        probe = subprocess.run(
            ["curl", "-s", "-m", "4", "-x", candidate, "-o", os.devnull,
             "-w", "%{http_code}", "https://api.github.com/"],
            capture_output=True, text=True,
        )
        if probe.stdout.strip().startswith(("2", "3")):
            print(f"代理可用：{candidate}")
            return candidate
    print("代理不可用，直连 GitHub")
    return None


def token():
    """从 ~/.git-credentials 取 github.com 的 PAT。"""
    path = os.path.expanduser("~/.git-credentials")
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line.startswith("https://") or "github.com" not in line:
            continue
        cred = line[len("https://"):].split("@")[0]
        if ":" in cred:
            return cred.split(":", 1)[1]
    raise SystemExit("在 ~/.git-credentials 里找不到 github.com 的 token")


TOK = token()
PROXY = pick_proxy()
BODY_FILE = os.path.join(ROOT, ".publish_body.json")


def api(url: str, method: str = "GET", body: dict | None = None, tries: int = 3) -> dict:
    """打 GitHub API。返回解析后的 dict；失败返回 {'error': str}。"""
    cmd = ["curl", "-s", "-X", method, "-m", "120"]
    if PROXY:
        cmd += ["-x", PROXY]
    cmd += ["-H", f"Authorization: token {TOK}",
           "-H", "Accept: application/vnd.github+json",
           "-H", "Content-Type: application/json"]
    if body is not None:
        with open(BODY_FILE, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        cmd += ["-d", "@" + BODY_FILE]
    cmd.append(url)
    raw = ""
    for _ in range(tries):
        raw = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.strip()
        if raw[:1] in "{[":
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        time.sleep(2)
    return {"error": raw[:160]}


def upload(path, local, message):
    """新建或覆盖一个文件。逐个文件直接查 sha，避免用 tree 缓存的旧结果。"""
    info: dict = api(f"https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}")
    sha = info.get("sha") if isinstance(info, dict) and "sha" in info else None
    body = {"message": message,
            "content": base64.b64encode(open(local, "rb").read()).decode(),
            "branch": BRANCH}
    if sha:
        body["sha"] = sha
    res: dict = api(f"https://api.github.com/repos/{REPO}/contents/{path}", "PUT", body)
    ok = res.get("content", {}).get("path") == path
    print(f"  {'OK' if ok else 'FAIL'} {path}" + ("" if ok else f"  {res}"))
    return ok


def main():
    # 1. 重建
    print("重建 index.html ...")
    build = os.path.join(ROOT, "tools", "build.py")
    if subprocess.call([sys.executable, build], cwd=ROOT) != 0:
        return 1

    # 2. 上传（三页共用一份源码，一起发）
    print("上传 ...")
    for name in ("index.html", "zhongte.html", "ziran.html"):
        if not upload(name, os.path.join(ROOT, name), "更新题库"):
            return 1

    # 3. 等构建
    print("等待 Pages 构建 ...")
    for _ in range(20):
        st: dict = api(f"https://api.github.com/repos/{REPO}/pages/builds/latest")
        status = st.get("status")
        if status not in ("building", "queued", None):
            print(f"  {status} {st.get('error', {}).get('message') or ''}".rstrip())
            break
        time.sleep(8)

    if os.path.exists(BODY_FILE):
        os.remove(BODY_FILE)
    print(f"\n链接： https://yz1128.github.io/{REPO.split('/')[1]}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
