# 腔体图像检测程序

统一使用 `measure_image.cmd`：拖入图片测单张，拖入文件夹批量测量；双击时输入图片或文件夹路径，直接回车则处理默认的 `图片` 文件夹。快捷入口现在默认同时检测外边缘和底面候选边缘（A 内沿），在同一张图上对照显示，并分别保存状态和尺寸。绿色为 A 内沿，品红色为黑边外沿，黄色轮廓段表示灰度支持不足。

自动读取的 **0.009683443764816625 mm/像素** 是 2 mm 棋盘格的初步比例，仅用于 A 内沿；双边缘模式中的外沿先输出像素。A 内沿被称为底面候选边缘，其实际高度尚未验证。默认标定适用于 7008×7000 原图及固定成像条件，分辨率不符时拒测。Python 命令行和函数原来的默认 `inner` 保留；加 `--boundary-side both` 同时检测两条边，`outer` 可单独检测外沿。轮廓或尺寸检查不通过时保留复核信息、清空该边缘尺寸，不因另一条边失败而丢失本条通过的结果。

## 常用入口

| 文件 | 用途 |
| --- | --- |
| `measure_image.cmd` | 统一入口：自动识别图片或文件夹，进行单图或批量测量 |
| `verify_baseline.cmd` | 使用父目录 `图片` 中的四张原图进行回归检查 |
| `cavity_measure.py` | 保留原 Python 命令行入口和公开函数导入 |

检测结果仍保存到：

```text
F:\文件\研究生文件\38所\cavity_measurement_source\图片检测结果
```

双边缘结果根目录包含对比图 `overlay_preview.jpg`、`尺寸结果.txt`、两行 `dimensions.csv` 和 `result.json`，另有 `底面边缘/`、`外边缘/` 两个独立结果子目录。批量结果放在 `尺寸测量/时间戳`，汇总 CSV 每张图分两行并标明单位。根 JSON 的 `dimensions` 为 `null`，具体尺寸在 `boundaries.inner` 与 `boundaries.outer`，避免混淆两种边缘和单位。每次运行新建时间戳目录；默认输出位置不变。

长宽尺寸在标注图、预览图、`尺寸结果.txt`、`dimensions.csv` 和批量 `尺寸汇总.csv` 中统一显示到小数点后三位，像素和毫米单位均适用。算法计算、JSON 和采样点坐标保留原始数值。三位小数是显示格式，不代表达到 0.001 mm 的实际测量精度；毫米计量仍需独立标定及精度验证。

## 文件布局

```text
cavity_measurement/
├─ *.cmd                       常用启动入口
├─ cavity_measure.py            原 Python 入口的兼容转发
├─ requirements.txt             安装依赖入口
├─ src/cavity_measurement/       轮廓识别、尺寸算法
├─ scripts/                     PowerShell 启动脚本
├─ config/                      标定、输出路径、参数示例、已验证依赖版本
├─ tools/                       批量测量与四图回归检查工具
├─ tests/                       自动测试
├─ baseline/                    四图的冻结轮廓与原图哈希
├─ docs/                        使用说明、验证记录、文件迁移说明
└─ _deps/                       本机已安装的 OpenCV 私有依赖
```

详细命令及标定说明见 [使用说明](docs/USAGE.md)，检测范围和测试记录见 [验证记录](docs/VALIDATION.md)，原文件位置对照见 [整理说明](docs/STRUCTURE.md)。以上相对路径均以本程序根目录为基准。

## 命令行

在本程序根目录运行：

```powershell
python cavity_measure.py --help
python cavity_measure.py measure --image "..\图片\矩形腔体1.bmp"
python tools/measure_folder.py
python tools/verify_baseline.py
python -m unittest discover -s tests -v
```

启动脚本会优先使用本机已有的 Codex 配套 Python。换电脑时，需要 Python 3.10 或以上，并执行 `python -m pip install -r requirements.txt`；本机 `_deps` 不包含在源代码 ZIP 中。四张回归图片是开发数据，冻结轮廓是算法参考结果，均不能证明实际尺寸精度。

尺寸功能、参数与限制见 [尺寸测量说明](docs/MEASUREMENT.md)。四张开发图片未建立与所选光学边界同截面的可追溯尺寸真值，本程序不宣称实物精度或测量不确定度。修改 `config/calibration.json` 可更新默认标定；单次 `--calibration` 或 `--mm-per-pixel` 可覆盖默认值。
