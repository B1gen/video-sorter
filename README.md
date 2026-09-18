# 视频分类器（Windows）

按 **时长 / 帧率 / 分辨率** 给文件夹里的视频分组浏览。选一个文件夹（或直接把文件夹拖进识别框），
程序会扫出所有视频、生成缩略图，左侧按档位分组，右侧显示缩略图 + 文件名，**双击缩略图即可在
资源管理器里定位到该视频**。

只做浏览和定位，不会移动、改名或删除任何文件。

## 快速开始

### 方式一：双击运行（需要电脑上有 Python 3.9+）

双击 `run_windows.bat`。第一次会自动建虚拟环境并装依赖（约 200 MB，需要联网），之后每次都是秒开。

没装 Python 的话，去 https://www.python.org/downloads/windows/ 下载安装，
安装时勾选 **Add python.exe to PATH**。

### 方式二：打包成 exe，之后不再需要 Python

```bat
build_windows.bat            :: 打包成文件夹，启动快 -> dist\VideoSorter\VideoSorter.exe
build_windows.bat onefile    :: 打包成单个 exe，方便拷到别的电脑 -> dist\VideoSorter.exe
```

把 `dist` 里的成果拷到任何一台 Windows 上都能双击运行。也可以把文件夹直接拖到 exe 图标上，
启动后会自动开始扫描。

### 开发者用法

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
python tests/test_classify.py     # 分类规则回归测试
```

## 界面怎么用

| 操作 | 效果 |
| --- | --- |
| 拖文件夹到顶部识别框 / 点「选择文件夹…」 | 开始扫描（也可以拖多个文件夹或单个视频文件） |
| **双击缩略图** | 在资源管理器中打开所在文件夹并选中该文件 |
| 右键缩略图 | 定位文件、用默认播放器打开、复制完整路径 / 文件名 |
| 左侧分类树 | 点某个档位只看该类；点「全部」恢复 |
| 分组下拉框 | 切换分组维度：时长、帧率、分辨率，以及「分辨率 → 帧率 → 时长」等组合 |
| 排序下拉框 + 倒序 | 按文件名 / 时长 / 帧率 / 分辨率 / 大小排序 |
| 右上搜索框 | 在当前分类里按文件名过滤 |
| 缩略图滑杆 | 四档缩略图大小 |
| 包含子文件夹 | 关掉就只扫当前一层 |

鼠标停在缩略图上会显示完整路径、精确分辨率、编码、大小等信息。窗口大小、上次的文件夹、
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

## 关于识别准确度：可选安装 ffmpeg

程序默认用 OpenCV 自带的解码器，绝大多数 mp4 / mov / mkv 都能正确读出时长、帧率、分辨率。

如果素材里有可变帧率（VFR）、手机竖屏旋转标记、或比较少见的编码，建议装一下 ffmpeg——
程序检测到就会优先用它，结果更准：

1. 从 https://www.gyan.dev/ffmpeg/builds/ 下载 release build 并解压；
2. 把 `ffprobe.exe` 和 `ffmpeg.exe` 放到 **exe 同目录**、同目录下的 `bin\` 文件夹，或加进系统 PATH。

状态栏和「帮助 → 关于」里会显示当前是否检测到 ffmpeg。

## 性能

* 遍历目录、解码元信息、生成缩略图分别在独立线程里跑，扫描过程中界面不卡，可以随时「停止」。
* 缩略图和元信息会缓存到本机（`%LOCALAPPDATA%\VideoSorter\...`），
  同一个文件夹**第二次扫描几乎瞬间完成**。文件被修改过会自动重新识别。
* 想清掉缓存：菜单「工具 → 清空缩略图缓存」。

## 支持的格式

mp4、m4v、mov、mkv、webm、avi、wmv、flv、f4v、mpg、mpeg、ts、mts、m2ts、vob、3gp、asf、
rm、rmvb、ogv、divx、mxf、dv 等（列表在 `video_sorter/models.py` 的 `VIDEO_SUFFIXES`）。

## 已知限制

* 少数需要专有解码器的文件（如部分 rmvb、加密流）可能读不出信息，会显示为「未知」档并在状态栏计数；
  装上 ffmpeg 通常能解决。
* 代码本身跨平台（macOS / Linux 也能跑，双击会调用对应的 Finder / 文件管理器），但打包脚本只写了 Windows。

## 项目结构

```
main.py                      入口
video_sorter/
  classify.py                分类档位与阈值（要调分类就改这里）
  probe.py                   读元信息 + 抽缩略图（ffprobe 优先，OpenCV 兜底）
  scanner.py                 目录遍历线程 + 解码线程池
  cache.py                   元信息与缩略图磁盘缓存
  reveal.py                  在资源管理器中定位 / 打开文件
  models.py  imaging.py  config.py
  ui/
    main_window.py           主窗口与交互
    drop_area.py             拖拽识别框
    category_tree.py         左侧分类树
    list_model.py            缩略图网格的模型 / 过滤 / 绘制
tests/test_classify.py       分类规则测试
run_windows.bat              双击运行
build_windows.bat            打包 exe
```
