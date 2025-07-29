#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby API 和 RSSHub 统一工具模块
整合所有导入器中的API调用方法
"""
import os
import urllib.parse
import requests
import feedparser
import base64
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from configparser import ConfigParser

class EmbyAPI:
    """Emby API 统一接口类"""
    
    def __init__(self, emby_server: str, emby_api_key: str, emby_user_id: str = None):
        self.emby_server = emby_server.rstrip('/')
        self.emby_api_key = emby_api_key
        self.emby_user_id = emby_user_id
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36"
        })
        
        # 缓存机制
        self._cache = {
            'movies': None,
            'series': None,
            'collections': None,
            'cache_time': None
        }
        self._cache_duration = 300  # 缓存5分钟
    
    def _is_cache_valid(self, cache_type: str) -> bool:
        """检查缓存是否有效"""
        if self._cache[cache_type] is None:
            return False
        if self._cache['cache_time'] is None:
            return False
        
        current_time = time.time()
        return (current_time - self._cache['cache_time']) < self._cache_duration
    
    def _get_cached_data(self, cache_type: str) -> Optional[Dict]:
        """获取缓存数据"""
        if self._is_cache_valid(cache_type):
            logging.info(f"📦 使用缓存数据: {cache_type}")
            return self._cache[cache_type]
        return None
    
    def _set_cached_data(self, cache_type: str, data: Dict):
        """设置缓存数据"""
        self._cache[cache_type] = data
        self._cache['cache_time'] = time.time()
        logging.info(f"💾 缓存数据: {cache_type}")
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """统一的请求方法，包含重试机制"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logging.info(f"🔄 尝试第 {attempt + 1} 次请求: {method} {url}")
                response = self.session.request(method, url, timeout=30, **kwargs)
                logging.info(f"📊 响应状态码: {response.status_code}")
                
                # 处理数据库异常
                if response.status_code == 500 and "SQLitePCL.pretty.SQLiteException" in response.text:
                    logging.warning(f"⚠️ Emby 数据库异常，尝试重试 ({attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        logging.error("❌ Emby 数据库异常，已达到最大重试次数")
                        return None
                
                # 204表示成功但无内容返回，这也是成功的响应
                if response.status_code in [200, 204]:
                    return response
                else:
                    logging.error(f"❌ API 请求失败: {response.status_code}")
                    logging.error(f"🔍 错误响应: {response.text[:500]}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        return None
                        
            except requests.exceptions.RequestException as e:
                logging.error(f"❌ 请求异常: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    return None
        
        return None
    
    def check_server_status(self) -> bool:
        """检查Emby服务器状态"""
        try:
            url = f"{self.emby_server}/emby/System/Info?api_key={self.emby_api_key}"
            response = self._make_request('GET', url)
            if response:
                logging.info("✅ Emby 服务器状态正常")
                return True
            else:
                logging.error("❌ Emby 服务器状态异常")
                return False
        except Exception as e:
            logging.error(f"❌ 检查 Emby 状态失败: {str(e)}")
            return False
    
    def search_item_by_name(self, name: str, item_type: str = "Movie", year: str = None, 
                           ignore_played: bool = False) -> Optional[Dict]:
        """根据名称搜索媒体项目"""
        # 构建搜索参数
        emby_user_id = ""
        ignore_played_param = ""
        year_param = ""
        
        if item_type == "Series":
            include_item_types = "IncludeItemTypes=Series"
        else:
            include_item_types = "IncludeItemTypes=Movie"
        
        if ignore_played and self.emby_user_id:
            ignore_played_param = "&Filters=IsUnplayed"
            emby_user_id = f"Users/{self.emby_user_id}"
        
        if year:
            year_param = f"&Year={year}"
        
        # 构建URL
        search_term = urllib.parse.quote(name)
        url = f"{self.emby_server}/emby/{emby_user_id}/Items?api_key={self.emby_api_key}{ignore_played_param}&Recursive=true&{include_item_types}&SearchTerm={search_term}{year_param}"
        
        logging.info(f"🔍 搜索项目: {name} (类型: {item_type}, 年份: {year})")
        
        response = self._make_request('GET', url)
        if not response:
            return None
        
        try:
            data = response.json()
            total_count = data.get('TotalRecordCount', 0)
            logging.info(f"📈 找到 {total_count} 个匹配项目")
            
            if total_count > 0:
                for item in data.get('Items', []):
                    if item['Name'] == name:
                        logging.info(f"✅ 找到匹配项目: {item['Name']} (ID: {item.get('Id', 'N/A')})")
                        return item
                logging.warning(f"⚠️ 未找到完全匹配的项目: {name}")
                return None
            else:
                logging.info(f"ℹ️ 未找到任何匹配的项目: {name}")
                return None
                
        except ValueError as e:
            logging.error(f"❌ JSON解析失败: {str(e)}")
            return None
    
    def create_collection(self, collection_name: str, initial_item_id: str) -> Optional[str]:
        """创建合集"""
        encoded_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/emby/Collections?IsLocked=false&Name={encoded_name}&Ids={initial_item_id}&api_key={self.emby_api_key}"
        headers = {"accept": "application/json"}
        
        logging.info(f"🔨 创建合集: {collection_name}")
        
        response = self._make_request('POST', url, headers=headers)
        if not response:
            return None
        
        try:
            collection_id = response.json().get('Id')
            if collection_id:
                logging.info(f"✅ 成功创建合集: {collection_id}")
                return collection_id
            else:
                logging.error("❌ 创建合集失败: 未返回ID")
                return None
        except ValueError as e:
            logging.error(f"❌ JSON解析失败: {str(e)}")
            return None
    
    def add_item_to_collection(self, item_id: str, collection_id: str) -> bool:
        """添加项目到合集"""
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items?Ids={item_id}&api_key={self.emby_api_key}"
        headers = {"accept": "application/json"}
        
        logging.info(f"➕ 添加项目到合集: item_id={item_id}, collection_id={collection_id}")
        
        response = self._make_request('POST', url, headers=headers)
        if response:
            if response.status_code == 204:
                logging.info(f"✅ 成功添加项目到合集 (状态码: 204 - 无内容)")
            else:
                logging.info(f"✅ 成功添加项目到合集 (状态码: {response.status_code})")
            return True
        else:
            logging.error(f"❌ 添加项目到合集失败")
            return False
    
    def check_collection_exists(self, collection_name: str) -> Optional[Dict]:
        """检查合集是否存在"""
        # 先尝试从缓存获取
        cached_collections = self._get_cached_data('collections')
        if cached_collections:
            for collection in cached_collections:
                if collection.get('Name') == collection_name:
                    return collection
        
        # 从服务器获取
        encoded_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&SearchTerm={encoded_name}&api_key={self.emby_api_key}"
        
        logging.info(f"🔍 检查合集是否存在: {collection_name}")
        
        response = self._make_request('GET', url)
        if not response:
            return None
        
        try:
            data = response.json()
            for item in data.get('Items', []):
                if item.get('Name') == collection_name:
                    logging.info(f"✅ 找到合集: {collection_name} (ID: {item.get('Id')})")
                    return item
            
            logging.info(f"ℹ️ 合集不存在: {collection_name}")
            return None
            
        except ValueError as e:
            logging.error(f"❌ JSON解析失败: {str(e)}")
            return None
    
    def get_collection_items(self, collection_id: str) -> List[str]:
        """获取合集中的所有项目名称"""
        url = f"{self.emby_server}/emby/Items?api_key={self.emby_api_key}&ParentId={collection_id}"
        
        logging.info(f"📋 获取合集项目: collection_id={collection_id}")
        
        response = self._make_request('GET', url)
        if not response:
            return []
        
        try:
            data = response.json()
            items = [item.get('Name', '') for item in data.get('Items', [])]
            logging.info(f"📈 合集包含 {len(items)} 个项目")
            return items
        except ValueError as e:
            logging.error(f"❌ JSON解析失败: {str(e)}")
            return []
    
    def clear_collection(self, collection_id: str) -> bool:
        """清空合集"""
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items/Delete"
        params = {"api_key": self.emby_api_key}
        
        logging.info(f"🗑️ 清空合集: collection_id={collection_id}")
        
        response = self._make_request('POST', url, params=params)
        if response:
            if response.status_code == 204:
                logging.info(f"✅ 成功清空合集 (状态码: 204 - 无内容)")
            else:
                logging.info(f"✅ 成功清空合集 (状态码: {response.status_code})")
            return True
        else:
            logging.error(f"❌ 清空合集失败")
            return False
    
    def replace_collection_cover(self, collection_id: str, image_url: str) -> bool:
        """替换合集封面"""
        try:
            # 下载图片
            image_response = requests.get(image_url, timeout=30)
            if image_response.status_code != 200:
                logging.error(f"❌ 下载图片失败: {image_response.status_code}")
                return False
            
            # 转换为base64
            base64_image = base64.b64encode(image_response.content)
            
            # 上传到Emby
            url = f'{self.emby_server}/emby/Items/{collection_id}/Images/Primary?api_key={self.emby_api_key}'
            headers = {
                'Content-Type': 'image/jpeg',
                'X-Emby-Token': self.emby_api_key
            }
            
            logging.info(f"🖼️ 替换合集封面: collection_id={collection_id}")
            
            response = self._make_request('POST', url, headers=headers, data=base64_image)
            if response:
                if response.status_code == 204:
                    logging.info(f"✅ 成功替换合集封面 (状态码: 204 - 无内容)")
                else:
                    logging.info(f"✅ 成功替换合集封面 (状态码: {response.status_code})")
                return True
            else:
                logging.error(f"❌ 替换合集封面失败")
                return False
                
        except Exception as e:
            logging.error(f"❌ 替换封面异常: {str(e)}")
            return False
    
    def get_all_collections(self) -> List[Dict]:
        """获取所有合集"""
        cached_collections = self._get_cached_data('collections')
        if cached_collections:
            return cached_collections
        
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&api_key={self.emby_api_key}"
        
        logging.info("📋 获取所有合集")
        
        response = self._make_request('GET', url)
        if not response:
            return []
        
        try:
            data = response.json()
            collections = data.get('Items', [])
            self._set_cached_data('collections', collections)
            logging.info(f"📈 找到 {len(collections)} 个合集")
            return collections
        except ValueError as e:
            logging.error(f"❌ JSON解析失败: {str(e)}")
            return []


class RSSHubAPI:
    """RSSHub API 统一接口类"""
    
    def __init__(self, rsshub_server: str, name_mapping: dict = None):
        self.rsshub_server = rsshub_server.rstrip('/')
        self.name_mapping = name_mapping or {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36"
        })
    
    def get_douban_movie_rss(self, rss_id: str) -> Optional[Dict]:
        """获取豆瓣电影RSS数据"""
        rss_url = f"{self.rsshub_server}/douban/movie/weekly/{rss_id}"
        
        logging.info(f"📡 获取豆瓣电影RSS: {rss_id}")
        
        try:
            response = self.session.get(rss_url, timeout=30)
            if response.status_code != 200:
                logging.error(f"❌ RSS请求失败: {response.status_code}")
                return None
            
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                logging.error(f"❌ RSS数据为空: {rss_url}")
                return None
            
            movies = []
            for item in feed.entries:
                name = item.title.strip() if item.title else ""
                if not name:
                    continue
                
                # 提取年份
                year = None
                if hasattr(item, 'year') and item.year:
                    year = item.year
                
                # 确定类型
                media_type = getattr(item, 'type', 'movie')
                if media_type == 'book':
                    continue
                if media_type == 'tv':
                    name = re.sub(r" 第[一二三四五六七八九十\d]+季", "", name)
                
                movies.append({
                    'name': name,
                    'year': year,
                    'type': media_type
                })
            
            result = {
                'title': feed.feed.title if hasattr(feed.feed, 'title') else f'豆瓣{rss_id}',
                'movies': movies
            }
            
            logging.info(f"✅ 成功获取RSS数据: {len(movies)} 部电影")
            return result
            
        except Exception as e:
            logging.error(f"❌ 获取RSS数据失败: {str(e)}")
            return None
    
    def get_douban_doulist_rss(self, doulist_id: str) -> Optional[Dict]:
        """获取豆瓣豆列RSS数据"""
        rss_url = f"{self.rsshub_server}/douban/doulist/{doulist_id}"
        
        logging.info(f"📡 获取豆瓣豆列RSS: {doulist_id}")
        
        try:
            response = self.session.get(rss_url, timeout=30)
            if response.status_code != 200:
                logging.error(f"❌ RSS请求失败: {response.status_code}")
                return None
            
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                logging.error(f"❌ RSS数据为空: {rss_url}")
                return None
            
            movies = []
            for item in feed.entries:
                raw_title = item.title.strip() if item.title else ""
                if not raw_title or re.match(r'^[\s\-—–]*$', raw_title):
                    continue
                
                # 提取简体名称
                name = raw_title
                simplified_name_match = re.match(r'([^\s]+)', name)
                if simplified_name_match:
                    name = simplified_name_match.group(1)
                
                # 应用名称映射
                name = self.name_mapping.get(name, name)
                
                # 从描述中提取年份和类型
                description = item.description
                year = None
                media_type = "movie"
                
                year_match = re.search(r'年份:\s*(\d{4})', description)
                if year_match:
                    year = year_match.group(1)
                
                type_match = re.search(r'类型:\s*([^<]+)', description)
                if type_match:
                    types = type_match.group(1).strip()
                    if "剧情" in types or "电影" in types or "爱情" in types or "同性" in types:
                        media_type = "movie"
                    elif "电视剧" in types or "剧集" in types:
                        media_type = "tv"
                
                if media_type == 'book':
                    continue
                if media_type == "tv":
                    name = re.sub(r" 第[一二三四五六七八九十\d]+季", "", name)
                
                movies.append({
                    'name': name,
                    'year': year,
                    'type': media_type
                })
            
            result = {
                'title': feed.feed.title if hasattr(feed.feed, 'title') else f'豆列{doulist_id}',
                'movies': movies
            }
            
            logging.info(f"✅ 成功获取豆列RSS数据: {len(movies)} 部电影")
            return result
            
        except Exception as e:
            logging.error(f"❌ 获取豆列RSS数据失败: {str(e)}")
            return None
    
    def get_bangumi_calendar(self) -> Optional[Dict]:
        """获取Bangumi日历数据"""
        rss_url = "https://api.bgm.tv/calendar"
        
        logging.info("📡 获取Bangumi日历数据")
        
        try:
            response = self.session.get(rss_url, timeout=30)
            if response.status_code != 200:
                logging.error(f"❌ Bangumi API请求失败: {response.status_code}")
                return None
            
            data = response.json()
            movies = []
            
            for entry in data:
                title = entry.get('weekday', {}).get('cn', '未知分类')
                for item in entry.get('items', []):
                    name = item.get('name_cn') or item.get('name')
                    year = None
                    
                    air_date = item.get('air_date')
                    if air_date:
                        year_match = re.search(r'(\d{4})', air_date)
                        if year_match:
                            year = year_match.group(1)
                    
                    media_type = 'tv' if item.get('type') == 2 else 'movie'
                    
                    if media_type == 'book':
                        continue
                    if media_type == 'tv':
                        name = re.sub(r" 第[一二三四五六七八九十\d]+季", "", name)
                    
                    movies.append({
                        'name': name,
                        'year': year,
                        'type': media_type
                    })
            
            result = {
                'title': 'Bangumi日历',
                'movies': movies
            }
            
            logging.info(f"✅ 成功获取Bangumi数据: {len(movies)} 部作品")
            return result
            
        except Exception as e:
            logging.error(f"❌ 获取Bangumi数据失败: {str(e)}")
            return None
    
    def test_connection(self, rss_type: str, rss_id: str) -> bool:
        """测试RSS连接"""
        if rss_type == 'douban_movie':
            rss_url = f"{self.rsshub_server}/douban/movie/weekly/{rss_id}"
        elif rss_type == 'douban_doulist':
            rss_url = f"{self.rsshub_server}/douban/doulist/{rss_id}"
        else:
            logging.error(f"❌ 不支持的RSS类型: {rss_type}")
            return False
        
        logging.info(f"🧪 测试RSS连接: {rss_url}")
        
        try:
            response = self.session.get(rss_url, timeout=30)
            logging.info(f"📊 RSS响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                feed = feedparser.parse(rss_url)
                if feed.entries:
                    logging.info(f"✅ RSS连接正常，找到{len(feed.entries)}个条目")
                    return True
                else:
                    logging.error("❌ RSS解析成功但无条目")
                    return False
            else:
                logging.error(f"❌ RSS请求失败: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"❌ RSS连接测试失败: {str(e)}")
            return False


# 导入正则表达式模块
import re 