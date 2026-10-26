#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B站视频下载小工具：yt-dlp 薄封装。

用法：
    python videofetch.py <B站链接...>            直接下载
    python videofetch.py                        交互模式，粘贴链接回车下载
可选参数：
    --browser edge|chrome|firefox   读取哪个浏览器的登录Cookie（默认 edge）
    --quality best|1080p|720p       画质上限（默认 best = 会员最高档）
    --sub                           同时下载字幕（含AI字幕，转srt）
    --danmaku                       同时下载弹幕（xml）
    --list-formats                  只列出可选画质，不下载
"""

import argparse
import email.utils
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloads"
COOKIES_FILE = PROJECT_DIR / "cookies.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def find_ffmpeg():
    """按优先级找 ffmpeg：随仓库附带的 → 旧机器固定路径 → 系统 PATH。"""
    for p in (PROJECT_DIR / "ffmpeg.exe", Path(r"D:\ffmpeg.exe")):
        if p.exists():
            return p
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


FFMPEG = find_ffmpeg()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def ensure_deps():
    """缺哪个依赖自动 pip 装哪个（装过就跳过；国内网络失败自动换清华镜像）。"""
    missing = []
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp")
    try:
        import qrcode  # noqa: F401
    except ImportError:
        missing.append("qrcode")
    if not missing:
        return True
    pkgs = " ".join(missing)
    print(f"首次运行，自动安装缺失的依赖: {pkgs} （只需一次，请稍候）...")
    attempts = [[], ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]]
    for extra in attempts:
        r = subprocess.run([sys.executable, "-m", "pip", "install", *extra, *missing])
        if r.returncode == 0:
            print("✔ 依赖安装完成")
            return True
    print("✘ 自动安装失败，请手动执行：")
    print(f"    {sys.executable} -m pip install {pkgs}")
    return False


def _http_get(url, cookie=None):
    headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.headers, resp.read().decode("utf-8", "replace")


def _parse_set_cookies(headers):
    """解析响应头里的 Set-Cookie，返回 [(名字, 值, 属性dict), ...]"""
    items = []
    for line in headers.get_all("Set-Cookie") or []:
        parts = line.split(";")
        if "=" not in parts[0]:
            continue
        name, _, value = parts[0].partition("=")
        attrs = {"domain": ".bilibili.com", "path": "/",
                 "expiry": str(int(time.time()) + 7776000)}  # 默认90天
        for p in parts[1:]:
            k, _, v = p.strip().partition("=")
            k = k.lower()
            if k == "expires":
                try:
                    attrs["expiry"] = str(int(
                        email.utils.parsedate_to_datetime(v).timestamp()))
                except Exception:
                    pass
            elif k == "max-age":
                try:
                    attrs["expiry"] = str(int(time.time()) + int(v))
                except Exception:
                    pass
            elif k == "domain" and v.strip():
                attrs["domain"] = v.strip()
            elif k == "path" and v.strip():
                attrs["path"] = v.strip()
        items.append((name.strip(), value.strip(), attrs))
    return items


def _write_png(path, matrix, scale=10):
    """把二维码矩阵写成 PNG（纯标准库，黑模块白底）。"""
    h, w = len(matrix), len(matrix[0])
    white, black = b"\xff\xff\xff", b"\x00\x00\x00"
    raw = bytearray()
    for row in matrix:
        pixels = b"".join((black if c else white) * scale for c in row)
        for _ in range(scale):
            raw += b"\x00" + pixels

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


def _cookie_header(cookies):
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def qr_login():
    """B站扫码登录：生成二维码 → 用户手机APP确认 → 写 cookies.txt。"""
    try:
        import qrcode
    except ImportError:
        print("✘ 缺少 qrcode 库，请先执行：")
        print(f"    {sys.executable} -m pip install qrcode")
        return False
    print("正在向B站申请登录二维码...")
    _, body = _http_get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
    data = json.loads(body)["data"]
    key = data["qrcode_key"]
    qr_png = PROJECT_DIR / "扫码登录.png"

    for attempt in range(3):  # 二维码过期自动重生成，最多3轮
        qr = qrcode.QRCode(border=4)  # 留白4模块，扫码规范要求
        qr.add_data(data["url"])
        qr.make(fit=True)
        _write_png(qr_png, qr.get_matrix(), scale=12)
        print()
        print("请用手机B站APP扫描二维码登录：")
        opened = False
        try:
            os.startfile(qr_png)
            opened = True
        except OSError:
            pass
        if opened:
            print("  · 二维码图片已在屏幕上弹出，用手机扫它（推荐）")
        else:
            print(f"  · 请手动打开这个图片再扫: {qr_png}")
        print("  · 手机B站APP → 右上角扫一扫 → 点【确认登录】")
        qr.print_ascii(invert=False)  # bat窗口是白底，正色才可扫
        ok, headers, last_json = False, None, None
        scanned = False
        for _ in range(90):  # 每个二维码最多等180秒
            time.sleep(2)
            try:
                headers, body = _http_get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
                    f"?qrcode_key={key}")
            except Exception as e:
                print(f"  网络波动（{e}），继续等待...")
                continue
            last_json = json.loads(body)
            state = last_json.get("data", {}).get("code", -1)
            if state == 86101:
                continue
            if state == 86090:
                if not scanned:
                    scanned = True
                    print("  已扫码，请在手机上点【确认登录】...")
                continue
            if state == 0:
                ok = True
                break
            if state == 86038:
                break  # 过期，重新生成
        if ok:
            break
        if attempt == 2:
            print("✘ 三次二维码都超时未登录，已退出。重新运行本程序即可再试。")
            return False
        print("  二维码已过期，自动重新生成...")
        _, body = _http_get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
        data = json.loads(body)["data"]
        key = data["qrcode_key"]

    # 提取Cookie：优先 Set-Cookie 响应头，兜底从 data.url 参数里拿
    cookies, items = {}, []
    for name, value, attrs in _parse_set_cookies(headers):
        cookies[name] = value
        items.append((name, value, attrs))
    if "SESSDATA" not in cookies and last_json:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(
            last_json.get("data", {}).get("url", "")).query)
        now = str(int(time.time()) + 7776000)
        for k in ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5"):
            if k in q:
                cookies[k] = q[k][0]
                items.append((k, q[k][0],
                              {"domain": ".bilibili.com", "path": "/", "expiry": now}))
    if "SESSDATA" not in cookies:
        print("✘ 登录成功但未取到 Cookie，请重试一次")
        return False

    # 访问主站补 buvid3 等设备Cookie，降低风控概率
    try:
        h2, _ = _http_get("https://www.bilibili.com/", cookie=_cookie_header(cookies))
        for name, value, attrs in _parse_set_cookies(h2):
            if name not in cookies:
                cookies[name] = value
                items.append((name, value, attrs))
    except Exception:
        pass

    lines = ["# Netscape HTTP Cookie File",
             f"# Generated by videofetch 扫码登录 at {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for name, value, attrs in items:
        domain = attrs["domain"]
        if not domain.startswith("."):
            domain = "." + domain  # Netscape格式要求：带点(匹配子域)须与TRUE标志成对
        lines.append("\t".join([domain, "TRUE", attrs["path"],
                                "TRUE", attrs["expiry"], name, value]))
    COOKIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✔ Cookie 已保存到 {COOKIES_FILE}")

    try:
        _, body = _http_get("https://api.bilibili.com/x/web-interface/nav",
                            cookie=_cookie_header(cookies))
        d = json.loads(body).get("data", {})
        if d.get("isLogin"):
            if d.get("vipStatus"):
                vip = {1: "大会员", 2: "年度大会员"}.get(d.get("vipType"), "大会员")
                print(f"✔ 登录身份：{d.get('uname')}（{vip}）—— 会员画质已解锁")
            else:
                print(f"✔ 登录身份：{d.get('uname')}（未开通大会员，最高1080P）")
    except Exception:
        pass
    print("现在双击 下载视频.bat 即可下载会员画质视频")
    try:
        qr_png.unlink()  # 登录完删掉二维码图片
    except OSError:
        pass
    return True


def yt_core_args(args, with_cookies=True):
    """yt-dlp 命令前缀：解释器 + 模块名 + Cookie 选项。"""
    core = [sys.executable, "-m", "yt_dlp"]
    if COOKIES_FILE.exists():
        core += ["--cookies", str(COOKIES_FILE)]
    elif with_cookies:
        core += ["--cookies-from-browser", args.browser]
    return core


def download_opts():
    """下载专用参数：ffmpeg 位置、命名、断点续传等。"""
    if FFMPEG is None:
        opts = []
        print("[提示] 没找到 ffmpeg，音视频无法合并。"
              "请把 ffmpeg.exe 放到本目录，或安装到系统 PATH")
    else:
        opts = ["--ffmpeg-location", str(FFMPEG)]
    opts += [
        "--windows-filenames",
        "--embed-metadata",
        "--download-archive", str(DOWNLOAD_DIR / "downloaded.txt"),
        "--no-overwrites",
        "--retries", "10",
    ]
    return opts


def run_flat_json(core, url):
    """flat 模式探测链接，返回 (元数据json或None, stderr文本)。"""
    cmd = core + ["--flat-playlist", "-J", url]
    try:
        raw = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=90)
    except subprocess.TimeoutExpired:
        return None, ""
    out = raw.stdout.strip()
    if raw.returncode != 0 or not out:
        return None, raw.stderr or ""
    try:
        return json.loads(out), raw.stderr or ""
    except json.JSONDecodeError:
        return None, raw.stderr or ""


def probe(url, args):
    """探测链接类型；Cookie 读不到时自动降级为游客模式。
    返回 (core参数, 描述文本, 是否多P/合集)。"""
    core = yt_core_args(args, with_cookies=True)
    info, err = run_flat_json(core, url)
    if info is None and COOKIES_FILE.exists():
        if err and "cookie" in err.lower():
            print("[提示] cookies.txt 读取失败（格式异常或已失效），先按游客身份下载")
            print("       修复办法：删除 cookies.txt 后重新运行 扫码登录.bat")
        core = yt_core_args(args, with_cookies=False)
        info, _ = run_flat_json(core, url)
        if info is not None:
            print("[提示] 本次按游客身份下载（最高480P）")
    elif info is None:
        core = yt_core_args(args, with_cookies=False)
        info, _ = run_flat_json(core, url)
        if info is not None:
            print(f"[提示] 未登录，本次按游客身份下载（最高480P）")
            print("       想要会员画质：先双击 扫码登录.bat 用手机B站APP扫码登录")
    if info is None:
        return core, None, False
    if info.get("_type") == "playlist":
        n = len(info.get("entries") or [])
        return core, f"《{info.get('title')}》 共 {n} 个视频", True
    return core, f"《{info.get('title')}》 单视频", False


def build_download_opts(args, is_playlist):
    opts = [
        "-S", "res,vcodec:h264,acodec:aac",
        "--merge-output-format", "mp4",
        "-P", str(DOWNLOAD_DIR),
    ]
    if args.quality == "1080p":
        opts += ["-f", "bv*[height<=1080]+ba/b[height<=1080]"]
    elif args.quality == "720p":
        opts += ["-f", "bv*[height<=720]+ba/b[height<=720]"]
    if is_playlist:
        opts += ["-o", "%(playlist_title)s/P%(playlist_index)03d - %(title)s.%(ext)s"]
    else:
        opts += ["-o", "%(title)s.%(ext)s"]
    if args.items:
        opts += ["--playlist-items", args.items]
    if args.sub:
        opts += ["--write-subs", "--write-auto-subs",
                 "--sub-langs", "ai-zh,zh-Hans,zh-CN",
                 "--convert-subs", "srt"]
    if args.danmaku:
        opts += ["--write-subs", "--sub-langs", "danmaku"]
    return opts


def download(url, args):
    print("\n" + "=" * 46)
    print("正在识别链接...")
    core, msg, is_playlist = probe(url, args)
    if msg:
        print(f"识别到：{msg}")
    else:
        print("（未能预识别链接类型，仍尝试直接下载）")
    cmd = core + download_opts() + build_download_opts(args, is_playlist)
    if args.list_formats:
        cmd += ["--list-formats", "--simulate"]
    cmd.append(url)
    code = subprocess.run(cmd).returncode
    if code == 0:
        print(f"✔ 完成，文件保存在 {DOWNLOAD_DIR}")
    else:
        print(f"✘ 下载失败（退出码 {code}）。常见原因：")
        print("  1. 链接不对或已失效")
        print("  2. 没有登录Cookie —— 按README用插件导出 cookies.txt 放到本目录")
        print("     （收藏夹/UP主批量链接没Cookie会被风控直接拒绝）")
        print("  3. 网络问题，重试一次")
    return code


def main():
    parser = argparse.ArgumentParser(description="B站视频下载小工具")
    parser.add_argument("urls", nargs="*", help="B站视频/合集/收藏夹链接")
    parser.add_argument("--browser", default="edge",
                        choices=["edge", "chrome", "firefox", "brave", "vivaldi", "opera"])
    parser.add_argument("--quality", default="best",
                        choices=["best", "1080p", "720p"])
    parser.add_argument("--sub", action="store_true", help="同时下载字幕")
    parser.add_argument("--danmaku", action="store_true", help="同时下载弹幕")
    parser.add_argument("--items", help="选集下载（整季/合集/收藏夹用），如 1-3 或 1,5")
    parser.add_argument("--list-formats", action="store_true", help="只列出可选画质")
    parser.add_argument("--login", action="store_true",
                        help="扫码登录B站，生成 cookies.txt（解锁会员画质）")
    args = parser.parse_args()

    if not ensure_deps():
        sys.exit(1)

    if args.login:
        sys.exit(0 if qr_login() else 1)

    urls = [u.strip().strip('"') for u in args.urls if u.strip()]
    if not urls:
        print("=" * 46)
        print(" B站视频下载工具 (yt-dlp)")
        print(" 粘贴B站链接后回车开始下载")
        print(" 可一次粘贴多个链接，用空格分隔")
        print(" 直接按回车退出")
        if not COOKIES_FILE.exists():
            print(" ── 尚未登录：先运行 扫码登录.bat 可解锁会员画质 ──")
        print("=" * 46)
        while True:
            try:
                line = input("\n粘贴链接 > ").strip().strip('"')
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            for u in line.split():
                download(u, args)
        return

    exit_code = 0
    for u in urls:
        if download(u, args) != 0:
            exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
