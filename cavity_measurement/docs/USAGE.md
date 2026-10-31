# 圆角方腔内部边框识别与尺寸检测工具

2026-10-31 当前默认：将图片或文件夹拖入 `measure_image.cmd`，或双击后输入路径，均只检测绿色 A 内边缘；默认不运行紫色外边缘拟合。结果直接保存到本次输出目录，JSON 的 `dimensions` 是内边缘尺寸，不再需要从 `boundaries.inner` 读取。默认初步标定、内边缘算法及拒测规则不变。`outer` / `both` 仅在手动显式指定时运行，下方旧日期记录保留。

2026-10-29 当前状态：按用户要求启用20张10 mm棋盘格、773个交点的联合比例0.009685371864397972 mm/像素，适用于7008×7000原图和用户确认的相同成像设置、测量平面高度。单图与批量入口自动读取config/calibration.json；A内沿换算毫米，外沿默认仍输出像素。轮廓定位、直边拟合和质量门限未因本次标定切换改变。该比例尚未经过独立标准长度验证，未启用镜头畸变校正。以下带日期的旧条目保留作历史记录。

2026-10-27 恢复记录：按用户要求恢复到腔体3未舍入读数60.0264474536×40.0374825574 mm的历史版本。默认重心法及标定比例0.009683443764816625 mm/像素已恢复；三帧联合标定参数与亚像素对照版本已备份保留，当前未启用。灰度剖面对照工具退出活动程序目录并归档，既有检测结果不删除。以下带日期的旧条目保留作历史记录。


快捷入口 `measure_image.cmd` 现在默认只识别**靠腔内的 A 内沿（底面候选边缘）**，保留圆角。A 内沿的实际物理高度尚未验证。

2026-10-25：修复零权重细化导致的人工轨迹跳变后，通过轮廓与直边质量检查的图片恢复尺寸输出。双边缘总览图现在保留已通过检查的 A 内沿长宽箭头与文字，外沿仍为独立的像素结果。无需改变原有启动操作或输入标定比例；未通过的边缘继续留空。

## 可选：外边缘与底面候选边缘同时检测（2026-10-24）

仅显式选择 `--boundary-side both` 或 PowerShell 参数 `-BoundarySide both` 时运行本节的双边缘模式。绿色是 A 内沿，品红色是外沿，黄色轮廓段是弱灰度支持；轨迹发生断裂时不强行连成闭合边框。

- 对比图和双边缘汇总在时间戳根目录；`底面边缘/`、`外边缘/` 分别保存各自结果、轮廓坐标和标注图。
- 当前初步标定仅用于 A 内沿，双边缘模式中的外沿只输出像素；不能将两种单位直接相减，或将两轮廓的间距解释为壁厚、腔深。
- 单独使用 `--boundary-side outer` 时也不会自动套用 A 内沿的默认标定；只有显式提供适用于外沿平面的 `--calibration` 或 `--mm-per-pixel` 才换算毫米。
- `completed` 表示两条边均完成指定的检测／测量检查；只做轮廓时不输出尺寸。任一边需要复核，整体为 `review_required`；另一条通过的边缘仍保存自己的结果。两边都无法定位时为 `failed`。退出码分别为 0、2、2。
- 检查不通过的候选轨迹可以显示和导出，但其尺寸为空；未闭合候选不生成实心掩膜、面积或周长。它不代表完整边界已识别成功。
- 根 JSON 使用 `boundaries.inner`、`boundaries.outer` 存储两条独立结果，根 `dimensions=null`；CSV 每条边一行。

Python 原默认仍为 `inner`。命令示例：

```powershell
python cavity_measure.py measure --image "..\图片\2026-10-23_10-03-51\矩形腔体2.bmp" --boundary-side both
python tools/measure_folder.py --images "..\图片\底面" --boundary-side both
python cavity_measure.py measure --image "..\图片\矩形腔体1.bmp" --boundary-side outer
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/measure_image.ps1 -InputPath "..\图片\矩形腔体1.bmp" -BoundarySide inner
```

以下原有单边示例仍有效。
图像操作定义是沿指向腔内的法向，从深色边界带进入较亮腔内的灰度过渡；单幅图不独立证明交界深度或实体截面。
默认完成“内轮廓 → 去除圆角段 → 四边独立拟合 → 中央对边间距”的像素尺寸计算；有独立标定时可换算毫米。
完整轮廓已在用户提供的四张实拍图上进行回归验证；尺寸计算另有独立已知几何、旋转、透视和拒测测试。
四张实拍图用于本轮开发调参，不能作为独立测试集，也没有提供可追溯的尺寸真值。

## 四张实拍图与以后复查

把图片或图片文件夹拖到统一入口 `measure_image.cmd` 上即可自动选择单图或批量测量。双击后可输入路径，或在路径处直接回车处理默认 `图片` 目录。启动后自动读取 `config/calibration.json` 的初步联合比例 `0.009685371864397972 mm/像素`（20张10 mm棋盘格、773个交点），不再询问比例。
程序通过暗边带定位、凸轮廓初始化、原图灰度法向剖面连续跟踪，输出内部边框闭合轮廓，再从四条直边的受支持点独立拟合并计算长宽。
定位时使用的凸性只约束搜索初值；最终轮廓不强制为矩形或圆弧。
绿色表示达到灰度支持门限的边界，黄色表示证据较弱且受连续性约束的段落。
默认 `--boundary-side inner` 跟踪黑边的**内侧暗到亮过渡**，绿色线位于黑边靠腔内的一沿。
可用 `--boundary-side outer` 对照之前的外侧轮廓；程序依据灰度边缘定位，不采用固定内缩像素数。

默认读取已有标定，检查通过时输出 `measured` 和毫米尺寸；显式 `--pixels-only` 可禁用默认标定。状态 `pixel_only` 表示像素尺寸检查通过，`dimensions` 给出长度和宽度，单位 `px`；提供独立标定后可返回 `measured` 和毫米尺寸。`review_required` 表示尺寸检查未通过，长度、宽度不输出。只有显式 `--detection outline` 才返回 `contour_detected`、`dimensions: null`，表示仅识别轮廓。
尺寸定义和算法门限见 `docs/MEASUREMENT.md`。四张图回归通过不代表实物尺寸精度已经验证。

```powershell
# 只识别已确认的 A 内边框；默认不加 outline 时还会计算像素长宽
python cavity_measure.py measure --image "..\图片\矩形腔体1.bmp" --detection outline

# 对照原来的外侧黑边轮廓
python cavity_measure.py measure --image "..\图片\矩形腔体1.bmp" --detection outline --boundary-side outer

# 以后改代码后，用相同的四张图复查
python tools/verify_baseline.py
```

也可直接双击 `verify_baseline.cmd`，默认读取程序父目录中的 `图片` 文件夹。
`baseline/manifest.json` 记录四张原始 BMP 的 SHA-256 和边界模式 `inner`；`baseline/contour_1.json` 至 `contour_4.json` 保存已更新的 A 内边框回归参考轮廓。
校验源图哈希后，重新检测并检查参考掩膜重合率和包围盒漂移，结果保存到统一输出位置的 `四图基准验证/时间戳`。
源图改变时会报哈希不一致，脚本不会自动覆盖参考。
这些参考是**目视复查后的算法输出**，用于发现后续代码回退，不是人工逐点标注的真值或计量基准。
原图保留在现有 `图片` 目录中，没有改写或重复存储。

## 输出位置与安装

当前统一输出位置：`F:\文件\研究生文件\38所\cavity_measurement_source\图片检测结果`。
测量结果保存到其下的时间戳子目录，标定文件保存到“标定/时间戳”。该目录不纳入 git 版本管理。
路径在程序根目录的 `config/output_config.json` 中设置；修改 `output_root` 即可同时改变所有启动方式的默认位置。
命令行的 `--out` 仍可单独指定位置。复制到其他电脑后，请同步修改该配置。

安装到其他电脑时，在本目录执行：

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

要求 Python 3.10 或以上。代码依赖 NumPy 和 OpenCV，不依赖深度学习模型、训练数据或 GPU。
本机的 `_deps` 目录保存了独立安装的 OpenCV，没有修改系统 Python；源代码 ZIP 不包含该目录。
批处理脚本优先使用本机 Codex 配套 Python，其他电脑则查找 `python`。

## 用自己的图测量

**便捷方式：把照片或图片文件夹拖到 `measure_image.cmd` 上。**
脚本自动读取默认标定，不再询问毫米/像素比例。默认文件的分辨率为 7008×7000；不匹配时拒测，避免把缩放图直接按原比例换算。每次结果放在“图片检测结果”下独立的时间戳子目录。
如需透视补偿、指定 ROI 或使用标定文件，请使用下面的命令行方式。

### 1. 已知同一测量平面的像素当量

例如，一件独立标准器的已知长度为 20 mm，在当前成像平面上对应 1000 pixel，
则 `mm_per_pixel = 20 / 1000 = 0.02`：

```powershell
python cavity_measure.py measure --image "D:\图片\腔体.png" --mm-per-pixel 0.02
```

以上 `0.02` **仅为用法示例**。必须换成自己系统的实际标定值。
标尺应与要测的 A 内边框所在底面共面，测量时保持镜头、焦距、相机位置和工件高度不变。
标量比例不能补偿空间倾斜，也不自动消除镜头畸变。
不能用被测腔体的设计值 60 × 40 mm 反算比例后，再用该比例“验证”尺寸。

需要只输出像素时，显式忽略默认标定：

```powershell
python cavity_measure.py measure --image "D:\图片\腔体.png" --pixels-only
python tools/measure_folder.py --pixels-only
```

默认标定保存在 `config/calibration.json`，修改该文件可更新所有入口。当前值是20张10 mm棋盘格、773个交点的初步联合拟合，尚未完成独立标准长度验证，未启用镜头畸变校正。Python 函数调用仍需显式传入标定，不会暗中加载默认值。

默认 `--detection auto` 与 `--detection contour` 都识别选定的完整暗边轮廓，并计算尺寸；没有标定且检查通过时为 `pixel_only`。找不到完整暗边、存在多个候选或尺寸证据不足时会拒测，不再自动换测其他区域。

### 2. 有平面倾斜：用独立参考点进行平面标定

在独立标定板或标准器上选取至少 4 个不共线的点，记录图像坐标及其已知毫米坐标。
实际建议使用更多、覆盖测量区域的参考点，并用额外标准长度独立复核。
各点必须是同一批一一对应的点，可以采用任意一致的顺序。

新建 `reference_points.json`：

```json
{
  "image_points_px": [[120, 110], [820, 140], [780, 650], [160, 620]],
  "world_points_mm": [[0, 0], [70, 0], [70, 50], [0, 50]]
}
```

这些坐标也是示例，需要替换。图像坐标按 `[x, y]`，原点在原始完整图像左上角。
参考平面要与实际腔口共面，标定后相机与腔口平面的相对姿态应保持一致。
有四个点时可能出现恰好为零的拟合残差，这不能证明标定准确。

```powershell
python cavity_measure.py calibrate --image "reference.png" --points reference_points.json --out calibration.json
python cavity_measure.py measure --image "cavity.png" --calibration calibration.json
```

如果已有镜头内参和畸变系数，将其保存为 JSON，标定时增加 `--intrinsics intrinsics.json`。
工具随后会对参考点、测量图像和 ROI 进行一致的去畸变处理。
内参应与当前相机分辨率、焦距和对焦状态一致。

```json
{
  "camera_matrix": [[1200, 0, 500], [0, 1200, 380], [0, 0, 1]],
  "dist_coeffs": [-0.1, 0.01, 0, 0, 0]
}
```

内参示例不能用于真实照片。**本工具读取已有内参，不实现多视图镜头内参标定。**
平面单应变换也不能代替镜头畸变校正。

### 3. 自动定位不稳定或图中有多个腔体

默认内轮廓模式在 ROI 内寻找完整暗边带，再跟踪 A 内边框；ROI 应包含完整边界并留有余量。

指定包含一个腔体、四周留有余量的 ROI，数值分别为左上角 x、y、宽、高，使用**原始完整图像坐标**：

```powershell
python cavity_measure.py measure --image cavity.png --roi 100 80 800 600 --mm-per-pixel 0.02
```

## 算法流程

内轮廓尺寸流程、质量门限及状态定义见 `docs/MEASUREMENT.md`。

对于不平行的对边，两个无限直线不存在唯一的固定间距。
因此工具会将状态设为 `review_required`，不输出单一矩形长宽，同时保留 25%、50%、75% 位置的截面间距供分析。
这些截面间距沿两侧法向的角平分线方向计算，是明确约定的几何量，不自动等同于图纸尺寸定义。

尺寸质量门限见 `config/contour_measurement.example.json`，可复制修改后通过 `--measurement-config my_measurement.json` 使用。
这些默认值是初始工程参数，**不是图纸公差或计量验收标准**。
调整门限时应结合实拍图、像素当量和参考测量，而不能只为使结果“通过”。

## 输出与状态

默认尺寸模式成功时，以下轮廓文件与尺寸文件一起输出；仅轮廓模式只输出轮廓及空尺寸说明：

- `overlay.png`：原始分辨率的完整轮廓叠加图。
- `overlay_preview.jpg`：便于打开的小尺寸预览。
- `contour_mask.png`：开口内部为 255、外部为 0 的填充掩膜。
- `contour_points.csv`：顺序排列的轮廓坐标、灰度梯度、支持标志及可选毫米坐标；最后一个点与第一个点闭合。
- `result.json`：完整轮廓、状态、灰度支持指标、识别方法与标定信息。

默认尺寸模式另有 `尺寸结果.txt`、`dimensions.csv`、带长宽箭头的标注图，以及 `edge_points.csv`。JSON 中保留独立四边方程、拟合残差与多截面间距。

| `status` | 含义 | CLI 退出码 |
|---|---|---:|
| `contour_detected` | 完整开口轮廓识别成功；本次未执行尺寸计量，`dimensions` 为 null | 0 |
| `measured` | 有毫米标定，当前图像检查通过 | 0 |
| `pixel_only` | 图像检查通过，只有像素尺寸 | 0 |
| `review_required` | 已提取边缘，但几何或拟合检查未通过；`dimensions` 为 null | 2 |
| `failed` | 图像、参数或可用边缘不足；`dimensions` 为 null | 2 |

`measured` 表示软件检查通过；它不证明绝对精度、不确定度或工件尺寸合格。
失败也会覆盖当前 `result.json`，防止后续程序误读上一次的尺寸。
失败时也会覆盖 `尺寸结果.txt` 和 `dimensions.csv`，尺寸列留空。如果复用目录，旧标注图和点坐标 CSV 不属于当前结果，应以最新状态为准。
建议每张图使用单独的输出目录，自动集成时优先检查退出码和 `result.json`。

## Python 接口

```python
from cavity_measure import read_image, read_json, analyze_array, save_measurement, default_output_path

image = read_image("cavity.png")
calibration = read_json("calibration.json")
report, overlay, points = analyze_array(image, calibration=calibration)
save_measurement(default_output_path(), report, overlay, points)
if report["dimensions"] is not None:
    print(report["dimensions"]["length"], report["dimensions"]["width"])
```

## 适用边界和现场验证

- 测量对象是清楚可见的 A 内边框（用户指定的底面与侧壁交界光学边缘），应属于同一测量平面。腔深、不同深度处的壁间距、底面形状、圆角半径和倒角尺寸不在本版范围内。
- 先明确测量的是倒角外边、倒角内边还是指定实体截面。灰度边缘不一定就是图纸规定的尺寸边界。
- 自动定位适用于一个主要、相对孤立、近似矩形的腔口。纹理、反光区域也可能形成类似候选区，需要检查标注图。
- 当直边不足、圆角占比过大、目标太小、严重失焦或反光掩盖实体边界时，应拒测或重新拍摄。
- 一个稳定、笔直的错误反光边界也可能通过残差检查。算法无法仅凭单幅图保证其就是正确实体边缘。
- 将真实零件与可靠参考设备在相同尺寸定义下对比，覆盖多件、多位置、重复装夹、光照和高度变化，分别评估偏差与重复性。
- 拟合残差、重采样步长、图像重复性以及合成图误差都不能当作实际测量不确定度。

## 验证

```powershell
python -m unittest discover -s tests -v
```

测试覆盖圆角轮廓跟踪与纹理干扰、内外边界、空白及裁切拒测、多腔体拒测和 ROI、
解析旋转圆角腔尺寸、弱支持点排除、弯曲边界拒测、未标定透视不输出矩形长宽、
默认标定读取与分辨率拒测、平面标定（透视、镜头畸变、异常参考点、命令行）、
异常标定、RANSAC 离群点、中文路径、批量部分失败以及失败时清除过期尺寸。
具体运行记录见 `docs/VALIDATION.md`。

API 依据：[OpenCV 几何形状接口](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html)、
[OpenCV 标定与去畸变接口](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)、
[OpenCV 形态学与黑帽操作](https://docs.opencv.org/4.x/d9/d61/tutorial_py_morphological_ops.html)。


## 2026-10-27：A 内沿灰度剖面与亚像素定位对照（历史功能，当前已停用）

在程序根目录运行独立诊断工具：

```powershell
python -X utf8 tools/inspect_profiles.py --image "..\图片\2026-10-25_14-15-50\矩形腔体3.bmp" --out "..\图片检测结果\剖面对照\腔体3_新目录" --reference-length 60.0067 --reference-width 40.0116
```

输出目录必须尚不存在，防止覆盖历史结果。正常 `measure_image.cmd` 和 `measure` 仍使用重心法。
诊断工具读取同一默认标定，对相同灰度剖面和连续跟踪路径，比较原局部梯度重心与局部梯度峰三点抛物线插值。
`--reference-length`、`--reference-width` 必须同时提供，只用于运行完成后的偏差比较，不参与定位、筛选、拟合或标定。
两种方法分别通过原有灰度和尺寸门限；无有效峰的点标为弱支持，不用插值或回退坐标冒充有效证据。

输出包括：`重心法/`、`梯度峰插值/` 的结果与标注；`profiles.npz` 的全部原始灰度、平滑灰度、梯度、法向、跟踪及定位数组；
`定位点对照.csv` 的两套坐标、向腔内位移及有效标记；`代表位置灰度剖面.csv` 的四边30%、50%、70%位置的完整曲线；
三张 `profile_comparison_*.png` 与 `comparison.json`。JSON另含相同支持点掩膜下的拟合对照，以区分位置变化和点集变化。
这些是同图光学定义比较，不是独立准确度、重复性或测量不确定度验证。工具仅诊断 A 内沿，不套用其比例测量外沿。


## 2026-10-31：临时测试与诊断文件位置

临时测试脚本、单图诊断、分析报告、预览和测试输出统一存放于 F:\文件\研究生文件\38所\测试，按日期和任务建立子目录。测试运行显式使用 --out 指定该目录下的新输出子目录。项目中的 tests/ 保留现有位置，日常图片检测结果继续按 config/output_config.json 保存。旧桌面工作目录中的文件已按用户确认删除，不存在可迁移的历史测试文件。
