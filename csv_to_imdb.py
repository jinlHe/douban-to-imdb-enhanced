import os
import sys
import time
import csv
from shutil import get_terminal_size

import urllib3
import yaml
from selenium import webdriver
from selenium import __version__ as selenium_version
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
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
SEARCH_BOX_TIMEOUT = 12
TITLE_PAGE_TIMEOUT = 8
RATING_ACTION_TIMEOUT = 8
POST_ACTION_DELAY_SECONDS = 0.2
PAGE_LOAD_TIMEOUT = 20


def is_record_eligible(row):
    return len(row) >= 3 and len(row) > 1 and bool(row[1])


def has_douban_link(row):
    return len(row) >= 4 and row[3].startswith('http')


def get_sync_flag_index(row):
    if len(row) >= 5 and has_douban_link(row):
        return 4
    if len(row) >= 4 and not has_douban_link(row):
        return 3
    return None


def is_record_synced(row):
    sync_flag_index = get_sync_flag_index(row)
    return sync_flag_index is not None and row[sync_flag_index] == '1'


def mark_record_synced(row):
    sync_flag_index = get_sync_flag_index(row)
    if sync_flag_index is None:
        row.append('1')
    else:
        row[sync_flag_index] = '1'


def clear_record_synced(row):
    sync_flag_index = get_sync_flag_index(row)
    if sync_flag_index is not None:
        row[sync_flag_index] = ''


def persist_all_records(file_name, all_records):
    temp_file_name = f'{file_name}.tmp'
    with open(temp_file_name, 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerows(all_records)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_file_name, file_name)


def format_duration(seconds):
    if seconds is None:
        return '--:--'
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
    return f'{minutes:02d}:{seconds:02d}'


class ProgressTracker:
    def __init__(self, total_records, initial_done=0):
        self.total_records = total_records
        self.initial_done = initial_done
        self.done_count = initial_done
        self.remote_total = max(0, total_records - initial_done)
        self.remote_processed = 0
        self.changed_count = 0
        self.already_done_count = 0
        self.failed_count = 0
        self.eta_sample_count = 0
        self.eta_elapsed_seconds = 0.0
        self.last_render_length = 0

    def _eta_seconds(self):
        remaining_remote = max(0, self.remote_total - self.remote_processed)
        if remaining_remote == 0:
            return 0
        if self.eta_sample_count == 0 or self.remote_processed == 0:
            return None

        actionable_ratio = self.eta_sample_count / self.remote_processed
        average_actionable_seconds = self.eta_elapsed_seconds / self.eta_sample_count
        estimated_remaining_actionable = remaining_remote * actionable_ratio
        return average_actionable_seconds * estimated_remaining_actionable

    def _bar(self, width=24):
        if self.total_records <= 0:
            return '-' * width
        filled = int(width * self.done_count / self.total_records)
        filled = min(width, max(0, filled))
        return '#' * filled + '-' * (width - filled)

    def render(self):
        terminal_width = get_terminal_size((120, 20)).columns
        percent = 100.0 if self.total_records == 0 else (self.done_count / self.total_records) * 100
        line = (
            f'[{self._bar()}] {self.done_count}/{self.total_records} {percent:5.1f}% '
            f'| changed {self.changed_count} '
            f'| already {self.already_done_count} '
            f'| failed {self.failed_count} '
            f'| ETA {format_duration(self._eta_seconds())}'
        )
        if len(line) > terminal_width:
            line = line[:terminal_width - 3] + '...'
        padding = max(0, self.last_render_length - len(line))
        sys.stdout.write('\r' + line + ' ' * padding)
        sys.stdout.flush()
        self.last_render_length = len(line)

    def log(self, message):
        if self.last_render_length:
            sys.stdout.write('\r' + ' ' * self.last_render_length + '\r')
            sys.stdout.flush()
            self.last_render_length = 0
        print(message)
        self.render()

    def update(self, include_in_eta, elapsed_seconds, changed=False, already_done=False, failed=False):
        self.done_count += 1
        self.remote_processed += 1
        if include_in_eta:
            self.eta_sample_count += 1
            self.eta_elapsed_seconds += elapsed_seconds
        if changed:
            self.changed_count += 1
        if already_done:
            self.already_done_count += 1
        if failed:
            self.failed_count += 1
        self.render()

    def finish(self):
        self.render()
        if self.last_render_length:
            sys.stdout.write('\n')
            sys.stdout.flush()
            self.last_render_length = 0


def wait_for_search_box(driver, timeout=SEARCH_BOX_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, 'suggestion-search'))
    )


def safe_get(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        print(f'页面加载超时，停止继续等待并继续执行：{url}')
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


def safe_submit_search(driver, search_bar, imdb_id):
    try:
        search_bar.submit()
    except TimeoutException:
        print(f'IMDb搜索结果页加载超时，停止继续等待并继续执行：{imdb_id}')
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


def wait_for_title_page(driver, imdb_id, timeout=TITLE_PAGE_TIMEOUT):
    already_rated_xpath = '//div[@data-testid="hero-rating-bar__user-rating__score"]'
    rate_btn_xpath = '//div[@data-testid="hero-rating-bar__user-rating"]/button'
    result_link_xpath = f'//a[contains(@href, "/title/{imdb_id}/")]'

    def title_page_or_result_ready(d):
        if imdb_id in d.current_url:
            has_rating_bar = len(d.find_elements_by_xpath(already_rated_xpath)) > 0
            has_rate_btn = len(d.find_elements_by_xpath(rate_btn_xpath)) > 0
            if has_rating_bar or has_rate_btn:
                return True
        return len(d.find_elements_by_xpath(result_link_xpath)) > 0

    WebDriverWait(driver, timeout).until(title_page_or_result_ready)

    if imdb_id not in driver.current_url:
        result_links = driver.find_elements_by_xpath(result_link_xpath)
        if result_links:
            driver.execute_script("arguments[0].click();", result_links[0])
            WebDriverWait(driver, timeout).until(
                lambda d: imdb_id in d.current_url and (
                    len(d.find_elements_by_xpath(already_rated_xpath)) > 0
                    or len(d.find_elements_by_xpath(rate_btn_xpath)) > 0
                )
            )


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
    options.page_load_strategy = 'eager'
    
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
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(30)
    safe_get(driver, 'https://www.imdb.com/registration/signin')
    print('Please complete IMDb login in the opened browser window.')
    input('After you are fully logged in to IMDb, press Enter here to continue...')
    try:
        wait_for_search_box(driver, timeout=3)
    except TimeoutException:
        safe_get(driver, 'https://www.imdb.com/')
    wait_for_search_box(driver)
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

    eligible_records = [line for line in all_records if is_record_eligible(line)]
    initial_done = 0 if is_unmark else sum(1 for line in eligible_records if is_record_synced(line))
    tracker = ProgressTracker(len(eligible_records), initial_done=initial_done)
    tracker.render()

    # 处理每条记录
    for line in eligible_records:
        if not is_unmark and is_record_synced(line):
            continue

        movie_name = line[0]
        movie_rate = int(line[1]) * 2 + rating_ajust
        imdb_id = line[2]
        item_start = time.perf_counter()
        if not imdb_id or not imdb_id.startswith('tt'):
            can_not_found.append(movie_name)
            tracker.log(f'无法在IMDB上找到：{movie_name}')
            tracker.update(include_in_eta=False, elapsed_seconds=0.0, failed=True)
            continue

        search_bar = wait_for_search_box(driver)
        search_bar.clear()
        search_bar.send_keys(imdb_id)
        safe_submit_search(driver, search_bar, imdb_id)
        wait_for_title_page(driver, imdb_id)
        already_rated_xpath = '//div[@data-testid="hero-rating-bar__user-rating__score"]'
        already_rated = len(driver.find_elements_by_xpath(already_rated_xpath)) > 0
        if is_unmark and not already_rated:
            never_marked.append(f'{movie_name}({imdb_id})')
            tracker.log(f'并没有在IMDB上打过分：{movie_name}({imdb_id})')
            tracker.update(include_in_eta=False, elapsed_seconds=time.perf_counter() - item_start, already_done=True)
            continue

        if not is_unmark and already_rated:
            already_marked.append(f'{movie_name}({imdb_id})')
            mark_record_synced(line)
            persist_all_records(file_name, all_records)
            tracker.log(f'已经在IMDB上打过分，跳过并标记为已同步：{movie_name}({imdb_id})')
            tracker.update(include_in_eta=False, elapsed_seconds=time.perf_counter() - item_start, already_done=True)
            continue

        rate_btn_xpath = '//div[@data-testid="hero-rating-bar__user-rating"]/button'
        try:
            rate_button = WebDriverWait(driver, RATING_ACTION_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, rate_btn_xpath))
            )
        except TimeoutException:
            can_not_found.append(movie_name)
            tracker.log(f'无法定位IMDb打分按钮：{movie_name}({imdb_id})')
            tracker.update(include_in_eta=True, elapsed_seconds=time.perf_counter() - item_start, failed=True)
            continue

        try:
            driver.execute_script("arguments[0].click();", rate_button)

            if is_unmark:
                remove_rating_xpath = "//div[@class='ipc-starbar']/following-sibling::button[2]"
                remove_button = WebDriverWait(driver, RATING_ACTION_TIMEOUT).until(
                    EC.element_to_be_clickable((By.XPATH, remove_rating_xpath))
                )
                driver.execute_script("arguments[0].click();", remove_button)
                clear_record_synced(line)
                persist_all_records(file_name, all_records)
                tracker.log(f'电影删除打分成功：{movie_name}({imdb_id})')
                success_unmarked += 1
                tracker.update(
                    include_in_eta=True,
                    elapsed_seconds=time.perf_counter() - item_start,
                    changed=True,
                )
            else:
                star_ele_xpath = f'//button[@aria-label="Rate {movie_rate}"]'
                star_ele = WebDriverWait(driver, RATING_ACTION_TIMEOUT).until(
                    EC.visibility_of_element_located((By.XPATH, star_ele_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", star_ele)
                driver.execute_script("arguments[0].click();", star_ele)

                confirm_rate_ele_xpath = "//div[@class='ipc-starbar']/following-sibling::button"
                WebDriverWait(driver, RATING_ACTION_TIMEOUT).until(
                    lambda d: d.find_element_by_xpath(confirm_rate_ele_xpath).is_enabled()
                )
                confirm_button = driver.find_element_by_xpath(confirm_rate_ele_xpath)
                driver.execute_script("arguments[0].click();", confirm_button)
                tracker.log(f'电影打分成功：{movie_name}({imdb_id}) → {movie_rate}★')
                success_marked += 1
                mark_record_synced(line)
                persist_all_records(file_name, all_records)
                tracker.update(
                    include_in_eta=True,
                    elapsed_seconds=time.perf_counter() - item_start,
                    changed=True,
                )
        except Exception as exc:
            can_not_found.append(movie_name)
            tracker.log(f'处理IMDb打分弹窗失败：{movie_name}({imdb_id}) -> {type(exc).__name__}: {exc}')
            tracker.update(include_in_eta=True, elapsed_seconds=time.perf_counter() - item_start, failed=True)
            continue

        time.sleep(POST_ACTION_DELAY_SECONDS)

    tracker.finish()
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
