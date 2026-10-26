# videofetch — B站视频下载小工具

用 [yt-dlp](https://github.com/yt-dlp/yt-dlp) + ffmpeg 把B站视频下载到本地，支持会员最高画质（1080P高码率 / 4K / HDR）。仅支持 Windows。

## 安装依赖（在其他电脑上使用）

1. 安装 [Python 3.8+](https://www.python.org/downloads/)（安装时勾选 **Add to PATH**）；
2. 依赖（yt-dlp、qrcode）**首次双击运行时自动安装**，无需手动操作；也可提前手动执行 `pip install yt-dlp qrcode`；
3. ffmpeg **已随仓库附带**（ffmpeg.exe，和脚本同目录），无需额外安装；脚本也会自动探测系统 PATH 里的 ffmpeg；
4. 双击 `扫码登录.bat` 登录 → 双击 `下载视频.bat` 下载。

## 怎么用

**第一次使用**：双击 `扫码登录.bat` → 自动弹出B站登录二维码 → 手机B站APP扫一扫 → 点确认 → 显示"登录身份：xxx"即成功（Cookie 存为本目录的 cookies.txt）。

**日常下载**：双击 `下载视频.bat` → 粘贴B站视频链接 → 回车，视频自动下载到 `downloads\` 文件夹。

也支持命令行方式（可以带参数）：

```bat
python videofetch.py https://www.bilibili.com/video/BVxxxxxx

python videofetch.py --quality 1080p --danmaku <链接>
python videofetch.py --list-formats <链接>     :: 只看有哪些画质，不下载
```

## 支持的链接

- 普通单个视频
- 多P视频（一次下全部分P，按 `P001、P002…` 命名）
- 合集、收藏夹、UP主投稿列表（自动建子文件夹）

> 注意：收藏夹 / UP主投稿这类批量链接**必须带登录 Cookie** 才能访问（B站风控会拒绝游客），单视频和多P游客也能下。

## 会员画质怎么来

工具通过**扫码登录**获取登录态（走B站官方登录接口，不读浏览器、不装插件）：

1. 双击 `扫码登录.bat`，二维码图片自动弹出（终端里也有一份）；
2. 手机B站APP → 右上角「扫一扫」→ 点【确认登录】；
3. 看到「登录身份：xxx（大会员）」即完成，Cookie 已存为 cookies.txt。

Cookie 一般可用数月。若某天下载突然只有480P，重新扫一次码即可。

> cookies.txt 相当于你的登录凭证，只放在本机（.gitignore 已排除），**不要发给任何人**。

### 备选方案

- 浏览器插件：装 **Get cookies.txt LOCALLY**，在 bilibili.com 登录页导出 cookies.txt 放到本目录（新版 Edge/Chrome 的 Cookie 有应用绑定加密，外部程序直接读不了，所以默认不走这条路）；
- Firefox：`python videofetch.py --browser firefox <链接>`，Firefox 可直接读。

## 常用参数

| 参数 | 作用 |
|---|---|
| `--quality 1080p` / `720p` | 限制最高画质（默认 best，会员可到4K） |
| `--items 1-3` 或 `1,5` | 选集下载（整季/合集/收藏夹用；ss整季链接默认下全部集数） |
| `--browser chrome` | 换浏览器读 Cookie |
| `--sub` | 同时下载字幕（含AI字幕，转成 srt） |
| `--danmaku` | 同时下载弹幕（xml） |
| `--list-formats` | 只列出可选画质，不下载 |

## 说明

- 已下载过的视频会跳过（记录在 `downloads\downloaded.txt`），收藏夹可以反复运行、只补新的。
- **仅供个人离线观看，请勿二次分发或商用**，尊重UP主的劳动成果。
