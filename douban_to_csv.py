import os
import sys
import csv
import re
import requests
import yaml
from datetime import datetime
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/537.36 (KHTML, like Gecko) ' \
             'Chrome/47.0.2526.106 Safari/537.36 '
CONFIG_FILE = 'config.yaml'


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f'Config file not found: {config_path}. Copy config.example.yaml to config.yaml '
            f'and fill in your local values before running the script.'
        )

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    required_keys = [
        'DOUBAN_COOKIES',
        'user_id',
        'start_page',
        'START_DATE',
        'MOVIE_CSV_FILE',
        'MISSING_IMDB_CSV_FILE',
    ]
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise KeyError(f'Missing config keys: {", ".join(missing_keys)}')

    return config


CONFIG = load_config()
START_DATE = str(CONFIG['START_DATE'])
IS_OVER = False
MOVIE_CSV_FILE = CONFIG['MOVIE_CSV_FILE']
MISSING_IMDB_CSV_FILE = CONFIG['MISSING_IMDB_CSV_FILE']
DOUBAN_COOKIES = CONFIG['DOUBAN_COOKIES']
DEFAULT_USER_ID = str(CONFIG['user_id'])
DEFAULT_START_PAGE = int(CONFIG['start_page'])

session = requests.Session()
session.headers.update({
    'User-Agent': USER_AGENT
})
session.cookies.update(DOUBAN_COOKIES)

def get_rating(rating_class):
    """
    :param rating_class: string
    :return: int
    example: "rating1-t" => 1
                "rating2-t" => 2
    """
    return int(rating_class[6])


def get_imdb_id(url):
    r = session.get(url, headers={'User-Agent': USER_AGENT})
    soup = BeautifulSoup(r.text, 'lxml')
    info_area = soup.find(id='info')
    imdb_id = None
    try:
        if info_area:
            # 由于豆瓣页面更改，IMDB的ID处不再有链接更改查询方法
            for index in range(-1, -len(info_area.find_all('span')) + 1, -1):
                imdb_id = info_area.find_all('span')[index].next_sibling.strip()
                if imdb_id.startswith('tt'):
                    break
        else:
            print('请手动添加', url)
    except:
        print('无法获得IMDB编号的电影页面：', url)
    finally:
        return imdb_id if not imdb_id or imdb_id.startswith('tt') else None


def get_csv_path(file_name):
    return os.path.dirname(os.path.abspath(__file__)) + f'/{file_name}'


def read_existing_csv():
    file_name = get_csv_path(MOVIE_CSV_FILE)
    existing_links = set()
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 4:  # 确保行有足够的列
                    existing_links.add(row[3])  # douban_link在第4列
    return existing_links


def read_missing_imdb_csv():
    file_name = get_csv_path(MISSING_IMDB_CSV_FILE)
    existing_links = set()
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 4:
                    existing_links.add(row[3])
    return existing_links


def is_valid_imdb_id(imdb_id):
    return bool(re.fullmatch(r'tt\d{3,}', imdb_id or ''))


def persist_missing_imdb_record(writer, csv_file, record, missing_imdb_links):
    if record[3] in missing_imdb_links:
        print(f'Skip duplicate missing IMDb record: {record[0]} ({record[3]})')
        return False

    writer.writerow(record)
    csv_file.flush()
    os.fsync(csv_file.fileno())
    missing_imdb_links.add(record[3])
    print(f'Recorded missing IMDb id: {record[0]} ({record[3]})')
    return True


def persist_record(writer, csv_file, record, existing_links, missing_imdb_writer, missing_imdb_csv_file, missing_imdb_links):
    if not is_valid_imdb_id(record[2]):
        persist_missing_imdb_record(
            missing_imdb_writer,
            missing_imdb_csv_file,
            record,
            missing_imdb_links,
        )
        return False

    # Flush each row so interrupted runs can resume from the already-written CSV.
    writer.writerow(record)
    csv_file.flush()
    os.fsync(csv_file.fileno())
    existing_links.add(record[3])
    return True


def get_info(url, existing_links, writer, csv_file, missing_imdb_writer, missing_imdb_csv_file, missing_imdb_links):
    written_count = 0
    r = session.get(url, headers={'User-Agent': USER_AGENT})
    soup = BeautifulSoup(r.text, "lxml")
    movie_items = soup.find_all("div", {"class": "item"})
    if len(movie_items) > 0:
        for item in movie_items:
            # meta data
            link_tag = item.find("a", href=True)
            if link_tag is None:
                print('Skip item without douban link')
                continue
            douban_link = link_tag['href']
            
            # 如果链接已存在，跳过
            if douban_link in existing_links:
                print(f'跳过已存在的电影: {douban_link}')
                continue
                
            title_node = item.find("li", {"class": "title"})
            if title_node is None or title_node.em is None:
                print(f'Skip item without title: {douban_link}')
                continue
            title = title_node.em.text

            date_span = item.find("span", {"class": "date"})
            if date_span is None:
                print(f'Skip item without comment date: {title} ({douban_link})')
                continue

            rating = date_span.find_previous_siblings()
            if len(rating) > 0 and rating[0].has_attr('class') and len(rating[0]['class']) > 0:
                try:
                    rating = get_rating(rating[0]['class'][0])
                except (IndexError, ValueError):
                    rating = None
            else:
                rating = None

            comment = item.find("span", {"class": "comment"})
            if comment is not None:
                comment = comment.contents[0].strip()

            comment_date_text = date_span.get_text(" ", strip=True)
            comment_date_match = re.search(r'\d{4}-\d{2}-\d{2}', comment_date_text)
            if comment_date_match is None:
                print(f'Skip item with invalid comment date: {title} ({douban_link}) -> {comment_date_text}')
                continue
            comment_date = comment_date_match.group(0)

            if datetime.strptime(comment_date, '%Y-%m-%d') <= datetime.strptime(START_DATE, '%Y%m%d'):
                global IS_OVER
                IS_OVER = True
                break

            imdb = get_imdb_id(douban_link)
            if persist_record(
                writer,
                csv_file,
                [title, rating, imdb, douban_link],
                existing_links,
                missing_imdb_writer,
                missing_imdb_csv_file,
                missing_imdb_links,
            ):
                written_count += 1
    else:
        return 0

    return written_count


def get_max_index(user_id):
    url = f"https://movie.douban.com/people/{user_id}/collect"
    r = session.get(url, headers={'User-Agent': USER_AGENT})
    soup = BeautifulSoup(r.text, "lxml")

    paginator = soup.find("div", {"class": "paginator"})
    if paginator is not None:
        max_index = paginator.find_all("a")[-2].get_text()
    else:
        max_index = 1
    print(f'总共 {max_index} 页')
    return int(max_index)


def url_generator(user_id, start_page=0):
    max_index = get_max_index(user_id)
    for index in range(start_page * 15, max_index * 15, 15):
        yield f"https://movie.douban.com/people/{user_id}/collect" \
              f"?start={index}&sort=time&rating=all&filter=all&mode=grid"


def export_legacy_batch(user_id, start_page=0):
    return export(user_id, start_page)
    # 读取已存在的链接
    existing_links = read_existing_csv()
    
    urls = url_generator(user_id, start_page)
    info = []
    page_no = start_page + 1
    for url in urls:
        if IS_OVER:
            break
        print(f'开始处理第 {page_no} 页...')
        info.extend(get_info(url, existing_links))
        page_no += 1
    print(f'处理完成, 总共处理了 {len(info)} 部电影')
    
    file_name = os.path.dirname(os.path.abspath(__file__)) + '/movie.csv'
    
    # 总是使用追加模式写入
    with open(file_name, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerows(info)
    print('追加电影评分至：', file_name)


def export(user_id, start_page=0):
    global IS_OVER
    IS_OVER = False

    existing_links = read_existing_csv()
    missing_imdb_links = read_missing_imdb_csv()
    urls = url_generator(user_id, start_page)
    total_written = 0
    page_no = start_page + 1
    file_name = get_csv_path(MOVIE_CSV_FILE)
    missing_imdb_file_name = get_csv_path(MISSING_IMDB_CSV_FILE)

    with open(file_name, 'a', encoding='utf-8', newline='') as f, \
            open(missing_imdb_file_name, 'a', encoding='utf-8', newline='') as missing_imdb_file:
        writer = csv.writer(f, lineterminator='\n')
        missing_imdb_writer = csv.writer(missing_imdb_file, lineterminator='\n')
        for url in urls:
            if IS_OVER:
                break
            print(f'Processing page {page_no}...')
            total_written += get_info(
                url,
                existing_links,
                writer,
                f,
                missing_imdb_writer,
                missing_imdb_file,
                missing_imdb_links,
            )
            page_no += 1

    print(f'Export finished. Newly written records: {total_written}')
    print('CSV file:', file_name)
    print('Missing IMDb CSV file:', missing_imdb_file_name)


def check_user_exist(user_id):
    r = session.get(f'https://movie.douban.com/people/{user_id}/', headers={'User-Agent': USER_AGENT})
    soup = BeautifulSoup(r.text, 'lxml')
    if '页面不存在' in soup.title:
        return False
    else:
        return True


if __name__ == '__main__':
    user_id = DEFAULT_USER_ID
    start_page = DEFAULT_START_PAGE
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        if not check_user_exist(user_id):
            print('请输入正确的豆瓣ID')
            sys.exit()
    
    start_page = DEFAULT_START_PAGE
    if len(sys.argv) >= 3:
        START_DATE = sys.argv[2]
    if len(sys.argv) >= 4:
        try:
            start_page = int(sys.argv[3])
            if start_page < 0:
                print('起始页码不能小于0')
                sys.exit()
        except ValueError:
            print('起始页码必须是数字')
            sys.exit()
            
    print(f'开始抓取{START_DATE + "之后的" if START_DATE != "19000502" else "所有"}观影数据...')
    print(f'从第 {start_page + 1} 页开始抓取')
    export(user_id, start_page)
