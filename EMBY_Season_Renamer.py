#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 季节重命名器
根据TMDB数据自动重命名剧集季节
"""
import os
import csv
import json
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from dateutil import parser
from configparser import ConfigParser
from utils import EmbyAPI

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

class JsonDataBase:
    """JSON数据库类，用于缓存TMDB数据"""
    
    def __init__(self, name, prefix='', db_type='dict', workdir=None):
        self.file_name = f'{prefix}_{name}.json' if prefix else f'{name}.json'
        self.file_path = os.path.join(workdir, self.file_name) if workdir else self.file_name
        self.db_type = db_type
        self.data = self.load()

    def load(self, encoding='utf-8'):
        try:
            with open(self.file_path, encoding=encoding) as f:
                _json = json.load(f)
        except (FileNotFoundError, ValueError):
            return dict(list=[], dict={})[self.db_type]
        else:
            return _json

    def dump(self, obj, encoding='utf-8'):
        with open(self.file_path, 'w', encoding=encoding) as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

    def save(self):
        self.dump(self.data)

class TmdbDataBase(JsonDataBase):
    """TMDB数据缓存类"""
    
    def __getitem__(self, tmdb_id):
        data = self.data.get(tmdb_id)
        if not data:
            return
        
        air_date = date.today()
        try:
            air_date = parser.parse(data['premiere_date']).date()
        except Exception:
            pass
        
        today = date.today()
        if air_date + timedelta(days=30) > today:
            expire_day = 3
        elif air_date + timedelta(days=90) > today:
            expire_day = 15
        elif air_date + timedelta(days=365) > today:
            expire_day = 30
        else:
            expire_day = 30
        
        update_date = date.fromisoformat(data['update_date'])
        if update_date + timedelta(days=expire_day) < today:
            return
        
        return data

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def clean_not_trust_data(self, expire_days=7, min_trust=0.5):
        """清理不可信数据"""
        today = date.today()
        keys_to_remove = []
        for key, value in self.data.items():
            update_date = date.fromisoformat(value['update_date'])
            if update_date + timedelta(days=expire_days) < today:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.data[key]
        self.save()

    def save_seasons(self, tmdb_id, premiere_date, name, alt_names, seasons=None):
        """保存季节数据"""
        self.data[tmdb_id] = {
            'premiere_date': premiere_date,
            'name': name,
            'alt_names': alt_names,
            'seasons': seasons,
            'update_date': date.today().isoformat()
        }
        self.save()

class TMDBAPI:
    """TMDB API接口类"""
    
    def __init__(self):
        self.api_key = config.get('TMDB', 'tmdb_api_key')
        self.base_url = config.get('TMDB', 'tmdb_api_base_url', fallback='https://api.themoviedb.org/3')
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        })
    
    def get_tv_series_info(self, tmdb_id: str) -> Optional[Dict]:
        """获取电视剧信息"""
        try:
            url = f"{self.base_url}/tv/{tmdb_id}?language=zh-CN&append_to_response=alternative_titles"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"❌ TMDB API请求失败: {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"❌ 获取TMDB数据失败: {str(e)}")
            return None

class Get_Detail:
    """季节重命名器主类"""
    
    def __init__(self):
        # 从配置文件获取配置
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        self.library_names = config.get('SeasonRenamer', 'library_names', fallback='').split(',')
        self.dry_run = config.getboolean('SeasonRenamer', 'dry_run', fallback=True)
        
        # 检查TMDB API密钥
        tmdb_api_key = config.get('TMDB', 'tmdb_api_key', fallback='')
        if not tmdb_api_key:
            logging.error("❌ TMDB API密钥未配置，请在config.conf的[TMDB]部分设置tmdb_api_key")
            return
        
        # 初始化API客户端
        self.emby_api = EmbyAPI(
            emby_server=self.emby_server,
            emby_api_key=self.emby_api_key,
            emby_user_id=self.emby_user_id
        )
        self.tmdb_api = TMDBAPI()
        
        # 初始化缓存
        self.tmdb_db = TmdbDataBase('tmdb_seasons', 'season_renamer')
        
        self.process_count = 0
    
    def get_or_default(self, _dict, key, default=None):
        """安全获取字典值"""
        return _dict.get(key, default)
    
    def get_season_info_from_tmdb(self, tmdb_id: str, is_movie: bool, series_name: str):
        """从TMDB获取季节信息"""
        cache_key = ('mv' if is_movie else 'tv') + f'{tmdb_id}'
        cache_data = self.tmdb_db[cache_key]
        
        if cache_data:
            alt_names = cache_data['seasons']
            return alt_names, True
        
        if is_movie:
            logging.warning(f"⚠️ 电影不支持季节重命名: {series_name}")
            return None, None
        
        # 获取电视剧信息
        resp_json = self.tmdb_api.get_tv_series_info(tmdb_id)
        if not resp_json:
            return None, None
        
        if 'seasons' in resp_json:
            titles = resp_json.get("alternative_titles", {})
            release_date = self.get_or_default(
                resp_json, 'last_air_date', 
                default=self.get_or_default(resp_json, 'first_air_date')
            )
            alt_names = self.get_or_default(titles, "results", None)
            
            self.tmdb_db.save_seasons(
                cache_key, 
                premiere_date=release_date,
                name=series_name, 
                alt_names=alt_names, 
                seasons=resp_json['seasons']
            )
            return resp_json['seasons'], False
        else:
            return None, None
    
    def rename_seasons(self, parent_id: str, tmdb_id: str, series_name: str, is_movie: bool):
        """重命名季节"""
        # 如果是电影，跳过（电影没有季节）
        if is_movie:
            logging.debug(f"📽️ 跳过电影: {series_name} (电影不支持季节重命名)")
            return
        
        tmdb_seasons, is_cache = self.get_season_info_from_tmdb(tmdb_id, is_movie, series_name)
        from_cache = ' (缓存)' if is_cache else ''
        
        if not tmdb_seasons:
            logging.error(f"❌ TMDB中未找到季节信息: {tmdb_id} {series_name}")
            return
        
        # 获取Emby中的季节信息
        seasons_url = f"{self.emby_server}/emby/Items?ParentId={parent_id}&api_key={self.emby_api_key}"
        response = requests.get(seasons_url)
        if response.status_code != 200:
            logging.error(f"❌ 获取季节列表失败: {response.status_code}")
            return
        
        seasons = response.json()['Items']
        
        for season in seasons:
            season_id = season['Id']
            season_name = season['Name']
            series_name = season.get('SeriesName', series_name)
            
            if 'IndexNumber' not in season:
                logging.info(f"📋 {series_name} {season_name} 没有编号，跳过")
                continue
            
            season_index = season['IndexNumber']
            tmdb_season = next(
                (s for s in tmdb_seasons if s['season_number'] == season_index), 
                None
            )
            
            if tmdb_season:
                tmdb_season_name = tmdb_season['name']
                
                # 获取单个季节详细信息
                season_detail_url = f"{self.emby_server}/emby/Users/{self.emby_user_id}/Items/{season_id}?Fields=ChannelMappingInfo&api_key={self.emby_api_key}"
                season_response = requests.get(season_detail_url)
                if season_response.status_code != 200:
                    logging.error(f"❌ 获取季节详情失败: {season_response.status_code}")
                    continue
                
                single_season = season_response.json()
                
                if 'Name' in single_season:
                    if season_name == tmdb_season_name:
                        if not self.dry_run:
                            logging.info(f"✅ {series_name} 第{season_index}季{from_cache} [{season_name}] 季名一致，跳过更新")
                        continue
                    else:
                        logging.info(f"🔄 {series_name} 第{season_index}季{from_cache} 将从 [{season_name}] 更名为 [{tmdb_season_name}]")
                    
                    single_season['Name'] = tmdb_season_name
                    
                    if 'LockedFields' not in single_season:
                        single_season['LockedFields'] = []
                    if 'Name' not in single_season['LockedFields']:
                        single_season['LockedFields'].append('Name')
                    
                    if not self.dry_run:
                        update_url = f"{self.emby_server}/emby/Items/{season_id}?api_key={self.emby_api_key}&reqformat=json"
                        update_response = requests.post(update_url, json=single_season)
                        
                        if update_response.status_code in [200, 204]:
                            self.process_count += 1
                            logging.info(f"✅ 成功更新 {series_name} {season_name}")
                        else:
                            logging.error(f"❌ 更新失败 {series_name} {season_name}: {update_response.status_code}")
    
    def get_library_id(self, name: str) -> Optional[str]:
        """获取库ID"""
        if not name:
            return None
        
        try:
            response = requests.get(
                f"{self.emby_server}/emby/Library/VirtualFolders",
                headers={'X-Emby-Token': self.emby_api_key}
            )
            
            if response.status_code == 200:
                libraries = response.json()
                for lib in libraries:
                    if lib['Name'] == name:
                        return lib['ItemId']
            
            logging.error(f"❌ 库不存在: {name}")
            return None
            
        except Exception as e:
            logging.error(f"❌ 获取库ID失败: {str(e)}")
            return None
    
    def get_library_items(self, parent_id: str) -> List[Dict]:
        """获取库中的项目（递归获取）"""
        try:
            params = {
                'ParentId': parent_id,
                'fields': 'ProviderIds'
            }
            
            response = requests.get(
                f"{self.emby_server}/emby/Items",
                headers={'X-Emby-Token': self.emby_api_key},
                params=params
            )
            
            if response.status_code != 200:
                logging.error(f"❌ 获取库项目失败: {response.status_code}")
                return []
            
            items = response.json().get('Items', [])
            
            # 分离文件夹和普通项目
            items_folder = [item for item in items if item["Type"] == "Folder"]
            items_normal = [item for item in items if item["Type"] != "Folder"]
            
            # 递归获取文件夹中的项目
            for folder in items_folder:
                folder_items = self.get_library_items(folder['Id'])
                items_normal.extend(folder_items)
            
            return items_normal
                
        except Exception as e:
            logging.error(f"❌ 获取库项目异常: {str(e)}")
            return []
    
    def run(self):
        """运行重命名器"""
        logging.info("🚀 开始运行季节重命名器")
        
        if not self.library_names or not self.library_names[0]:
            logging.error("❌ 未配置库名称")
            return
        
        for library_name in self.library_names:
            library_name = library_name.strip()
            if not library_name:
                continue
            
            logging.info(f"📚 处理库: {library_name}")
            
            # 获取库ID
            library_id = self.get_library_id(library_name)
            if not library_id:
                continue
            
            # 获取库中的项目
            items = self.get_library_items(library_id)
            logging.info(f"📋 找到 {len(items)} 个项目")
            
            # 统计有TMDB ID的项目
            items_with_tmdb = [item for item in items if item.get('ProviderIds', {}).get('Tmdb')]
            logging.info(f"🎯 其中 {len(items_with_tmdb)} 个项目有TMDB ID")
            
            for item in items:
                # 调试：打印ProviderIds信息
                provider_ids = item.get('ProviderIds', {})
                logging.debug(f"🔍 项目 {item['Name']} 的ProviderIds: {provider_ids}")
                
                tmdb_id = provider_ids.get('Tmdb')
                if not tmdb_id:
                    logging.debug(f"⏭️ 跳过项目 {item['Name']}: 没有TMDB ID")
                    continue
                
                item_name = item['Name']
                item_id = item['Id']
                is_movie = item['Type'] == 'Movie'
                
                # 跳过电影，只处理电视剧
                if is_movie:
                    logging.debug(f"📽️ 跳过电影: {item_name}")
                    continue
                
                logging.info(f"🎬 处理项目: {item_name} (TMDB: {tmdb_id})")
                self.rename_seasons(item_id, tmdb_id, item_name, is_movie)
        
        logging.info(f"✅ 季节重命名器运行完成，处理了 {self.process_count} 个季节")

if __name__ == "__main__":
    logging.info("执行单次任务")
    gd = Get_Detail()
    gd.run() 