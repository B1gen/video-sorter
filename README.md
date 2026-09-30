# 视频分类器（Windows）

按 **时长 / 帧率 / 分辨率 / 有无声音** 给文件夹里的视频分组浏览。选一个文件夹（或直接把文件夹拖进识别框），
程序会扫出所有视频、生成缩略图，左侧按档位分组，右侧显示缩略图 + 文件名。**鼠标停在缩略图上会直接播放预览**，**选中后按空格用系统自带播放器播放**，
**双击缩略图即可在资源管理器里定位到该视频**。

只做浏览和定位，不会移动、改名或删除任何文件。

## 快速开始

### 方式一：直接下载 exe（推荐，不需要装 Python）

到 GitHub 仓库的 **Releases** 页面（https://github.com/B1gen/video-sorter/releases/latest）下载：

* **`VideoSorter.exe`**：单个文件，双击就能用，方便拷到别的电脑（每次启动先解压，慢几秒）；
* **`VideoSorter-版本号-windows.zip`**：文件夹版，解压后双击里面的 `VideoSorter.exe`，启动更快。

第一次打开时 Windows 可能提示「Windows 已保护你的电脑」（程序没有数字签名），点「更多信息 → 仍要运行」。
也可以把文件夹直接拖到 exe 图标上，启动后会自动开始扫描。

这些 exe 由 GitHub Actions（`.github/workflows/build-windows.yml`）在 Windows 上自动打包：
每次合并到 `main` 都会重新打包，并更新 `video_sorter/__init__.py` 里版本号对应的 Release；
想发新版本，改一下 `__version__` 再合并即可。每个 PR 也会打包一次，
在 PR 的 Checks → 「Build Windows exe」→ Summary 页面底部的 Artifacts 里可以下载试用。
打包后会用 `VideoSorter.exe --self-test 报告文件` 实际解码视频、识别声音、写缓存，全部通过才算成功。

### 方式二：双击 `run_windows.bat` 运行源码（需要电脑上有 Python 3.9+）

第一次会自动建虚拟环境并装依赖（约 200 MB，需要联网），之后每次都是秒开；更新代码后依赖有变化也会自动补装。

没装 Python 的话，去 https://www.python.org/downloads/windows/ 下载安装，
安装时勾选 **Add python.exe to PATH**。

### 方式三：自己在本机打包 exe

```bat
build_windows.bat            :: 打包成文件夹，启动快 -> dist\VideoSorter\VideoSorter.exe（另附 zip）
build_windows.bat onefile    :: 打包成单个 exe，方便拷到别的电脑 -> dist\VideoSorter.exe
```

打包参数都在 `packaging/build.py` 里，本机打包和 GitHub 自动打包用的是同一份。

### 开发者用法

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
python -m pytest tests            # 全部测试
python main.py --self-test report.txt   # 和打包后一样的自检
```

## 界面怎么用

| 操作 | 效果 |
| --- | --- |
| 拖文件夹到顶部识别框 / 点「选择文件夹…」 | 开始扫描（也可以拖多个文件夹或单个视频文件） |
| **鼠标停在缩略图上** | 静音循环播放预览，底部蓝条是播放进度；移开即停 |
| **选中后按空格** | 用系统默认播放器（如 Windows 的「媒体播放器 / 电影和电视」）播放 |
| **双击缩略图** | 在资源管理器中打开所在文件夹并选中该文件 |
| 右键缩略图 | 定位文件、用默认播放器打开、复制完整路径 / 文件名 |
| 左侧分类树 | 点某个档位只看该类；点「全部」恢复 |
| 分组下拉框 | 切换分组维度：时长、帧率、分辨率、声音，以及「分辨率 → 帧率 → 时长」「声音 → 时长」等组合 |
| 排序下拉框 + 倒序 | 按文件名 / 时长 / 帧率 / 分辨率 / 大小 / 声音排序 |
| 右上搜索框 | 在当前分类里按文件名过滤 |
| 缩略图滑杆 | 四档缩略图大小 |
| 包含子文件夹 | 关掉就只扫当前一层 |
| 菜单「视图 → 鼠标悬停时播放预览」 | 关掉悬停预览（设置会记住） |

鼠标停在缩略图下方的文件名处会显示完整路径、精确分辨率、编码、大小等信息（关掉悬停预览后，停在画面上也会显示）。窗口大小、上次的文件夹、
分组和排序方式都会记住。

## 分类规则

* **时长**：≤5 秒、5–10 秒、10–20 秒、20–30 秒、30 秒–1 分钟、1–2 分钟、2–5 分钟、
  5–10 分钟、10–30 分钟、>30 分钟。
  实际录出来的「10 秒」往往是 10.03 秒，所以允许 0.6 秒的容差，不会掉到下一档。
* **帧率**：自动归一到标准帧率，29.97 → `30 fps`、23.976 → `24 fps`、59.94 → `60 fps`；
  非标准帧率按实测值显示（如 `43 fps`）。
* **分辨率**：按**短边**判定，所以竖屏 1080×1920 也算 `1080p`，横竖屏在信息里单独标注。
  常见档位有 360p / 480p / 720p / 1080p / 1200p / 1260p / 1440p (2K) / 2160p (4K) / 4320p (8K)，
  非标准尺寸直接显示短边像素（如 `668p`）。

**想改档位就改 `video_sorter/classify.py` 顶部那三张表**（`DURATION_BUCKETS`、`STANDARD_FPS`、
`RESOLUTION_STEPS`），界面和分类树会自动跟着变，不用改别的地方。
* **声音**：分成「有声音」「无声音（音轨是静音）」「无声音（没有音轨）」「有音轨（未测音量）」「声音未知」。
  没声音的视频缩略图左上角会有红色「无声」标记。
  * 有音轨但没声音（录屏、剪辑导出时常见的空音轨，或只有底噪、电流声）也算「无声音」。
    判定方法：解码音频，看**最响的一小段（约 20~40 毫秒）的 RMS 音量**，低于 -45 dB 就算静音。
    不看单个采样的峰值，因为底噪的峰值常到 -40 dB，但听起来就是没声音。
    视频有多条音轨时，所有音轨都安静才算静音。
  * 默认用依赖里的 **PyAV**（pip 包自带 FFmpeg 解码库）来测，**不需要另外装 ffmpeg**。
    10 分钟以内的视频从头到尾全部分析；更长的视频均匀抽 60 段、每段 10 秒。
    阈值和抽样参数在 `video_sorter/audio.py` 顶部（`SILENCE_THRESHOLD_DB` 等）。
  * 没装 PyAV 时，如果有 ffmpeg 就用它测，但只能测第一条音轨；两个都没有时，显示「有音轨（未测音量）」，
    状态栏会提示缺少 PyAV。更新代码后双击 `run_windows.bat` 会自动补装。
  * 没装 PyAV 时，有没有音轨由 ffprobe 或直接读文件头判断（读文件头支持 mp4 / mov / m4v / 3gp / mkv / webm）。

## 关于识别准确度：可选安装 ffmpeg

程序默认用 OpenCV 自带的解码器，绝大多数 mp4 / mov / mkv 都能正确读出时长、帧率、分辨率。

如果素材里有可变帧率（VFR）、手机竖屏旋转标记、或比较少见的编码，建议装一下 ffmpeg——
程序检测到就会优先用它，结果更准：

1. 从 https://www.gyan.dev/ffmpeg/builds/ 下载 release build 并解压；
2. 把 `ffprobe.exe` 和 `ffmpeg.exe` 放到 **exe 同目录**、同目录下的 `bin\` 文件夹，或加进系统 PATH。

状态栏和「帮助 → 关于」里会显示当前是否检测到 ffmpeg，以及静音识别用的是什么。

## 性能

* 遍历目录、解码元信息、生成缩略图分别在独立线程里跑，扫描过程中界面不卡，可以随时「停止」。
* 缩略图和元信息会缓存到本机（`%LOCALAPPDATA%\VideoSorter\...`），
  同一个文件夹**第二次扫描几乎瞬间完成**。文件被修改过会自动重新识别。
  （这一版改进了静音识别，升级后第一次扫描会把旧缓存重新识别一遍；
  之前没法测音量时留下的「未测音量」结果，装好 PyAV 后再扫描也会自动补测。）
* 悬停预览在鼠标停留约 0.35 秒后才开始（划过不会触发），同一时间只解码一个视频，最高 30 fps 显示；
  4K 等大文件解码跟不上时会自动跳帧，保证按原速播放。停留时长可改 `config.py` 的 `HOVER_PREVIEW_DELAY_MS`。
* 想清掉缓存：菜单「工具 → 清空缩略图缓存」。

## 支持的格式

mp4、m4v、mov、mkv、webm、avi、wmv、flv、f4v、mpg、mpeg、ts、mts、m2ts、vob、3gp、asf、
rm、rmvb、ogv、divx、mxf、dv 等（列表在 `video_sorter/models.py` 的 `VIDEO_SUFFIXES`）。

## 已知限制

* 少数需要专有解码器的文件（如部分 rmvb、加密流）可能读不出信息，会显示为「未知」档并在状态栏计数；
  装上 ffmpeg 通常能解决。
* 代码本身跨平台（macOS / Linux 也能跑，双击会调用对应的 Finder / 文件管理器）；`packaging/build.py` 在 macOS / Linux 上也能打包，但自动发布只做了 Windows。

## 项目结构

```
main.py                      入口
video_sorter/
  classify.py                分类档位与阈值（要调分类就改这里）
  audio.py                   用 PyAV 识别音轨、判断是否静音（要调静音阈值就改这里）
  containers.py              不依赖 ffprobe，读 mp4 / mkv 文件头判断有无音轨
  probe.py                   读元信息 + 抽缩略图（ffprobe 优先，OpenCV 兜底）
  scanner.py                 目录遍历线程 + 解码线程池
  cache.py                   元信息与缩略图磁盘缓存
  preview.py                 悬停预览：后台线程用 OpenCV 按原速解码
  reveal.py                  在资源管理器中定位 / 打开文件
  icon.py                    程序图标（代码绘制，打包时导出成 exe 图标）
  selftest.py                --self-test 自检
  models.py  imaging.py  config.py
  ui/
    main_window.py           主窗口与交互
    drop_area.py             拖拽识别框
    category_tree.py         左侧分类树
    list_model.py            缩略图网格的模型 / 过滤 / 绘制
tests/test_classify.py       分类规则测试
tests/test_audio.py          音轨识别测试
run_windows.bat              双击运行源码
build_windows.bat            本机打包 exe
packaging/build.py           打包脚本（PyInstaller 参数都在这里）
.github/workflows/           GitHub 上自动打包 Windows exe 并发布 Release
```
