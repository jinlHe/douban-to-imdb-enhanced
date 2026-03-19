# douban-to-imdb-enhanced

[English README](README_en.md)

将豆瓣电影评分导出为 CSV，再通过 Selenium 同步到 IMDb。

当前仓库基于 [f-is-h/douban-to-imdb](https://github.com/f-is-h/douban-to-imdb) 做了适配和补充，文档说明以本仓库当前代码为准。

## 项目流程

整个流程分两步，顺序不能反：

1. 运行 `douban_to_csv.py`，从豆瓣导出评分到本地 CSV
2. 运行 `csv_to_imdb.py`，读取 CSV 并同步到 IMDb

## 环境要求

- Windows
- Python 3.8 左右版本
- Google Chrome
- 与本机 Chrome 匹配的 `chromedriver.exe`

## 安装依赖

使用 `venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

使用 conda：

```powershell
conda create -n douban-to-imdb-enhanced python=3.8 -y
conda activate douban-to-imdb-enhanced
pip install -r requirements.txt
```

说明：

- 当前依赖见 `requirements.txt`
- 项目使用 `selenium==3.141.0`，需要搭配 `urllib3<2`

## 配置文件

当前代码通过 `config.yaml` 读取本地配置。

先复制示例配置：

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

然后按自己的环境修改 `config.yaml`：

```yaml
DOUBAN_COOKIES:
  bid: "your_bid"
  dbcl2: "your_dbcl2"
  ck: "your_ck"

user_id: "your_douban_user_id"
start_page: 0
START_DATE: "20240101"
MOVIE_CSV_FILE: "movie.csv"
MISSING_IMDB_CSV_FILE: "missing_imdb.csv"
CHROMEDRIVER_PATH: "E:\\chromedriver\\chromedriver-win64\\chromedriver.exe"
```

各字段含义：

- `DOUBAN_COOKIES`：豆瓣登录 Cookie，用于稳定抓取
- `user_id`：豆瓣用户 ID
- `start_page`：从第几页开始抓取，第一页填 `0`
- `START_DATE`：抓取截止条件，格式为 `yyyymmdd`
- `MOVIE_CSV_FILE`：导出的主 CSV 文件名
- `MISSING_IMDB_CSV_FILE`：缺失 IMDb ID 的记录文件名
- `CHROMEDRIVER_PATH`：本机 `chromedriver.exe` 路径；如果 `chromedriver` 已加入系统 `PATH`，也可以不配置这一项

## 隐私与公开仓库

下面这些文件默认只建议保留在本地：

- `config.yaml`
- `movie.csv`
- `missing_imdb.csv`

当前仓库的 `.gitignore` 已忽略这些文件；公开仓库时应提交 `config.example.yaml`，不要提交真实配置和真实数据。

## 第一步：导出豆瓣评分

### 运行方式

使用 `config.yaml` 中的默认配置：

```powershell
python .\douban_to_csv.py
```

命令行覆盖参数：

```powershell
python .\douban_to_csv.py <user_id> [yyyymmdd] [start_page]
```

示例：

```powershell
python .\douban_to_csv.py 172989509 20240101 17
```

运行中的终端示例：

![douban_to_csv terminal demo](figure/douban2csv_runing_terminal.png)

### 参数说明

- `user_id`：不传时使用 `config.yaml` 中的 `user_id`
- `yyyymmdd`：不传时使用 `config.yaml` 中的 `START_DATE`
- `start_page`：不传时使用 `config.yaml` 中的 `start_page`

### `START_DATE` 的行为

`START_DATE` 的格式是 `yyyymmdd`，例如：

```text
20240101
```

脚本行为是：

- 只继续处理评分日期大于 `START_DATE` 的记录
- 一旦遇到评分日期小于或等于 `START_DATE` 的条目，就停止继续向后翻页

### 导出逻辑

当前 `douban_to_csv.py` 的行为和 README 旧版本相比有几处关键差异：

- 所有配置从 `config.yaml` 读取，不再直接改脚本里的默认值
- `movie.csv` 中已存在的 `douban_link` 会被自动跳过
- 缺失或无效的 IMDb ID 会写入 `missing_imdb.csv`
- 两个 CSV 都是边抓边写，每条写入后都会 `flush` 和 `fsync`
- 如果条目没有链接、标题或有效日期，会直接跳过

### 输出文件

`movie.csv`：

- 存放已拿到有效 IMDb ID 的记录
- 每行格式大致为：`标题, 豆瓣星级, imdb_id, douban_link`

![movie.csv sample](figure/moviecsv.png)

`missing_imdb.csv`：

- 存放没有 IMDb ID 或 IMDb ID 无效的记录
- 只在自身文件内部做去重，不影响 `movie.csv` 的去重判断

![missing_imdb.csv sample](figure/missingcsv.png)

## 第二步：同步 IMDb 评分

### 运行前确认

运行 `csv_to_imdb.py` 前，请确认：

1. 已先运行过 `douban_to_csv.py`
2. `MOVIE_CSV_FILE` 对应的 CSV 已生成
3. Chrome 已安装
4. ChromeDriver 与本机 Chrome 版本匹配
5. `CHROMEDRIVER_PATH` 可用，或者 `chromedriver` 已在系统 `PATH` 中

### ChromeDriver 说明

当前代码支持两种方式启动 ChromeDriver：

- 在 `config.yaml` 中配置 `CHROMEDRIVER_PATH`
- 不配置路径，直接依赖系统环境变量里的 `chromedriver`

### 登录流程

脚本会：

1. 打开 IMDb 登录页
2. 等你在浏览器里手动完成登录
3. 自动检测是否已经成功登录
4. 跳回 IMDb 首页并确认搜索框可用
5. 开始逐条同步评分


建议使用：

- `Sign in with IMDb`

不建议使用：

- `Sign in with Google`

原因是 Selenium 打开的自动化浏览器里，Google 登录更容易触发额外安全校验。

### 命令格式

默认导入评分：

```powershell
python .\csv_to_imdb.py
```

删除 IMDb 上已存在的评分：

```powershell
python .\csv_to_imdb.py unmark
```

自定义评分偏移：

```powershell
python .\csv_to_imdb.py -2
python .\csv_to_imdb.py -1
python .\csv_to_imdb.py 0
python .\csv_to_imdb.py 1
python .\csv_to_imdb.py 2
```

IMDb 自动化打分时的终端示例：

![IMDb sync terminal demo](figure/imdb_runing_terminal.png)

说明：

- 允许的偏移范围只有 `-2` 到 `2`
- 默认偏移值是 `-1`
- 脚本运行过程中，你可以继续用电脑做其他事情，包括 IMDb 自动化打分阶段
- 一般不需要一直盯着浏览器窗口；为了更稳，尽量不要手动操作正在被自动化控制的 IMDb 窗口

### 评分换算

脚本按下面的规则换算 IMDb 分数：

```text
IMDb 评分 = 豆瓣星级 * 2 + 调整值
```

默认参数下：

- 豆瓣 5 星 -> IMDb 9 分
- 豆瓣 1 星 -> IMDb 1 分

### 同步后的 CSV 变化

导入成功后，脚本会回写 `movie.csv`：

- 如果某条记录原本只有 4 列，会追加第 5 列标记 `1`
- 如果已经有第 5 列，会更新为 `1`

这个标记表示该条记录已经成功执行过一次评分写入。

## 常见问题

### 为什么一定要先运行 `douban_to_csv.py`？

因为 `csv_to_imdb.py` 读取的是本地生成的 `MOVIE_CSV_FILE`。没有这个文件，第二步就没有输入数据。

### 抓取中断后为什么可以继续？

因为导出脚本是边抓边写的：

- 每处理一条就立刻写入 CSV
- 已写入 `movie.csv` 的 `douban_link` 下次会被跳过

所以中断后重新运行时，不需要从头开始。

### 为什么有些条目没有进入 `movie.csv`？

常见原因有：

- 豆瓣条目页没有 IMDb ID
- 豆瓣页面访问受限
- 解析到的 IMDb ID 格式无效
- 条目缺少标题、链接或有效评分日期

这类记录会被跳过，或写入 `missing_imdb.csv`。

### `missing_imdb.csv` 会影响 `movie.csv` 去重吗？

不会。

当前逻辑是：

- `movie.csv` 只根据 `movie.csv` 自己判断重复
- `missing_imdb.csv` 只根据 `missing_imdb.csv` 自己判断重复

两者互不影响。

### 如果我因为被检测而重跑，怎么更快恢复？

可以一起利用两种方式：

- 保留已经生成的 `movie.csv`
- 调整 `start_page`，从更后面的分页继续抓

这样既能依赖已有 CSV 自动跳过，也能减少前面页面的重复访问。

## 可选后续步骤

如果你想把 IMDb 的记录继续导入 Trakt，可以再看：

- [TraktRater](https://github.com/damienhaynes/TraktRater/releases)

## 致谢

- 当前仓库代码基于 [f-is-h/douban-to-imdb](https://github.com/f-is-h/douban-to-imdb)
- 豆瓣导出逻辑参考了 [douban-exporter-lite](https://github.com/IvanWoo/douban-exporter-lite)
- Trakt 导入部分可参考 [TraktRater](https://github.com/damienhaynes/TraktRater/releases)
