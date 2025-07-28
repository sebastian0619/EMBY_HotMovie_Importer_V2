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
        self.csvout = config.getboolean('Output', 'csvout', fallback=False)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36 Edg/101.0.1210.39"
        }
        
        # 添加缓存机制
        self._cache = {
            'movies': None,
            'series': None,
            'collections': None,
            'cache_time': None
        }
        self._cache_duration = 300  # 缓存5分钟

    def _is_cache_valid(self, cache_type):
        """检查缓存是否有效"""
        if self._cache[cache_type] is None:
            return False
        if self._cache['cache_time'] is None:
            return False
        
        current_time = time.time()
        return (current_time - self._cache['cache_time']) < self._cache_duration
    
    def _get_cached_data(self, cache_type):
        """获取缓存数据"""
        if self._is_cache_valid(cache_type):
            logging.info(f"📦 使用缓存数据: {cache_type}")
            return self._cache[cache_type]
        return None
    
    def _set_cached_data(self, cache_type, data):
        """设置缓存数据"""
        self._cache[cache_type] = data
        self._cache['cache_time'] = time.time()
        logging.info(f"💾 缓存数据已更新: {cache_type}")

    def _fetch_all_items_with_cache(self, item_type):
        """获取所有项目（带缓存）"""
        cache_key = 'movies' if item_type == 'movie' else 'series'
        
        # 检查缓存
        cached_data = self._get_cached_data(cache_key)
        if cached_data:
            return cached_data
        
        logging.info(f"🔄 缓存未命中，开始获取所有 {item_type} 数据...")
        
        # 获取新数据
        all_items = self._fetch_all_items(item_type)
        
        # 缓存数据
        self._set_cached_data(cache_key, all_items)
        
        return all_items
    
    def _fetch_all_items(self, item_type):
        """获取所有项目（实际网络请求）"""
        includeItemTypes = "IncludeItemTypes=movie" if item_type == 'movie' else "IncludeItemTypes=Series"
        ignore_played = ""
        emby_user_id = ""
        
        if self.ignore_played:
            ignore_played = "&Filters=IsUnplayed"
            emby_user_id = f"Users/{self.emby_user_id}"
        
        all_items = []
        start_index = 0
        limit = 1000
        
        while True:
            url = f"{self.emby_server}/emby/{emby_user_id}/Items?api_key={self.emby_api_key}{ignore_played}&Recursive=true&{includeItemTypes}&StartIndex={start_index}&Limit={limit}"
            logging.info(f"📡 获取 {item_type} 数据 (分页 {start_index//limit + 1}): {url}")
            
            try:
                response = requests.get(url, timeout=60)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('Items', [])
                    total_count = data.get('TotalRecordCount', 0)
                    current_count = len(items)
                    
                    logging.info(f"📈 分页 {start_index//limit + 1}: 获取到 {current_count} 个 {item_type}")
                    all_items.extend(items)
                    
                    if current_count < limit:
                        logging.info(f"✅ 已获取所有 {item_type} 数据，总共 {len(all_items)} 个")
                        break
                    
                    start_index += limit
                    if start_index >= total_count:
                        logging.info(f"✅ 已获取所有 {item_type} 数据，总共 {len(all_items)} 个")
                        break
                else:
                    logging.error(f"❌ 获取 {item_type} 数据失败: {response.status_code}")
                    break
                
                # 移除延迟，提升速度
                
            except Exception as e:
                logging.error(f"❌ 获取 {item_type} 数据异常: {str(e)}")
                break
        
        return all_items

    def search_emby_by_name_and_year_fallback(self, db_movie: DbMovie):
        """备用的电影搜索方法，使用缓存数据"""
        name = db_movie.name
        item_type = 'movie' if db_movie.type == 'movie' else 'series'
        
        logging.info(f"🔄 使用备用方法搜索: {name} (类型: {db_movie.type}, 年份: {db_movie.year})")
        
        try:
            # 使用缓存获取所有项目
            all_items = self._fetch_all_items_with_cache(item_type)
            
            if not all_items:
                logging.warning(f"⚠️ 没有获取到任何 {item_type} 数据")
                return None
            
            logging.info(f"📈 在 {len(all_items)} 个 {item_type} 中搜索: {name}")
            
            # 在所有项目中查找匹配的名称
            for item in all_items:
                item_name = item.get('Name', '')
                item_year = item.get('ProductionYear')
                
                # 检查名称匹配
                if item_name == name:
                    # 如果指定了年份，也要检查年份
                    if db_movie.year and item_year:
                        if str(item_year) == str(db_movie.year):
                            logging.info(f"✅ 备用方法找到匹配项目: {item_name} (年份: {item_year}, ID: {item.get('Id', 'N/A')})")
                            return item
                    else:
                        # 没有指定年份，只匹配名称
                        logging.info(f"✅ 备用方法找到匹配项目: {item_name} (ID: {item.get('Id', 'N/A')})")
                        return item
            
            logging.info(f"ℹ️ 备用方法未找到匹配项目: {name}")
            return None
                
        except Exception as e:
            logging.error(f"❌ 备用搜索异常: {str(e)}")
            return None

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
        
        logging.info(f"🔍 搜索电影: {name} (类型: {db_movie.type}, 年份: {db_movie.year})")
        logging.info(f"📡 请求URL: {url}")
        
        # 添加重试机制
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logging.info(f"🔄 尝试第 {attempt + 1} 次请求...")
                response = requests.get(url, timeout=30)
                logging.info(f"📊 响应状态码: {response.status_code}")
                
                if response.status_code == 500 and "SQLitePCL.pretty.SQLiteException" in response.text:
                    logging.warning(f"⚠️ Emby 数据库异常，尝试重试 ({attempt + 1}/{max_retries}): {name}")
                    logging.warning(f"🔍 错误详情: {response.text[:500]}")
                    if attempt < max_retries - 1:
                        # 移除延迟，立即重试
                        continue
                    else:
                        logging.error(f"❌ Emby 数据库异常，已达到最大重试次数，使用备用搜索方法: {name}")
                        return self.search_emby_by_name_and_year_fallback(db_movie)
                
                if response.status_code != 200:
                    logging.error(f"❌ Emby API 请求失败: {response.status_code}")
                    logging.error(f"🔍 错误响应: {response.text[:500]}")
                    if attempt < max_retries - 1:
                        # 移除延迟，立即重试
                        continue
                    else:
                        return self.search_emby_by_name_and_year_fallback(db_movie)
                
                data = response.json()
                logging.info(f"📈 找到 {data.get('TotalRecordCount', 0)} 个匹配项目")
                
                if data.get('TotalRecordCount', 0) > 0:
                    for item in data.get('Items', []):
                        if item['Name'] == name:
                            logging.info(f"✅ 找到匹配电影: {item['Name']} (ID: {item.get('Id', 'N/A')})")
                            return item
                    logging.warning(f"⚠️ 未找到完全匹配的电影: {name}")
                    return None
                else:
                    logging.info(f"ℹ️ 未找到任何匹配的电影: {name}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logging.error(f"❌ Emby API 请求异常: {str(e)}")
                if attempt < max_retries - 1:
                    # 移除延迟，立即重试
                    continue
                else:
                    return self.search_emby_by_name_and_year_fallback(db_movie)
            except ValueError as e:
                logging.error(f"❌ Emby API 响应JSON解析失败: {str(e)}")
                logging.error(f"🔍 响应内容: {response.text[:500]}")
                if attempt < max_retries - 1:
                    # 移除延迟，立即重试
                    continue
                else:
                    return self.search_emby_by_name_and_year_fallback(db_movie)
        
        return None

    def create_collection(self, collection_name, emby_id):
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/emby/Collections?IsLocked=false&Name={encoded_collection_name}&Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {
            "accept": "application/json"
        }
        
        logging.info(f"🔨 创建合集: {collection_name}")
        logging.info(f"📡 请求URL: {url}")
        logging.info(f"🎬 初始电影ID: {emby_id}")
        
        try:
            response = requests.post(url, headers=headers, timeout=30)
            logging.info(f"📊 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                collection_id = response.json().get('Id')
                logging.info(f"✅ 成功创建合集: {collection_id}")
                print(f"成功创建合集: {collection_id}")
                return collection_id
            else:
                logging.error(f"❌ 创建合集失败: {response.status_code}")
                logging.error(f"🔍 错误响应: {response.text[:500]}")
                print(f"创建合集失败: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ 创建合集请求异常: {str(e)}")
            print(f"创建合集请求异常: {str(e)}")
            return None
        except ValueError as e:
            logging.error(f"❌ 创建合集响应JSON解析失败: {str(e)}")
            logging.error(f"🔍 响应内容: {response.text[:500]}")
            print(f"创建合集响应JSON解析失败: {str(e)} - 响应内容: {response.text[:200]}")
            return None

    def add_movie_to_collection(self, emby_id, collection_id):
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items?Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {"accept": "*/*"}
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return response.status_code == 204

    def check_collection_exists_fallback(self, collection_name) -> EmbyBox:
        """备用的合集检查方法，使用缓存数据"""
        try:
            logging.info(f"🔄 使用备用方法检查合集: {collection_name}")
            
            # 使用缓存获取所有合集
            all_collections = self._fetch_all_collections_with_cache()
            
            if not all_collections:
                logging.warning(f"⚠️ 没有获取到任何合集数据")
                return EmbyBox(None, [])
            
            logging.info(f"📈 在 {len(all_collections)} 个合集中搜索: {collection_name}")
            
            # 在返回的合集中查找匹配的名称
            for item in all_collections:
                item_name = item.get("Name", "")
                item_type = item.get("Type", "")
                logging.info(f"🔍 检查合集: {item_name} (类型: {item_type})")
                
                if item_name == collection_name and item_type == "BoxSet":
                    emby_box_id = item['Id']
                    logging.info(f"✅ 备用方法找到匹配合集: {item_name} (ID: {emby_box_id})")
                    return EmbyBox(emby_box_id, self.get_emby_box_movie(emby_box_id))
            
            # 如果没找到，返回空结果
            logging.info(f"ℹ️ 备用方法未找到匹配的合集: {collection_name}")
            return EmbyBox(None, [])
                
        except Exception as e:
            logging.error(f"❌ 备用合集检查异常: {str(e)}")
            return EmbyBox(None, [])
    
    def _fetch_all_collections_with_cache(self):
        """获取所有合集（带缓存）"""
        # 检查缓存
        cached_data = self._get_cached_data('collections')
        if cached_data:
            return cached_data
        
        logging.info(f"🔄 缓存未命中，开始获取所有合集数据...")
        
        # 获取新数据
        all_collections = self._fetch_all_collections()
        
        # 缓存数据
        self._set_cached_data('collections', all_collections)
        
        return all_collections
    
    def _fetch_all_collections(self):
        """获取所有合集（实际网络请求）"""
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&api_key={self.emby_api_key}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                collections = data.get('Items', [])
                logging.info(f"📈 获取到 {len(collections)} 个合集")
                return collections
            else:
                logging.error(f"❌ 获取合集失败: {response.status_code}")
                return []
        except Exception as e:
            logging.error(f"❌ 获取合集异常: {str(e)}")
            return []

    def check_collection_exists(self, collection_name) -> EmbyBox:
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&SearchTerm={encoded_collection_name}&api_key={self.emby_api_key}"
        
        logging.info(f"🔍 检查合集是否存在: {collection_name}")
        logging.info(f"📡 请求URL: {url}")
        
        # 添加重试机制
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logging.info(f"🔄 尝试第 {attempt + 1} 次检查合集...")
                response = requests.get(url, timeout=30)
                logging.info(f"📊 响应状态码: {response.status_code}")
                
                # 检查是否是 SQLite 异常
                if response.status_code == 500 and "SQLitePCL.pretty.SQLiteException" in response.text:
                    logging.warning(f"⚠️ Emby 数据库异常，尝试重试 ({attempt + 1}/{max_retries}): {collection_name}")
                    logging.warning(f"🔍 错误详情: {response.text[:500]}")
                    if attempt < max_retries - 1:
                        # 移除延迟，立即重试
                        continue
                    else:
                        logging.error(f"❌ Emby 数据库异常，已达到最大重试次数，使用备用方法: {collection_name}")
                        # 使用备用方法
                        return self.check_collection_exists_fallback(collection_name)
                
                if response.status_code == 200:
                    data = response.json()
                    logging.info(f"📈 找到 {len(data.get('Items', []))} 个合集")
                    
                    # 修复逻辑：检查所有返回的合集，而不是只看第一个
                    for item in data.get("Items", []):
                        item_name = item.get("Name", "")
                        item_type = item.get("Type", "")
                        logging.info(f"🔍 主方法检查合集: {item_name} (类型: {item_type})")
                        
                        if item_name == collection_name and item_type == "BoxSet":
                            emby_box_id = item['Id']
                            logging.info(f"✅ 主方法找到匹配合集: {item_name} (ID: {emby_box_id})")
                            return EmbyBox(emby_box_id, self.get_emby_box_movie(emby_box_id))
                    
                    # 如果没找到匹配的合集
                    logging.info(f"ℹ️ 主方法未找到匹配的合集: {collection_name}")
                    return EmbyBox(None, [])
                else:
                    logging.error(f"❌ 检查合集存在性失败: {response.status_code}")
                    logging.error(f"🔍 错误响应: {response.text[:500]}")
                    if attempt < max_retries - 1:
                        # 移除延迟，立即重试
                        continue
                    else:
                        # 使用备用方法
                        return self.check_collection_exists_fallback(collection_name)
                        
            except requests.exceptions.RequestException as e:
                logging.error(f"❌ 检查合集存在性请求异常: {str(e)}")
                if attempt < max_retries - 1:
                    # 移除延迟，立即重试
                    continue
                else:
                    # 使用备用方法
                    return self.check_collection_exists_fallback(collection_name)
            except ValueError as e:
                logging.error(f"❌ 检查合集存在性响应JSON解析失败: {str(e)}")
                logging.error(f"🔍 响应内容: {response.text[:500]}")
                if attempt < max_retries - 1:
                    # 移除延迟，立即重试
                    continue
                else:
                    # 使用备用方法
                    return self.check_collection_exists_fallback(collection_name)
        
        return EmbyBox(None, [])

    def get_emby_box_movie(self, box_id):
        url = f"{self.emby_server}/emby/Items?api_key={self.emby_api_key}&ParentId={box_id}"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return [item["Name"] for item in data["Items"]]
            else:
                logging.error(f"获取合集电影列表失败: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            logging.error(f"获取合集电影列表请求异常: {str(e)}")
        except ValueError as e:
            logging.error(f"获取合集电影列表响应JSON解析失败: {str(e)}")
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
            logging.info(f"🚀 开始处理 RSS: {rss_id}")
            
            # 先测试RSS连接
            if not self.test_rss_connection(rss_id):
                logging.error(f"❌ RSS连接测试失败，跳过处理: {rss_id}")
                continue
            # 获取豆瓣 RSS 数据
            self.dbmovies = self.get_douban_rss(rss_id)
            if not self.dbmovies or not self.dbmovies.movies:
                logging.error(f"❌ RSS 数据获取失败或无有效电影: rss_id: {rss_id}")
                continue  # 跳过当前 RSS
            box_name = "✨" + self.dbmovies.title
            logging.info(f"📺 更新合集: {box_name} (rss_id: {rss_id})")
            print(f'更新 {box_name} rss_id: {rss_id}')
            
            # 检查合集是否存在
            logging.info(f"🔍 检查合集是否存在: {box_name}")
            emby_box = self.check_collection_exists(box_name)
            box_id = emby_box.box_id if emby_box else None

            if box_id:
                logging.info(f"✅ 合集已存在，ID: {box_id}")
                # 如果合集存在，清空合集内容
                existing_items = self.get_collection_items(box_id)
                if existing_items:
                    logging.info(f"🗑️ 合集 {box_id} 存在 {len(existing_items)} 个项目，开始清空...")
                    print(f"集合 {box_id} 存在项目，开始清空...")
                    self.clear_collection(box_id)
                    print(f"集合 {box_id} 已被清空")
                    # 清空后重新获取合集的状态，确保清空成功
                    emby_box = self.get_collection_items(box_id)
                    if not emby_box or len(emby_box) == 0:
                        logging.info(f"✅ 合集 {box_id} 清空成功，准备重新添加电影...")
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
                        logging.error(f"❌ 合集 {box_id} 清空失败，跳过添加电影")
                        print(f"集合 {box_id} 清空失败，跳过添加电影")
                        continue  # 跳过添加操作
                else:
                    logging.info(f"ℹ️ 合集 {box_id} 中没有需要清空的项目，直接添加电影...")
                    print(f"集合 {box_id} 中没有需要清空的项目，直接添加电影...")
            else:
                # 如果合集不存在，尝试创建
                logging.info(f"🔨 合集 {box_name} 不存在，开始创建...")
                print(f"合集 {box_name} 不存在，开始创建...")
                first_movie_data = None
                # 遍历电影列表，找到第一个有效的 Emby 数据
                for db_movie in self.dbmovies.movies:
                    emby_data = self.search_emby_by_name_and_year(db_movie)
                    if emby_data:
                        first_movie_data = emby_data
                        break
                if not first_movie_data:
                    logging.error(f"❌ 创建合集失败，无法找到初始电影数据，跳过 {box_name}")
                    print(f"创建合集失败，无法找到初始电影数据，跳过 {box_name}")
                    continue  # 跳过当前 RSS
                emby_id = first_movie_data["Id"]
                box_id = self.create_collection(box_name, emby_id)
                if not box_id:
                    logging.error(f"❌ 合集 {box_name} 创建失败，跳过")
                    print(f"合集 {box_name} 创建失败，跳过")
                    continue
                logging.info(f"✅ 合集 '{box_name}' 已创建成功，ID: {box_id}")
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
                    if self.csvout:
                        with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as file:
                            writer = csv.writer(file)
                            writer.writerow([movie_name, movie_year, box_name])
                
                # 移除延迟，提升速度

            print(f"更新完成: {box_name}")


    def get_douban_rss(self, rss_id):
        # 解析rss
        rss_url = f"{self.rsshub_server}/douban/movie/weekly/{rss_id}"
        logging.info(f"正在获取RSS数据: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                logging.error(f"RSS数据为空或解析失败: {rss_url}")
                return None
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
            logging.info(f"成功获取RSS数据，共{len(movies)}部电影")
            return db_movie
        except Exception as e:
            logging.error(f"获取RSS数据失败: {str(e)} - URL: {rss_url}")
            return None

    def test_rss_connection(self, rss_id):
        """测试RSS连接是否正常"""
        rss_url = f"{self.rsshub_server}/douban/movie/weekly/{rss_id}"
        logging.info(f"测试RSS连接: {rss_url}")
        try:
            response = requests.get(rss_url, timeout=30)
            logging.info(f"RSS响应状态码: {response.status_code}")
            logging.info(f"RSS响应内容前200字符: {response.text[:200]}")
            if response.status_code == 200:
                feed = feedparser.parse(rss_url)
                if feed.entries:
                    logging.info(f"RSS解析成功，找到{len(feed.entries)}个条目")
                    return True
                else:
                    logging.error("RSS解析成功但无条目")
                    return False
            else:
                logging.error(f"RSS请求失败: {response.status_code}")
                return False
        except Exception as e:
            logging.error(f"RSS连接测试失败: {str(e)}")
            return False

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
        # 启动时立即执行一次
        logging.info("程序启动，立即执行一次任务")
        run_scheduled_task()
        
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
                    time.sleep(5)  # 减少检查间隔，提升响应速度
                except KeyboardInterrupt:
                    logging.info("收到退出信号，程序退出")
                    break
                except Exception as e:
                    logging.error(f"运行出错: {str(e)}")
                    time.sleep(10)  # 减少错误恢复时间
        else:
            logging.info(f"使用固定间隔: {schedule_interval}分钟")
            schedule.every(schedule_interval).minutes.do(run_scheduled_task)
            
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except KeyboardInterrupt:
                    logging.info("收到退出信号，程序退出")
                    break
                except Exception as e:
                    logging.error(f"运行出错: {str(e)}")
                    time.sleep(10)  # 减少错误恢复时间
    else:
        logging.info("执行单次任务")
        gd = Get_Detail()
        gd.run()

if __name__ == "__main__":
    main()
