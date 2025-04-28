import os
import urllib.parse
from configparser import ConfigParser
import base64
import requests
import feedparser
import re
import csv
import time
import schedule
import logging
from typing import List
from datetime import datetime
from croniter import croniter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('emby_importer.log'),
        logging.StreamHandler()
    ]
)

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

# 获取定时配置
enable_schedule = config.getboolean('Schedule', 'enable_schedule', fallback=False)
schedule_interval = config.getint('Schedule', 'schedule_interval', fallback=60)
cron_expression = config.get('Schedule', 'cron', fallback='')

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
        # 获取配置项的值
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.rsshub_server = config.get('Server', 'rsshub_server')
        self.ignore_played = config.getboolean('Extra', 'ignore_played', fallback=False)
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        self.rss_ids = config.get('Collection', 'rss_ids').split(',')
        self.csv_file_path = config.get('Output', 'csv_file_path')  # 从配置文件中获取文件路径
        # self.csv_mode = config.get('Output', 'csv_mode')  # 从配置文件中获取文件模式
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36 Edg/101.0.1210.39"
        }

    def search_emby_by_name_and_year(self, db_movie: DbMovie):
        name = db_movie.name
        yearParam = f"&Years={db_movie.year}"
        includeItemTypes = "IncludeItemTypes=movie"
        ignore_played = ""
        emby_user_id = ""
        # 删除季信息
        if db_movie.type == "tv":
            yearParam = ''
            includeItemTypes = "IncludeItemTypes=Series"
        if self.ignore_played:
            # 不查询播放过的
            ignore_played = "&Filters=IsUnplayed"
            emby_user_id = f"Users/{self.emby_user_id}"
        url = f"{self.emby_server}/emby/{emby_user_id}/Items?api_key={self.emby_api_key}{ignore_played}&Recursive=true&{includeItemTypes}&SearchTerm={name}{yearParam}"
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200 and data.get('TotalRecordCount', 0) > 0:
            for item in data.get('Items', []):
                if item['Name'] == name:
                    return item
            return None
        else:
            return None

    def create_collection(self, collection_name, emby_id):
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/emby/Collections?IsLocked=false&Name={encoded_collection_name}&Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {
            "accept": "application/json"
        }
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            collection_id = response.json().get('Id')
            print(f"成功创建合集: {collection_id}")
            return collection_id
        else:
            print("创建合集失败.")
            return None

    def add_movie_to_collection(self, emby_id, collection_id):
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items?Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {"accept": "*/*"}
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return response.status_code == 204

    def check_collection_exists(self, collection_name) -> EmbyBox:
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&SearchTerm={encoded_collection_name}&api_key={self.emby_api_key}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if len(data["Items"]) > 0 and data["Items"][0]["Type"] == "BoxSet":
                emby_box_id = data["Items"][0]['Id']
                return EmbyBox(emby_box_id, self.get_emby_box_movie(emby_box_id))
        return EmbyBox(None, [])

    def get_emby_box_movie(self, box_id):
        url = f"{self.emby_server}/emby/Items?api_key={self.emby_api_key}&ParentId={box_id}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return [item["Name"] for item in data["Items"]]
        return []


    def get_collection_items(self, collection_id):
        url = f"{self.emby_server}/emby/Items"
        params = {
            "ParentId": collection_id,
            "Recursive": "false",
            "Limit": 999,
            "api_key": self.emby_api_key
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get("Items", [])

    def clear_collection(self, collection_id):
        items = self.get_collection_items(collection_id)
        if not items:
            print(f"集合 {collection_id} 中没有需要清空的项目")
            return
        item_ids = [item["Id"] for item in items]
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items/Delete"
        params = {
            "Ids": ",".join(item_ids),
            "api_key": self.emby_api_key
        }
        response = requests.post(url, params=params)
        response.raise_for_status()
        print(f"清空集合 {collection_id}，移除项目: {', '.join(item_ids)}")

    def replace_cover_image(self, box_id, image_url):
        response = requests.get(image_url)
        image_content = response.content
        base64_image = base64.b64encode(image_content).decode('utf-8')
        url = f'{self.emby_server}/emby/Items/{box_id}/Images/Primary?api_key={self.emby_api_key}'
        headers = {
            'Content-Type': 'image/jpeg'
        }
        response = requests.post(url, headers=headers, data=base64_image)
        if response.status_code == 204:
            print(f'成功更新合集封面 {box_id}.')
        else:
            print(f'合集封面更新失败 {box_id}.')
            
    def run(self):
        # 遍历 RSS ID 获取电影信息
        for rss_id in self.rss_ids:
            # 获取豆瓣 RSS 数据
            self.dbmovies = self.get_douban_rss(rss_id)
            if not self.dbmovies or not self.dbmovies.movies:
                print(f"RSS 数据获取失败或无有效电影: rss_id: {rss_id}")
                continue  # 跳过当前 RSS
            box_name = "✨" + self.dbmovies.title
            print(f'更新 {box_name} rss_id: {rss_id}')
            # 检查合集是否存在
            emby_box = self.check_collection_exists(box_name)
            box_id = emby_box.box_id if emby_box else None

            if box_id:
                # 如果合集存在，清空合集内容
                existing_items = self.get_collection_items(box_id)
                if existing_items:
                    print(f"集合 {box_id} 存在项目，开始清空...")
                    self.clear_collection(box_id)
                    print(f"集合 {box_id} 已被清空")
                    # 清空后重新获取合集的状态，确保清空成功
                    emby_box = self.get_collection_items(box_id)
                    if not emby_box or len(emby_box) == 0:
                        print(f"集合 {box_id} 清空成功，准备重新添加电影...")
                        # 清空合集后，更新封面图
                        first_movie_data = None
                        # 遍历电影列表，找到第一个有效的 Emby 数据
                        for db_movie in self.dbmovies.movies:
                            emby_data = self.search_emby_by_name_and_year(db_movie)
                            if emby_data:
                                first_movie_data = emby_data
                                break
                        if first_movie_data:
                            emby_id = first_movie_data["Id"]
                            image_url = f"{self.emby_server}/emby/Items/{emby_id}/Images/Primary?api_key={self.emby_api_key}"
                            self.replace_cover_image(box_id, image_url)
                    else:
                        print(f"集合 {box_id} 清空失败，跳过添加电影")
                        continue  # 跳过添加操作
                else:
                    print(f"集合 {box_id} 中没有需要清空的项目，直接添加电影...")
            else:
                # 如果合集不存在，尝试创建
                print(f"合集 {box_name} 不存在，开始创建...")
                first_movie_data = None
                # 遍历电影列表，找到第一个有效的 Emby 数据
                for db_movie in self.dbmovies.movies:
                    emby_data = self.search_emby_by_name_and_year(db_movie)
                    if emby_data:
                        first_movie_data = emby_data
                        break
                if not first_movie_data:
                    print(f"创建合集失败，无法找到初始电影数据，跳过 {box_name}")
                    continue  # 跳过当前 RSS
                emby_id = first_movie_data["Id"]
                box_id = self.create_collection(box_name, emby_id)
                if not box_id:
                    print(f"合集 {box_name} 创建失败，跳过")
                    continue
                print(f"合集 '{box_name}' 已创建成功，ID: {box_id}")
                
                # 创建合集后，立即更新封面图
                image_url = f"{self.emby_server}/emby/Items/{emby_id}/Images/Primary?api_key={self.emby_api_key}"
                self.replace_cover_image(box_id, image_url)



            # 将电影逐一加入合集
            for db_movie in self.dbmovies.movies:
                movie_name = db_movie.name
                movie_year = db_movie.year
                # 确保 emby_box 是有效对象并且含有 box_movies 属性
                if isinstance(emby_box, dict) and 'box_movies' in emby_box:
                    if movie_name in emby_box['box_movies']:
                        print(f"电影 '{movie_name}' 已在合集中，跳过")
                        continue
                emby_data = self.search_emby_by_name_and_year(db_movie)
                if movie_name in self.noexist:
                    print(f"电影 '{movie_name}' 不存在，跳过")
                    continue
                if emby_data:
                    emby_id = emby_data["Id"]
                    added_to_collection = self.add_movie_to_collection(emby_id, box_id)
                    if added_to_collection:
                        print(f"影视 '{movie_name}' 成功加入合集 '{box_name}'")
                    else:
                        print(f"影视 '{movie_name}' 加入合集 '{box_name}' 失败")
                else:
                    self.noexist.append(movie_name)
                    print(f"电影 '{movie_name}' 不存在于 Emby 中，记录为未找到")
                    
                    # 将未找到的电影记录到 CSV 文件
                    with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as file:
                        writer = csv.writer(file)
                        writer.writerow([movie_name, movie_year, box_name])

            print(f"更新完成: {box_name}")


    def get_douban_rss(self, rss_id):
        # 解析rss
        rss_url = f"{self.rsshub_server}/douban/movie/weekly/{rss_id}"
        # print(f"rss_url: {rss_url}")
        feed = feedparser.parse(rss_url)
        # 封装成对象
        movies = []
        for item in feed.entries:
            name = item.title
            # 豆瓣和TMDB的影片名有时候会不一样，导致明明库里有的却没有匹配上。
            name_mapping = {
                "7号房的礼物": "七号房的礼物"
            }
            name = name_mapping.get(name, name)
            type = item.type
            if type == 'book':
                continue
                # 删除季信息
            if type == "tv":
                name = re.sub(r" 第[一二三四五六七八九十\d]+季", "", name)

                
            movies.append(DbMovie(name, item.year, type))
        db_movie = DbMovieRss(feed.feed.title, movies)
        return db_movie

def run_scheduled_task():
    logging.info("开始执行定时任务")
    try:
        gd = Get_Detail()
        gd.run()
    except Exception as e:
        logging.error(f"执行任务时发生错误: {str(e)}")
    logging.info("定时任务执行完成")

def main():
    if enable_schedule:
        logging.info("启动守护模式")
        if cron_expression:
            logging.info(f"使用cron表达式: {cron_expression}")
            # 使用croniter计算下次运行时间
            cron = croniter(cron_expression, datetime.now())
            next_run = cron.get_next(datetime)
            logging.info(f"下次运行时间: {next_run}")
            
            while True:
                try:
                    now = datetime.now()
                    if now >= next_run:
                        run_scheduled_task()
                        next_run = cron.get_next(datetime)
                        logging.info(f"下次运行时间: {next_run}")
                    time.sleep(30)  # 每30秒检查一次
                except KeyboardInterrupt:
                    logging.info("收到退出信号，程序退出")
                    break
                except Exception as e:
                    logging.error(f"运行出错: {str(e)}")
                    time.sleep(60)  # 出错后等待1分钟再继续
        else:
            logging.info(f"使用固定间隔: {schedule_interval}分钟")
            schedule.every(schedule_interval).minutes.do(run_scheduled_task)
            
            # 立即执行一次
            run_scheduled_task()
            
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except KeyboardInterrupt:
                    logging.info("收到退出信号，程序退出")
                    break
                except Exception as e:
                    logging.error(f"运行出错: {str(e)}")
                    time.sleep(60)  # 出错后等待1分钟再继续
    else:
        logging.info("执行单次任务")
        gd = Get_Detail()
        gd.run()

if __name__ == "__main__":
    main()
