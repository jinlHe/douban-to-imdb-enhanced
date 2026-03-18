import os
import sys
import time
import csv

import urllib3
import yaml
from selenium import webdriver
from selenium import __version__ as selenium_version
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options

CONFIG_FILE = 'config.yaml'


def get_project_path(file_name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)


def load_config():
    config_path = get_project_path(CONFIG_FILE)
    if not os.path.exists(config_path):
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


CONFIG = load_config()
MOVIE_CSV_FILE = CONFIG.get('MOVIE_CSV_FILE', 'movie.csv')
CHROMEDRIVER_PATH = CONFIG.get('CHROMEDRIVER_PATH')


def ensure_selenium_urllib3_compatibility():
    selenium_major = int(selenium_version.split('.', 1)[0])
    urllib3_major = int(urllib3.__version__.split('.', 1)[0])
    if selenium_major < 4 and urllib3_major >= 2:
        raise RuntimeError(
            f"Incompatible dependency versions: selenium {selenium_version} does not support "
            f"urllib3 {urllib3.__version__}. Run: pip install \"urllib3<2\""
        )

def get_chrome_driver():
    """获取配置好的Chrome浏览器实例"""
    ensure_selenium_urllib3_compatibility()
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    
    try:
        if CHROMEDRIVER_PATH:
            driver = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=options)
        else:
            driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"初始化Chrome浏览器失败：{str(e)}")
        print("请确保：")
        print("1. Chrome浏览器已安装")
        print("2. ChromeDriver版本与Chrome浏览器版本匹配")
        print("3. ChromeDriver路径正确")
        print("4. If you are using selenium 3.141.0, run: pip install \"urllib3<2\"")
        raise

def login():
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    driver.get('https://www.imdb.com/registration/signin')
    print('Please complete IMDb login in the opened browser window.')
    input('After you are fully logged in to IMDb, press Enter here to continue...')
    driver.get('https://www.imdb.com/')
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.ID, 'suggestion-search'))
    )
    print('IMDb login confirmed, continuing...')
    return driver
    driver.get('https://www.imdb.com/registration/signin')
    element = driver.find_element_by_id('signin-perks')
    driver.execute_script("arguments[0].setAttribute('style', 'color: red;font-size: larger; font-weight: 700;')",
                          element)
    driver.execute_script("arguments[0].innerText = '请登录自己的IMDB账号, 程序将等待至登录成功。'", element)
    current_url = driver.current_url
    while True:
        WebDriverWait(driver, 600).until(EC.url_changes(current_url))
        new_url = driver.current_url
        if new_url == 'https://www.imdb.com/?ref_=login':
            break
    print('IMDB登录成功')
    return driver


def mark(is_unmark=False, rating_ajust=-1):
    driver = login()
    success_marked = 0
    success_unmarked = 0
    can_not_found = []
    already_marked = []
    never_marked = []
    file_name = get_project_path(MOVIE_CSV_FILE)
    
    # 读取所有记录
    all_records = []
    with open(file_name, 'r', encoding='utf-8') as file:
        content = csv.reader(file, lineterminator='\n')
        for line in content:
            all_records.append(line)
    
    # 处理每条记录
    for line in all_records:
        # 如果只标记为看过并没有打过分则略过
        if not line[1]:
            continue
        movie_name = line[0]
        movie_rate = int(line[1]) * 2 + rating_ajust
        imdb_id = line[2]
        if not imdb_id or not imdb_id.startswith('tt'):
            can_not_found.append(movie_name)
            print('无法在IMDB上找到：', movie_name)
            continue

        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.ID, 'suggestion-search')))
        search_bar = driver.find_element_by_id('suggestion-search')
        search_bar.send_keys(imdb_id)
        search_bar.submit()
        time.sleep(3)
        try:
            if is_unmark:
                driver.find_element_by_xpath('//div[@data-testid="hero-rating-bar__user-rating__score"]')
            else:
                driver.find_element_by_xpath('//div[@data-testid="hero-rating-bar__user-rating"]')
        except NoSuchElementException:
            if is_unmark:
                never_marked.append(f'{movie_name}({imdb_id})')
                print(f'并没有在IMDB上打过分：{movie_name}({imdb_id})')
            else:
                already_marked.append(f'{movie_name}({imdb_id})')
                print(f'已经在IMDB上打过分：{movie_name}({imdb_id})')
        else:
            rate_btn_xpath = '//div[@data-testid="hero-rating-bar__user-rating"]/button'
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, rate_btn_xpath))
            )
            driver.find_element_by_xpath(rate_btn_xpath).click()

            if is_unmark:
                driver.find_element_by_xpath("//div[@class='ipc-starbar']/following-sibling::button[2]").click()
                print(f'电影删除打分成功：{movie_name}({imdb_id})')
                success_unmarked += 1
            else:
                from selenium.webdriver.common.action_chains import ActionChains
                # 新版IMDB页面如果不先将鼠标移动到相应星星处再点击则则点击无效
                star_ele_xpath = f'//button[@aria-label="Rate {movie_rate}"]'
                WebDriverWait(driver, 3).until(
                    EC.visibility_of_element_located((By.XPATH, star_ele_xpath))
                )
                star_ele = driver.find_element_by_xpath(star_ele_xpath)
                mark_action = ActionChains(driver).move_to_element(star_ele).click()
                mark_action.perform()
                confirm_rate_ele_xpath = "//div[@class='ipc-starbar']/following-sibling::button"
                driver.find_element_by_xpath(confirm_rate_ele_xpath).click()
                print(f'电影打分成功：{movie_name}({imdb_id}) → {movie_rate}★')
                success_marked += 1
                
                # 更新记录，添加成功标记
                if len(line) < 5:
                    line.append('1')  # 添加第五列
                else:
                    line[4] = '1'  # 更新第五列
            time.sleep(1)
    
    # 保存更新后的记录
    with open(file_name, 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerows(all_records)
    
    driver.close()

    print('***************************************************************************')
    if is_unmark:
        print(f'成功删除了 {success_unmarked} 部电影的打分')
        print(f'有 {len(can_not_found)} 部电影没能在IMDB上找到：', can_not_found)
        print(f'有 {len(never_marked)} 部电影并没有在IMDB上打过分：', never_marked)
    else:
        print(f'成功标记了 {success_marked} 部电影')
        print(f'有 {len(can_not_found)} 部电影没能在IMDB上找到：', can_not_found)
        print(f'有 {len(already_marked)} 部电影已经在IMDB上打过分：', already_marked)
    print('***************************************************************************')


if __name__ == '__main__':
    if not os.path.exists(get_project_path(MOVIE_CSV_FILE)):
        print('未能找到CSV文件，请先导出豆瓣评分，请参照：',
              'https://github.com/fisheepx/douban-to-imdb')
        sys.exit()
    if len(sys.argv) > 1 and sys.argv[1] == 'unmark':
        mark(True)
    elif len(sys.argv) > 1:
        if sys.argv[1] not in ['-2', '-1', '0', '1', '2']:
            print('分数调整范围不能超过±2分(默认 -1分)，请参照：',
                  'https://github.com/fisheepx/douban-to-imdb')
            sys.exit()
        else:
            mark(False, int(sys.argv[1]))
    else:
        mark()
