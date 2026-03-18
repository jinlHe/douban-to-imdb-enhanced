# douban-to-imdb-enhanced

将豆瓣电影评分导出为 CSV，再自动导入 IMDb。

当前仓库使用名称 `douban-to-imdb-enhanced`，用于和原始项目区分。本文档中的说明以当前仓库代码为准。

本项目是在 `https://github.com/f-is-h/douban-to-imdb` 的基础上修改而来，针对当前实际使用流程补充了说明，并调整了部分导出逻辑。

这个项目的完整流程分为两步，而且顺序不能反：

1. 先运行 `douban_to_csv.py`
2. 再运行 `csv_to_imdb.py`

`douban_to_csv.py` 负责从豆瓣抓取评分并生成本地 CSV，`csv_to_imdb.py` 再读取这些 CSV，把评分同步到 IMDb。

## 适用场景

- 你原来的观影和评分记录主要在豆瓣
- 你希望把评分补到 IMDb
- 后续你可能还想把 IMDb 记录再导入 Trakt、Infuse 等工具

## 环境要求

- Windows
- Python 3.8 左右版本，推荐使用虚拟环境或 conda 环境
- Google Chrome 浏览器
- 与本机 Chrome 版本匹配的 `chromedriver.exe`

## 安装依赖

可以使用 `venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

也可以使用 conda：

```powershell
conda create -n douban-to-imdb-enhanced python=3.8 -y
conda activate douban-to-imdb-enhanced
pip install -r requirements.txt
```

注意：

- 请直接安装 `requirements.txt`，其中已经包含当前代码需要的依赖版本
- 如果你手动安装过依赖，请确保 `selenium==3.141.0` 搭配 `urllib3<2`

## 总体流程

1. 在 `douban_to_csv.py` 中完善 `DOUBAN_COOKIES`
2. 设置自己的 `user_id`、`START_DATE`，必要时设置 `start_page`
3. 运行 `python douban_to_csv.py`
4. 确认已经生成或更新 `movie.csv`
5. 在 `csv_to_imdb.py` 中设置 `chromedriver_path`
6. 确保本机已安装 Chrome，并且 `chromedriver.exe` 与 Chrome 版本匹配
7. 运行 `python csv_to_imdb.py`
8. 浏览器打开后，使用 IMDb 账号登录，不要使用 Google 登录方式

## 第一步：导出豆瓣评分

### 需要先配置的内容

#### 1. `DOUBAN_COOKIES`

`douban_to_csv.py` 中的 `DOUBAN_COOKIES` 需要替换成你自己的豆瓣 Cookie，否则程序无法稳定抓取。

这部分可以参考这篇文章：

- https://blog.csdn.net/zhuzuwei/article/details/80875703

网络上也有很多类似教程，搜索 “豆瓣 cookies 获取” 或 “浏览器开发者工具复制 cookie” 都能找到。

#### 2. `user_id`

你需要设置自己的豆瓣 `user_id`。可以直接修改 `douban_to_csv.py` 里的默认值，也可以在命令行里传入。

查找方式：

1. 登录豆瓣
2. 打开个人主页
3. 观察 URL，形如：

```text
https://www.douban.com/people/123456789/
```

其中这段数字或字符串就是你的 `user_id`。

#### 3. `START_DATE`

`START_DATE` 的格式为 `yyyymmdd`。

含义是：

- 只抓取评分日期大于这个日期的记录
- 一旦程序遇到评分日期小于或等于 `START_DATE` 的条目，就会停止继续往后抓

例如：

```python
START_DATE = '20240101'
```

表示只处理 `2024-01-01` 之后的记录。

#### 4. `start_page`

如果你在抓取过程中被豆瓣检测、程序中断、或者想从较后面的页重新开始，可以设置 `start_page` 来快速跳过前面的分页，减少重复请求。

这在“已经抓过一部分、现在要继续跑”的场景下很有用。

另外，当前代码本身也会根据已经写入的 `movie.csv` 自动跳过已存在的 `douban_link`，但手动设置 `start_page` 仍然可以明显减少前面分页的重复访问。

### 命令格式

```powershell
python .\douban_to_csv.py <user_id> [yyyymmdd] [start_page]
```

示例：

```powershell
python .\douban_to_csv.py 172989509 20240101 17
```

### 输出文件说明

运行 `douban_to_csv.py` 后，主要会生成或更新两个文件：

#### `movie.csv`

- 存放“已经拿到有效 IMDb 编号”的电影记录
- 只有形如 `tt0189192` 这样的 IMDb 编号才会写入
- 文件是边处理边写入、实时更新的，不是最后一次性写入
- 这样即使中途报错或被中断，已经抓到的数据也不会丢失

#### `missing_imdb.csv`

- 存放“没有 IMDb 编号”或 IMDb 编号无效的记录
- 这个文件仅用于记录哪些豆瓣条目没有有效 IMDb 编号
- 它本身不会参与 `movie.csv` 的重复判断
- 它只保证自己内部不重复写入相同的 `douban_link`

### 当前导出逻辑的特点

- 已经存在于 `movie.csv` 中的条目会被自动跳过
- `movie.csv` 是实时追加更新的
- 没有 IMDb 编号的数据会被单独写入 `missing_imdb.csv`
- 一些包含敏感内容的条目，或者豆瓣页面本身拿不到 IMDb 信息的条目，可能需要手动处理

## 第二步：导入 IMDb 评分

在运行 `csv_to_imdb.py` 之前，请先确认：

1. 你已经先运行过 `douban_to_csv.py`
2. 当前目录下已经有 `movie.csv`
3. 你的电脑已经安装 Google Chrome
4. 你已经根据自己的 Chrome 版本下载了匹配的 `chromedriver.exe`
5. 你已经在 `csv_to_imdb.py` 中把 `chromedriver_path` 改成自己的实际路径

### `chromedriver_path` 配置

当前代码里使用的是硬编码路径，你需要手动修改：

```python
chromedriver_path = r"E:\chromedriver\chromedriver-win64\chromedriver.exe"
```

请将它改成你自己的 `chromedriver.exe` 路径。

### 登录 IMDb 的注意事项

程序运行后会自动打开浏览器并跳到 IMDb 登录页。

请注意：

- 不要通过 Google 账号登录方式登录
- 不要使用“浏览器里的 Google 账号同步登录”那套方式
- 请直接使用 `IMDb` 账号登录

也就是说，登录时请选择：

- `Sign in with IMDb`

不要选：

- `Sign in with Google`

这是因为 Selenium 打开的自动化浏览器里，Google 登录经常会触发安全限制，导致无法正常继续。

当前脚本的登录流程是：

1. 打开 IMDb 登录页
2. 等你手动完成登录
3. 你回到终端按一次回车
4. 程序继续执行评分

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

### 评分换算规则

当前代码会把豆瓣评分换算为 IMDb 评分：

```text
IMDb评分 = 豆瓣星级 * 2 + 调整值
```

例如默认参数下：

- 豆瓣 5 星 -> IMDb 9 分
- 豆瓣 1 星 -> IMDb 1 分

默认调整值是 `-1`。

## 常见问题

### 1. 为什么一定要先运行 `douban_to_csv.py`？

因为 `csv_to_imdb.py` 读取的是本地生成的 `movie.csv`。没有这个文件，第二步就没有输入数据。

### 2. 为什么抓取中断后还能继续？

因为当前版本的 `douban_to_csv.py` 是边抓边写：

- 每处理一条就写入 `movie.csv`
- 已经写过的 `douban_link` 会在下次运行时被跳过

所以中断后重新运行时，不需要从头全部重来。

### 3. 为什么有些条目没有进入 `movie.csv`？

通常有几种原因：

- 豆瓣条目页里没有 IMDb 编号
- 页面访问受限
- 拿到的 IMDb 编号格式无效

这类条目现在会被单独记录到 `missing_imdb.csv`。

### 4. `missing_imdb.csv` 会影响 `movie.csv` 的去重吗？

不会。

当前逻辑是：

- `movie.csv` 只根据 `movie.csv` 自己判断是否重复
- `missing_imdb.csv` 只根据 `missing_imdb.csv` 自己判断是否重复

两者互不干扰。

### 5. 如果我因为被检测而重跑，怎么更快恢复？

可以同时利用两种方式：

- 保留已经写好的 `movie.csv`
- 调整 `start_page`，从更靠后的分页继续跑

这样既能依赖现有 CSV 自动跳过，又能减少无意义的分页请求。

## 可选的后续步骤

如果你想把 IMDb 的记录继续导入 Trakt，可以再看：

- [TraktRater](https://github.com/damienhaynes/TraktRater/releases)

它是一个 Windows 工具，可以继续把 IMDb 记录导入 Trakt。

## 致谢

- 当前仓库代码是在 [f-is-h/douban-to-imdb](https://github.com/f-is-h/douban-to-imdb) 的基础上修改而来，更符合当前实际使用情况
- 豆瓣导出逻辑参考了 [douban-exporter-lite](https://github.com/IvanWoo/douban-exporter-lite)
- Trakt 导入部分可参考 [TraktRater](https://github.com/damienhaynes/TraktRater/releases)
