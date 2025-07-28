import os
import urllib.parse
from configparser import ConfigParser
import base64
import requests
import feedparser
import re
from typing import List
import sys
import csv
import io
import time
from datetime import datetime

print("开始获取RSS条目.....")
# 强制设置标准输出和标准错误为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
config = ConfigParser()

with open('config.conf', encoding='utf-8') as f:
    config.read_file(f)
use_proxy = config.getboolean('Proxy', 'use_proxy', fallback=False)
if use_proxy:
    os.environ['http_proxy'] = config.get('Proxy', 'http_proxy', fallback='http://127.0.0.1:7890')
    os.environ['https_proxy'] = config.get('Proxy', 'https_proxy', fallback='http://127.0.0.1:7890')
else:
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)

class DbMovie:
    def __init__(self, name, year, type):
        self.name = name
        self.year = year
        self.type = type

class DbMovieRss:
    def __init__(self, title, movies: List[DbMovie]):
        self.title = title
        self.movies = movies

class EmbyBox:
    def __init__(self, box_id, box_movies):
        self.box_id = box_id
        self.box_movies = box_movies

class Get_Detail(object):
    def __init__(self):
        self.noexist = []
        self.dbmovies = {}
        self.collection_id = ""
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.rsshub_server = config.get('Server', 'rsshub_server')
        self.ignore_played = config.getboolean('Extra', 'ignore_played', fallback=False)
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        self.rss_ids = config.get('Collection', 'doulist_ids').split(',')
        self.csvout = config.getboolean('Output', 'csvout', fallback=False)
        self.csv_file_path = config.get('Output', 'csv_file_path')
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36 Edg/101.0.1210.39"
        }

    def clean_title(self, title: str) -> str:
        special_chars = r'[【】·｜。▧~➠❍★❶*+?!@#$%^&()\[\]{}\\|<>,;:\'"`]'
        cleaned_title = re.sub(special_chars, '', title)
        cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
        result = cleaned_title if cleaned_title else "默认合集"
        return result

    def search_emby_by_name_and_year(self, db_movie: DbMovie):
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 搜索 Emby 媒体: name={db_movie.name}, year={db_movie.year}, type={db_movie.type}")
        name = db_movie.name
        year = db_movie.year
        media_type = db_movie.type

        # 校验 name 是否有效
        if not name or name.strip() == '':
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: 电影名称为空，跳过搜索")
            return None

        includeItemTypes = "IncludeItemTypes=movie" if media_type == "movie" else "IncludeItemTypes=Series"
        ignore_played = ""
        emby_user_id = ""
        if self.ignore_played:
            ignore_played = "&Filters=IsUnplayed"
            emby_user_id = f"Users/{self.emby_user_id}"

        # 编码搜索名称以处理特殊字符
        encoded_name = urllib.parse.quote(name, safe='')
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 编码后的搜索名称: {encoded_name}")
        
        # 优先尝试无年份搜索
        url = f"{self.emby_server}/emby/{emby_user_id}/Items?api_key={self.emby_api_key}{ignore_played}&Recursive=true&{includeItemTypes}&SearchTerm={encoded_name}"
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 搜索 Emby（无年份）: URL={url}")
        response = requests.get(url, headers=self.headers)
        
        if response.status_code != 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Emby API 请求失败: status_code={response.status_code}, URL={url}")
            return None
        
        data = response.json()
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Emby API 响应: TotalRecordCount={data.get('TotalRecordCount', 0)}")
        if response.status_code == 200 and data.get('TotalRecordCount', 0) > 0:
            for item in data.get('Items', []):
                item_name = item['Name']
                item_id = item['Id']
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查 Emby 媒体: item_name={item_name}, item_id={item_id}, search_name={name}")
                if item_name == name or name.lower() in item_name.lower():
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到匹配: item_name={item_name}, item_id={item_id}")
                    return item

        # 如果无年份搜索失败，且有年份数据，尝试年份范围搜索（±1年）
        if year:
            year_range = ",".join(str(y) for y in range(int(year) - 1, int(year) + 2))
            url = f"{self.emby_server}/emby/{emby_user_id}/Items?api_key={self.emby_api_key}{ignore_played}&Recursive=true&{includeItemTypes}&SearchTerm={encoded_name}&Years={year_range}"
            
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Emby API 请求失败: status_code={response.status_code}, URL={url}")
                return None
            
            data = response.json()
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Emby API 响应: TotalRecordCount={data.get('TotalRecordCount', 0)}")
            if response.status_code == 200 and data.get('TotalRecordCount', 0) > 0:
                for item in data.get('Items', []):
                    item_name = item['Name']
                    item_id = item['Id']
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查 Emby 媒体: item_name={item_name}, item_id={item_id}, search_name={name}")
                    if item_name == name or name.lower() in item_name.lower():
                        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到匹配: item_name={item_name}, item_id={item_id}")
                        return item
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Emby 搜索无结果: name={name}, year={year}, type={media_type}")
        return None

    def create_collection(self, collection_name, emby_id):
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 创建合集: name={collection_name}, initial_movie_id={emby_id}")
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/emby/Collections?IsLocked=false&Name={encoded_collection_name}&Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {
            "accept": "application/json"
        }
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送创建合集请求: URL={url}")
        response = requests.post(url, headers=headers)
        
        if response.status_code == 200:
            collection_id = response.json().get('Id')
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功创建合集: collection_id={collection_id}")
            return collection_id
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 创建合集失败: status_code={response.status_code}, response={response.text}")
            return None

    def add_movie_to_collection(self, emby_id, collection_id):
        # print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 添加电影到合集: movie_id={emby_id}, collection_id={collection_id}")
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items?Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {"accept": "*/*"}
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送添加电影请求: URL={url}")
        response = requests.post(url, headers=headers)
        
        if response.status_code == 204:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 电影添加成功: movie_id={emby_id}, collection_id={collection_id}")
            # input(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 按 Enter 继续添加下一部电影...")
            return True
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 电影添加失败: movie_id={emby_id}, collection_id={collection_id}, status_code={response.status_code}")
            return False

    def check_collection_exists(self, collection_name) -> EmbyBox:
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查合集是否存在: name={collection_name}")
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&SearchTerm={encoded_collection_name}&api_key={self.emby_api_key}"
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送检查合集请求: URL={url}")
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查合集响应: TotalRecordCount={data.get('TotalRecordCount', 0)}")
            if len(data["Items"]) > 0 and data["Items"][0]["Type"] == "BoxSet":
                emby_box_id = data["Items"][0]['Id']
                box_movies = self.get_emby_box_movie(emby_box_id)
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集存在: box_id={emby_box_id}, movies={box_movies}")
                return EmbyBox(emby_box_id, box_movies)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集不存在: name={collection_name}")
        return EmbyBox(None, [])

    def get_emby_box_movie(self, box_id):
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取合集电影列表: box_id={box_id}")
        url = f"{self.emby_server}/emby/Items?api_key={self.emby_api_key}&ParentId={box_id}"
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送获取合集电影请求: URL={url}")
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            movies = [item["Name"] for item in data["Items"]]
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取合集电影: box_id={box_id}, movies={movies}")
            return movies
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取合集电影失败: box_id={box_id}, status_code={response.status_code}")
        return []

    def get_collection_items(self, collection_id):
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取合集项目: collection_id={collection_id}")
        url = f"{self.emby_server}/emby/Items"
        params = {
            "ParentId": collection_id,
            "Recursive": "false",
            "Limit": 999,
            "api_key": self.emby_api_key
        }
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送获取合集项目请求: URL={url}, params={params}")
        response = requests.get(url, params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取合集项目: collection_id={collection_id}, item_count={len(items)}")
        return items

    def clear_collection(self, collection_id):
        # print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 清空合集: collection_id={collection_id}")
        items = self.get_collection_items(collection_id)
        if not items:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集无项目: collection_id={collection_id}")
            return
        item_ids = [item["Id"] for item in items]
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items/Delete"
        params = {
            "Ids": ",".join(item_ids),
            "api_key": self.emby_api_key
        }
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送清空合集请求: URL={url}, item_ids={item_ids}")
        response = requests.post(url, params=params)
        response.raise_for_status()
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 清空合集成功: collection_id={collection_id}, removed_items={item_ids}")

    def replace_cover_image(self, box_id, image_url):
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 更新合集封面: box_id={box_id}, image_url={image_url}")
        response = requests.get(image_url)
        image_content = response.content
        base64_image = base64.b64encode(image_content).decode('utf-8')
        url = f'{self.emby_server}/emby/Items/{box_id}/Images/Primary?api_key={self.emby_api_key}'
        headers = {
            'Content-Type': 'image/jpeg'
        }
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送更新封面请求: URL={url}")
        response = requests.post(url, headers=headers, data=base64_image)
        if response.status_code == 204:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功更新合集封面: box_id={box_id}")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 更新合集封面失败: box_id={box_id}, status_code={response.status_code}")

    def run(self):
        # print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始运行脚本，处理 RSS IDs: {self.rss_ids}")
        for rss_id in self.rss_ids:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 处理 RSS ID: {rss_id}")
            self.dbmovies = self.get_douban_rss(rss_id)
            if not self.dbmovies or not self.dbmovies.movies:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] RSS 数据获取失败或无有效电影: rss_id={rss_id}")
                continue
            
            cleaned_title = self.clean_title(self.dbmovies.title)
            box_name = "✨" + cleaned_title
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 更新合集: name={box_name}, rss_id={rss_id}")
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 当前 noexist 列表: {self.noexist}")
            
            emby_box = self.check_collection_exists(box_name)
            box_id = emby_box.box_id if emby_box else None
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集检查结果: box_id={box_id}, existing_movies={emby_box.box_movies}")

            if box_id:
                existing_items = self.get_collection_items(box_id)
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集现有项目: count={len(existing_items)}")
                if existing_items:
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集存在项目，开始清空: box_id={box_id}")
                    self.clear_collection(box_id)
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集已清空: box_id={box_id}")
                    emby_box = EmbyBox(box_id, self.get_emby_box_movie(box_id))
                    if not emby_box.box_movies:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集清空成功: box_id={box_id}")
                    else:
                        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集清空失败: box_id={box_id}, remaining_movies={emby_box.box_movies}")
                        continue
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集无项目，直接添加电影: box_id={box_id}")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集不存在，开始创建: name={box_name}")
                first_movie_data = None
                for db_movie in self.dbmovies.movies:
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 搜索初始电影: name={db_movie.name}, year={db_movie.year}")
                    emby_data = self.search_emby_by_name_and_year(db_movie)
                    if emby_data:
                        first_movie_data = emby_data
                        break
                if not first_movie_data:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 创建合集失败，无法找到初始电影: box_name={box_name}")
                    continue
                emby_id = first_movie_data["Id"]
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到初始电影: emby_id={emby_id}, name={first_movie_data['Name']}")
                box_id = self.create_collection(box_name, emby_id)
                if not box_id:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集创建失败: box_name={box_name}")
                    continue
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集创建成功: box_name={box_name}, box_id={box_id}")
                image_url = f"{self.emby_server}/emby/Items/{emby_id}/Images/Primary?api_key={self.emby_api_key}"
                self.replace_cover_image(box_id, image_url)

            # print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始添加电影到合集: box_name={box_name}, box_id={box_id}")
            for db_movie in self.dbmovies.movies:
                movie_name = db_movie.name
                movie_year = db_movie.year
                # print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 处理电影: name={movie_name}, year={movie_year}")
                if movie_name in emby_box.box_movies:
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 电影已存在于合集，跳过: name={movie_name}")
                    continue
                if movie_name in self.noexist:
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 电影已记录为不存在，跳过: name={movie_name}")
                    continue
                emby_data = self.search_emby_by_name_and_year(db_movie)
                if emby_data:
                    emby_id = emby_data["Id"]
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 Emby 媒体: emby_id={emby_id}, name={emby_data['Name']}")
                    added_to_collection = self.add_movie_to_collection(emby_id, box_id)
                    if added_to_collection:
                        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功加入合集: movie_name={movie_name}, emby_id={emby_id}, box_name={box_name}")
                        emby_box.box_movies.append(movie_name)  # 更新本地记录
                    else:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 加入合集失败: movie_name={movie_name}, emby_id={emby_id}, box_name={box_name}")
                else:
                    self.noexist.append(movie_name)
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 电影不存在于 Emby，记录为未找到: name={movie_name}")
                    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 当前 noexist 列表: {self.noexist}")
                    # 根据 csvout 开关决定是否将未找到的电影记录到 CSV 文件
                    if self.csvout:
                        with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as file:
                            writer = csv.writer(file)
                            writer.writerow([movie_name, movie_year, box_name])
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 合集更新完成: box_name={box_name}, box_id={box_id}")
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 当前合集电影: {self.get_emby_box_movie(box_id)}")

    def get_douban_rss(self, rss_id):
        # print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取 Douban RSS: rss_id={rss_id}")
        rss_url = f"{self.rsshub_server}/douban/doulist/{rss_id}"
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] RSS URL: {rss_url}")
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 无法解析 RSS 数据或数据为空: {rss_url}")
            return None

        movies = []
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 解析 RSS 条目: count={len(feed.entries)}")
        for item in feed.entries:
            raw_title = item.title.strip() if item.title else ""
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 解析 RSS 条目: raw_title='{raw_title}', description='{item.description[:100]}...'")

            # 校验标题是否有效
            if not raw_title or re.match(r'^[\s\-—–]*$', raw_title):
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: 标题为空或无效，跳过: raw_title='{raw_title}'")
                continue

            name = raw_title
            # 提取简体名称（第一个非空格子串）
            simplified_name_match = re.match(r'([^\s]+)', name)
            if simplified_name_match:
                name = simplified_name_match.group(1)
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 提取简体名称: {name}")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 未提取简体名称，使用原始标题: {name}")

            name_mapping = {
                "7号房的礼物": "七号房的礼物",
            }
            name = name_mapping.get(name, name)
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 应用名称映射后: {name}")

            # 从 description 中提取年份和类型
            description = item.description
            year = None
            media_type = "movie"  # 默认电影
            year_match = re.search(r'年份:\s*(\d{4})', description)
            if year_match:
                year = year_match.group(1)
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 提取年份: {year}")

            type_match = re.search(r'类型:\s*([^<]+)', description)
            if type_match:
                types = type_match.group(1).strip()
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 提取类型: {types}")
                if "剧情" in types or "电影" in types or "爱情" in types or "同性" in types:
                    media_type = "movie"
                elif "电视剧" in types or "剧集" in types:
                    media_type = "tv"
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 确定媒体类型: {media_type}")

            if media_type == 'book':
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 跳过书籍: name={name}")
                continue
            if media_type == "tv":
                name = re.sub(r" 第[一二三四五六七八九十\d]+季", "", name)
                # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 去除季信息后: name={name}")

            movies.append(DbMovie(name, year, media_type))
            # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 添加电影到列表: name={name}, year={year}, type={media_type}")

        db_movie = DbMovieRss(feed.feed.title, movies)
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] RSS 解析完成: title={db_movie.title}, movie_count={len(db_movie.movies)}")
        return db_movie

if __name__ == "__main__":
    gd = Get_Detail()
    gd.run()
