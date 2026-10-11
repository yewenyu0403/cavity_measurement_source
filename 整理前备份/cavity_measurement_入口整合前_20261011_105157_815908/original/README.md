# 腔体图像检测程序

在本文件夹中，把图片拖到 `measure_image.cmd` 上即可检测；没有实际标定值时，比例输入直接回车。程序默认识别已确认的 **A 内边框：外围黑边靠腔内的一沿，包含圆角**。

**当前支持 A 内边框的像素长宽测量。** 默认状态 `pixel_only`，单位 `px`；没有实际标定时，不输出毫米尺寸。长宽是四条直边独立拟合后的中央截面对边间距，圆角不参与拟合。`--detection outline` 仍可仅识别轮廓。图像检查通过不能代替实际尺寸精度验证。

## 常用入口

| 文件 | 用途 |
| --- | --- |
| `measure_image.cmd` | 拖入图片或双击后输入图片路径，测量 A 内边框长宽 |
| `measure_folder.cmd` | 双击测量父目录 `图片` 中所有图片；也可拖入其他图片文件夹 |
| `verify_baseline.cmd` | 使用父目录 `图片` 中的四张原图进行回归检查 |
| `run_demo.cmd` | 运行合成的 60 × 40 mm 示例并打开结果图 |
| `cavity_measure.py` | 保留原 Python 命令行入口和公开函数导入 |

检测结果仍保存到：

```text
F:\文件\研究生文件\38所\cavity_measurement_source\图片检测结果
```

单图结果包括 `尺寸结果.txt`、`dimensions.csv`、`result.json` 和标注图；批量结果放在 `尺寸测量/时间戳`，另有 `尺寸汇总.csv` 和总览图。每次运行创建独立的时间戳子目录。修改 [config/output_config.json](config/output_config.json) 中的 `output_root` 可更改默认位置；命令行 `--out` 可指定单次运行的位置。

## 文件布局

```text
cavity_measurement/
├─ *.cmd                       常用启动入口
├─ cavity_measure.py            原 Python 入口的兼容转发
├─ requirements.txt             安装依赖入口
├─ src/cavity_measurement/       轮廓识别、尺寸算法、合成图生成
├─ scripts/                     PowerShell 启动脚本
├─ config/                      输出路径、参数示例、已验证依赖版本
├─ tools/                       四图回归检查工具
├─ tests/                       自动测试
├─ baseline/                    四图的冻结轮廓与原图哈希
├─ examples/demo_output/         随程序保留的历史合成示例
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

尺寸功能、参数与限制见 [尺寸测量说明](docs/MEASUREMENT.md)。四张开发图片尚无独立的实际尺寸真值，本程序不宣称实物精度或测量不确定度。
