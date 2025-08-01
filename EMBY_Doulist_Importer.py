#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 豆列导入器 - 重构版本
使用统一的 utils.py API 接口
"""
import os
import csv
import logging
import re
from typing import List
from datetime import datetime
from configparser import ConfigParser
from utils import EmbyAPI, RSSHubAPI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('emby_importer.log'),
        logging.StreamHandler()
    ]
)

# 加载配置
config = ConfigParser()
with open('config.conf', encoding='utf-8') as f:
    config.read_file(f)

# 配置代理
use_proxy = config.getboolean('Proxy', 'use_proxy', fallback=False)
if use_proxy:
    os.environ['http_proxy'] = config.get('Proxy', 'http_proxy', fallback='http://127.0.0.1:7890')
    os.environ['https_proxy'] = config.get('Proxy', 'https_proxy', fallback='http://127.0.0.1:7890')
else:
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)

class DbMovie:
    """电影数据类"""
    def __init__(self, name, year, type):
        self.name = name
        self.year = year
        self.type = type

class DbMovieRss:
    """RSS电影数据类"""
    def __init__(self, title, movies: List[DbMovie]):
        self.title = title
        self.movies = movies

class Get_Detail:
    """豆列导入器主类"""
    
    def __init__(self):
        self.noexist = []
        self.dbmovies = {}
        
        # 从配置文件获取配置
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.rsshub_server = config.get('Server', 'rsshub_server')
        self.ignore_played = config.getboolean('Extra', 'ignore_played', fallback=False)
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        self.doulist_ids = config.get('Collection', 'doulist_ids').split(',')
        self.csv_file_path = config.get('Output', 'csv_file_path')
        self.csvout = config.getboolean('Output', 'csvout', fallback=False)
        
        # CSV文件由main.py统一管理，不需要在这里初始化
        
        # 从配置文件读取名称映射
        self.name_mapping = {}
        if config.has_section('NameMapping'):
            for key, value in config.items('NameMapping'):
                self.name_mapping[key] = value
            logging.info(f"📝 加载名称映射: {len(self.name_mapping)} 条规则")
        else:
            logging.info("📝 未找到名称映射配置，使用默认映射")
            # 默认映射作为后备
            self.name_mapping = {
                "7号房的礼物": "七号房的礼物",
            }
        
        # 初始化API客户端
        self.emby_api = EmbyAPI(
            emby_server=self.emby_server,
            emby_api_key=self.emby_api_key,
            emby_user_id=self.emby_user_id
        )
        self.rss_api = RSSHubAPI(rsshub_server=self.rsshub_server, name_mapping=self.name_mapping)
    

    def _write_to_csv(self, movie_name, movie_year, box_name):
        """写入CSV文件"""
        try:
            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=['importer', 'collection_name', 'movie_name', 'year', 'reason', 'timestamp'])
                writer.writerow({
                    'importer': 'doulist',
                    'collection_name': box_name,
                    'movie_name': movie_name,
                    'year': movie_year,
                    'reason': '未找到匹配的电影',
                    'timestamp': current_time
                })
                logging.info(f"📝 记录到CSV: {movie_name} ({movie_year})")
        except Exception as e:
            logging.error(f"❌ 写入CSV失败: {str(e)}")
    

    def clean_title(self, title: str) -> str:
        """清理标题"""
        # 移除多余的空白字符
        title = re.sub(r'\s+', ' ', title.strip())
        return title
    
    def search_emby_by_name_and_year(self, db_movie: DbMovie):
        """搜索Emby中的电影"""
        item_type = "Series" if db_movie.type == "tv" else "Movie"
        return self.emby_api.search_item_by_name(
            name=db_movie.name,
            item_type=item_type,
            year=db_movie.year,
            ignore_played=self.ignore_played
        )

    def create_collection(self, collection_name, emby_id):
        """创建合集"""
        return self.emby_api.create_collection(collection_name, emby_id)

    def add_movie_to_collection(self, emby_id, collection_id):
        """添加电影到合集"""
        return self.emby_api.add_item_to_collection(emby_id, collection_id)
    
    def check_collection_exists(self, collection_name):
        """检查合集是否存在"""
        collection = self.emby_api.check_collection_exists(collection_name)
        if collection:
            # 获取合集中的电影列表
            items = self.emby_api.get_collection_items(collection['Id'])
            return {
                'box_id': collection['Id'],
                'box_movies': items
            }
        return None

    def get_emby_box_movie(self, box_id):
        """获取合集电影列表"""
        return self.emby_api.get_collection_items(box_id)

    def clear_collection(self, collection_id):
        """清空合集"""
        return self.emby_api.clear_collection(collection_id)

    def replace_cover_image(self, box_id, image_url):
        """替换合集封面"""
        return self.emby_api.replace_collection_cover(box_id, image_url)
    
    def get_douban_doulist_rss(self, doulist_id):
        """获取豆瓣豆列RSS数据"""
        result = self.rss_api.get_douban_doulist_rss(doulist_id)
        if not result:
            return None
        
        # 转换为内部数据格式
        movies = []
        for movie_data in result['movies']:
            movies.append(DbMovie(
                name=movie_data['name'],
                year=movie_data['year'],
                type=movie_data['type']
            ))
        
        return DbMovieRss(result['title'], movies)

    def run(self):
        """运行导入器"""
        logging.info("🚀 开始运行豆列导入器")
        
        # 遍历豆列ID
        for doulist_id in self.doulist_ids:
            doulist_id = doulist_id.strip()
            if not doulist_id:
                continue
            
            logging.info(f"📡 处理豆列ID: {doulist_id}")
            
            # 获取豆列RSS数据
            self.dbmovies = self.get_douban_doulist_rss(doulist_id)
            if not self.dbmovies or not self.dbmovies.movies:
                logging.warning(f"⚠️ 未获取到豆列数据: {doulist_id}")
                continue
            
            box_name = self.dbmovies.title
            logging.info(f"📋 合集名称: {box_name}")
            logging.info(f"🎬 电影数量: {len(self.dbmovies.movies)}")
            
            # 检查合集是否存在
            emby_box = self.check_collection_exists(box_name)
            
            if emby_box:
                box_id = emby_box['box_id']
                logging.info(f"✅ 合集已存在: {box_name} (ID: {box_id})")
                
                # 检查是否需要清空合集
                if not emby_box['box_movies']:
                    logging.info(f"🗑️ 合集为空，准备重新添加电影...")
                else:
                    logging.info(f"📋 合集包含 {len(emby_box['box_movies'])} 部电影")
            else:
                logging.info(f"🔨 合集不存在，开始创建: {box_name}")
                
                # 找到第一部电影作为初始电影
                first_movie_data = None
                for db_movie in self.dbmovies.movies:
                    emby_data = self.search_emby_by_name_and_year(db_movie)
                    if emby_data:
                        first_movie_data = emby_data
                        break
                
                if not first_movie_data:
                    logging.error(f"❌ 创建合集失败，无法找到初始电影: {box_name}")
                    continue
                
                # 创建合集
                box_id = self.create_collection(box_name, first_movie_data["Id"])
                if not box_id:
                    logging.error(f"❌ 合集创建失败: {box_name}")
                    continue
                
                logging.info(f"✅ 合集创建成功: {box_name} (ID: {box_id})")
                
                # 设置合集封面
                image_url = f"{self.emby_server}/emby/Items/{first_movie_data['Id']}/Images/Primary?api_key={self.emby_api_key}"
                self.replace_cover_image(box_id, image_url)

                # 初始化合集电影列表
                emby_box = {'box_id': box_id, 'box_movies': []}
            
            # 添加电影到合集
            added_count = 0
            for db_movie in self.dbmovies.movies:
                movie_name = db_movie.name
                movie_year = db_movie.year
                
                # 检查电影是否已在合集中
                if movie_name in emby_box['box_movies']:
                    logging.info(f"✅ 电影已在合集中，跳过: {movie_name}")
                    continue
                
                # 检查是否已记录为不存在
                if movie_name in self.noexist:
                    logging.info(f"⚠️ 电影已记录为不存在，跳过: {movie_name}")
                    continue
                
                # 搜索Emby中的电影
                emby_data = self.search_emby_by_name_and_year(db_movie)
                if emby_data:
                    emby_id = emby_data["Id"]
                    # 添加到合集
                    if self.add_movie_to_collection(emby_id, box_id):
                        logging.info(f"✅ 成功添加电影到合集: {movie_name}")
                        emby_box['box_movies'].append(movie_name)  # 更新本地记录
                        added_count += 1
                    else:
                        logging.error(f"❌ 添加电影到合集失败: {movie_name}")
                else:
                    self.noexist.append(movie_name)
                    logging.warning(f"⚠️ 电影不存在于Emby中: {movie_name}")
                    
                    # 记录到CSV文件
                    if self.csvout:
                        self._write_to_csv(movie_name, movie_year, box_name)
            
            logging.info(f"🎯 合集更新完成: {box_name}, 新增 {added_count} 部电影")
        

        
        logging.info("✅ 豆列导入器运行完成")

if __name__ == "__main__":
    logging.info("执行单次任务")
    gd = Get_Detail()
    gd.run()
