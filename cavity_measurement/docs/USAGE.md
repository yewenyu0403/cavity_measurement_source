# 圆角方腔内部边框识别与尺寸检测工具

默认优先识别**外围黑色边界带靠腔内的一沿（含圆角）**，即用户在局部图中确认的 A 边、所需的底面与侧壁交界。
图像操作定义是沿指向腔内的法向，从深色边界带进入较亮腔内的灰度过渡；单幅图不独立证明交界深度或实体截面。
默认完成“内轮廓 → 去除圆角段 → 四边独立拟合 → 中央对边间距”的像素尺寸计算；有独立标定时可换算毫米。原有灰度区域定位尺寸流程通过 `--detection strict` 保留。
完整轮廓已在用户提供的四张实拍图上进行回归验证；尺寸计算另有独立已知几何、旋转、透视和拒测测试。
四张实拍图用于本轮开发调参，不能作为独立测试集，也没有提供可追溯的尺寸真值。

## 四张实拍图与以后复查

把图片或图片文件夹拖到统一入口 `measure_image.cmd` 上即可自动选择单图或批量测量。双击后可输入路径，或在路径处直接回车处理默认 `图片` 目录。未标定时，比例输入直接回车。
程序通过暗边带定位、凸轮廓初始化、原图灰度法向剖面连续跟踪，输出内部边框闭合轮廓，再从四条直边的受支持点独立拟合并计算长宽。
定位时使用的凸性只约束搜索初值；最终轮廓不强制为矩形或圆弧。
绿色表示达到灰度支持门限的边界，黄色表示证据较弱且受连续性约束的段落。
默认 `--boundary-side inner` 跟踪黑边的**内侧暗到亮过渡**，绿色线位于黑边靠腔内的一沿。
可用 `--boundary-side outer` 对照之前的外侧轮廓；程序依据灰度边缘定位，不采用固定内缩像素数。

默认状态 `pixel_only` 表示像素尺寸检查通过，`dimensions` 给出长度和宽度，单位 `px`；提供独立标定后可返回 `measured` 和毫米尺寸。`review_required` 表示尺寸检查未通过，长度、宽度不输出。只有显式 `--detection outline` 才返回 `contour_detected`、`dimensions: null`，表示仅识别轮廓。
尺寸定义和算法门限见 `docs/MEASUREMENT.md`。四张图回归通过不代表实物尺寸精度已经验证。

```powershell
# 只识别已确认的 A 内边框；默认不加 outline 时还会计算像素长宽
python cavity_measure.py measure --image "..\图片\矩形腔体1.bmp" --detection outline

# 对照原来的外侧黑边轮廓
python cavity_measure.py measure --image "..\图片\矩形腔体1.bmp" --detection outline --boundary-side outer

# 明确调用原有四条直线的尺寸计量流程
python cavity_measure.py measure --image "D:\图片\腔体.png" --detection strict --calibration calibration.json

# 以后改代码后，用相同的四张图复查
python tools/verify_baseline.py
```

也可直接双击 `verify_baseline.cmd`，默认读取程序父目录中的 `图片` 文件夹。
`baseline/manifest.json` 记录四张原始 BMP 的 SHA-256 和边界模式 `inner`；`baseline/contour_1.json` 至 `contour_4.json` 保存已更新的 A 内边框回归参考轮廓。
校验源图哈希后，重新检测并检查参考掩膜重合率和包围盒漂移，结果保存到统一输出位置的 `四图基准验证/时间戳`。
源图改变时会报哈希不一致，脚本不会自动覆盖参考。
这些参考是**目视复查后的算法输出**，用于发现后续代码回退，不是人工逐点标注的真值或计量基准。
原图保留在现有 `图片` 目录中，没有改写或重复存储。

## 最快开始

在本机直接双击 `run_demo.cmd` 可生成并测量一个合成的 60 × 40 mm 圆角方腔。
示例运行后，会打开“图片检测结果/合成示例/时间戳/overlay.png”查看标注结果。

当前统一输出位置：`F:\文件\研究生文件\38所\cavity_measurement_source\图片检测结果`。
测量结果保存到其下的时间戳子目录，合成示例保存到“合成示例/时间戳”，标定文件保存到“标定/时间戳”。
路径在程序根目录的 `config/output_config.json` 中设置；修改 `output_root` 即可同时改变所有启动方式的默认位置。
命令行的 `--out` 仍可单独指定位置。复制到其他电脑后，请同步修改该配置。

安装到其他电脑时，在本目录执行：

```powershell
python -m pip install -r requirements.txt
python cavity_measure.py demo
```

要求 Python 3.10 或以上。代码依赖 NumPy 和 OpenCV，不依赖深度学习模型、训练数据或 GPU。
本机的 `_deps` 目录保存了独立安装的 OpenCV，没有修改系统 Python；源代码 ZIP 不包含该目录。
批处理脚本优先使用本机 Codex 配套 Python，其他电脑则查找 `python`。

## 用自己的图测量

**便捷方式：把照片或图片文件夹拖到 `measure_image.cmd` 上。**
脚本询问已知的毫米/像素比例；未标定直接回车。每次结果放在“图片检测结果”下独立的时间戳子目录。
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

暂时没有标定也可以运行：

```powershell
python cavity_measure.py measure --image "D:\图片\腔体.png"
```

默认 `--detection auto` 与 `--detection contour` 都识别选定的完整暗边轮廓，并计算尺寸；没有标定且检查通过时为 `pixel_only`。找不到完整暗边、存在多个候选或尺寸证据不足时会拒测，不再自动换测其他区域。旧灰度区域测量请明确使用 `--detection strict`。

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
工具随后会对参考点、测量图像和人工种子点进行一致的去畸变处理。
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

默认内轮廓模式在 ROI 内寻找完整暗边带，再跟踪 A 内边框；ROI 应包含完整边界并留有余量。以下人工种子与极性参数仅适用于旧 `--detection strict` 流程：它通过孤立亮/暗区域定位，默认腔内比外部暗，亮腔使用 `--polarity bright`。

指定包含一个腔体、四周留有余量的 ROI，数值分别为左上角 x、y、宽、高：

```powershell
python cavity_measure.py measure --image cavity.png --roi 100 80 800 600 --mm-per-pixel 0.02
```

强透视、倒角或多重边缘可能使自动外接矩形偏离目标边，此时提供四个近似的**直边延长线交点**。
圆角方腔的种子点是虚拟尖角，不是圆弧上任意四个点。
创建 `corners.json`，然后使用 `--detection strict --corners corners.json`：

```json
{
  "corners_px": [[200, 180], [800, 180], [800, 580], [200, 580]]
}
```

种子点及 ROI 均使用**原始完整图像坐标**。`--corners` 优先于自动定位，此时 ROI 不参与定位。
四点会自动按周向排列，边序号 E0～E3 随排列而定，不对应固定的工件 X/Y 轴。
最终边缘应位于种子线附近，默认搜索带为线两侧各 12 px；完整灰度剖面还需留约 4 px 余量。
搜索带过大会增加把倒角、反光或底面边界误认为腔口的风险。

## 算法流程

默认内轮廓尺寸流程见 `docs/MEASUREMENT.md`。以下保留旧 `--detection strict` 流程的说明和参数：

1. 可选：依据相机内参对原图去畸变。
2. 对 ROI 做 Otsu 阈值分割，使用外接旋转矩形获得四边初值；也可人工指定四角。
3. 每条种子边默认去掉两端各 22%，避开圆角，只在中间直边取样。
4. 沿直边法向以 0.25 px 间隔重采样灰度剖面。
5. 检查对比度、梯度方向与相近强度的多重边缘；歧义剖面不参与拟合。
6. 对主边缘附近的灰度梯度做背景扣除和局部重心计算，得到亚像素坐标。
   重心定位对模糊宽度、非对称反射和多重边缘仍敏感；0.25 px 是采样步长，不是精度指标。
7. 每条边单独做 RANSAC，再用正交最小二乘精拟合；不强制四边平行或垂直。
8. 若有平面标定，把可靠点转换到毫米平面后重新拟合。
9. 检查有效点比例、支持范围、拟合残差、对边平行度与邻边正交性。
10. 在质量检查通过时，输出两组对边在中心截面处的间距，较大者称 `length`，较小者称 `width`。

对于不平行的对边，两个无限直线不存在唯一的固定间距。
因此工具会将状态设为 `review_required`，不输出单一矩形长宽，同时保留 25%、50%、75% 位置的截面间距供分析。
这些截面间距沿两侧法向的角平分线方向计算，是明确约定的几何量，不自动等同于图纸尺寸定义。

旧 `--detection strict` 的参数保存在 `config/settings.example.json`，可复制修改后通过 `--config my_settings.json` 使用。默认内轮廓尺寸参数见 `config/contour_measurement.example.json`，通过 `--measurement-config my_measurement.json` 使用。

| 参数 | 默认值 | 调整依据 |
|---|---:|---|
| `band_px` | 12 | 种子线两侧搜索范围；优先改善定位，不应盲目放宽 |
| `corner_exclusion` | 0.22 | 每条边两端的排除比例；圆角较大时增大 |
| `min_gradient` | 5 | 每像素灰度变化阈值；照明过弱时先改善拍摄 |
| `ransac_threshold_px` | 0.7 | 点到直线的内点阈值 |
| `max_rms_px` | 0.45 | 内点拟合残差上限 |
| `max_parallel_angle_deg` | 0.20 | 对边夹角检查阈值 |
| `max_orthogonal_error_deg` | 0.50 | 邻边偏离 90° 的检查阈值 |

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

旧 `strict` 直线流程另有以下诊断：

- `overlay.png`：四边、边缘点、RANSAC 离群点（红色）、拟合残差及测量状态。
- `result.json`：尺寸、单位、标定信息、四边方程、截面间距和质量检查结果。
- `edge_points.csv`：每个采样点的图像坐标、内点标志及可选毫米坐标。

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
from cavity_measure import Settings, read_image, read_json, analyze_array, save_measurement, default_output_path

image = read_image("cavity.png")
calibration = read_json("calibration.json")
report, overlay, points = analyze_array(image, Settings(), calibration)
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

测试覆盖旋转及噪声、透视补偿、镜头畸变一致处理、标量标定、亮/暗极性、
低对比度拒测、多腔体拒测和 ROI、未校正梯形、异常标定、RANSAC 离群点、
错误初值、中文路径、命令行标定以及失败时清除过期尺寸。
具体运行记录见 `docs/VALIDATION.md`。

API 依据：[OpenCV 几何形状接口](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html)、
[OpenCV 标定与去畸变接口](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)、
[OpenCV 形态学与黑帽操作](https://docs.opencv.org/4.x/d9/d61/tutorial_py_morphological_ops.html)。
