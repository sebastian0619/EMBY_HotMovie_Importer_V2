#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 类型标签映射器
将Emby库中的中文类型标签映射为英文标签
"""
import os
import logging
import requests
from typing import List, Dict, Optional
from configparser import ConfigParser

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

class Get_Detail:
    """类型标签映射器主类"""
    
    def __init__(self):
        # 从配置文件获取配置
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        
        # 从配置文件读取类型映射
        self.genre_mapping = {}
        if config.has_section('GenreMapping'):
            for key, value in config.items('GenreMapping'):
                self.genre_mapping[key] = value
            logging.info(f"🏷️ 加载类型映射: {len(self.genre_mapping)} 条规则")
        else:
            logging.warning("⚠️ 未找到类型映射配置")
        
        # 获取库配置
        library_names_str = config.get('GenreMapper', 'library_names', fallback='')
        self.library_names = [name.strip() for name in library_names_str.split(',') if name.strip()]
        self.dry_run = config.getboolean('GenreMapper', 'dry_run', fallback=True)
        
        if not self.library_names:
            logging.warning("⚠️ 未配置库名，将处理所有库")
    
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
                'api_key': self.emby_api_key,
                'Recursive': 'true',
                'IncludeItemTypes': 'Movie,Series',
                'Fields': 'ProviderIds,Genres'
            }
            
            response = requests.get(
                f"{self.emby_server}/emby/Items",
                params=params,
                headers={'X-Emby-Token': self.emby_api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('Items', [])
                logging.info(f"📋 找到 {len(items)} 个项目")
                return items
            else:
                logging.error(f"❌ 获取库项目失败: {response.status_code}")
                return []
                
        except Exception as e:
            logging.error(f"❌ 获取库项目异常: {str(e)}")
            return []
    
    def map_genres(self, genres: List[str]) -> List[str]:
        """映射类型标签"""
        if not genres:
            return []
        
        mapped_genres = []
        for genre in genres:
            mapped_genre = self.genre_mapping.get(genre, genre)
            if mapped_genre not in mapped_genres:  # 避免重复
                mapped_genres.append(mapped_genre)
        
        return mapped_genres
    
    def update_item_genres(self, item_id: str, genres: List[str]) -> bool:
        """更新项目的类型标签"""
        try:
            # 获取项目详情
            response = requests.get(
                f"{self.emby_server}/emby/Users/{self.emby_user_id}/Items/{item_id}?Fields=ChannelMappingInfo",
                headers={'X-Emby-Token': self.emby_api_key}
            )
            
            if response.status_code != 200:
                logging.error(f"❌ 获取项目详情失败: {response.status_code}")
                return False
            
            item_data = response.json()
            
            # 更新类型标签
            item_data['Genres'] = genres
            
            # 确保LockedFields包含Genres
            if 'LockedFields' not in item_data:
                item_data['LockedFields'] = []
            if 'Genres' not in item_data['LockedFields']:
                item_data['LockedFields'].append('Genres')
            
            # 更新项目
            update_response = requests.post(
                f"{self.emby_server}/emby/Items/{item_id}?api_key={self.emby_api_key}&reqformat=json",
                json=item_data,
                headers={'X-Emby-Token': self.emby_api_key}
            )
            
            if update_response.status_code in [200, 204]:
                return True
            else:
                logging.error(f"❌ 更新项目失败: {update_response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"❌ 更新项目异常: {str(e)}")
            return False
    
    def process_library(self, library_name: str):
        """处理单个库"""
        logging.info(f"📚 处理库: {library_name}")
        
        # 获取库ID
        library_id = self.get_library_id(library_name)
        if not library_id:
            logging.error(f"❌ 无法获取库ID: {library_name}")
            return
        
        # 获取库中的项目
        items = self.get_library_items(library_id)
        if not items:
            logging.warning(f"⚠️ 库中没有找到项目: {library_name}")
            return
        
        processed_count = 0
        updated_count = 0
        
        for item in items:
            item_name = item.get('Name', 'Unknown')
            item_type = item.get('Type', 'Unknown')
            current_genres = item.get('Genres', [])
            
            # 跳过没有类型标签的项目
            if not current_genres:
                continue
            
            processed_count += 1
            
            # 映射类型标签
            mapped_genres = self.map_genres(current_genres)
            
            # 检查是否有变化
            if set(mapped_genres) != set(current_genres):
                logging.info(f"🔄 {item_name} ({item_type}): {current_genres} -> {mapped_genres}")
                
                if not self.dry_run:
                    if self.update_item_genres(item['Id'], mapped_genres):
                        updated_count += 1
                        logging.info(f"✅ 成功更新: {item_name}")
                    else:
                        logging.error(f"❌ 更新失败: {item_name}")
                else:
                    updated_count += 1
                    logging.info(f"🔍 预览模式 - 将更新: {item_name}")
            else:
                logging.debug(f"ℹ️ 无需更新: {item_name} ({current_genres})")
        
        logging.info(f"🎯 库 {library_name} 处理完成: 处理 {processed_count} 个项目，更新 {updated_count} 个项目")
    
    def run(self):
        """运行类型标签映射器"""
        logging.info("🚀 开始运行类型标签映射器")
        
        if not self.genre_mapping:
            logging.error("❌ 没有配置类型映射规则")
            return
        
        if self.dry_run:
            logging.info("🔍 预览模式 - 不会实际修改数据")
        
        # 处理指定的库
        if self.library_names:
            for library_name in self.library_names:
                self.process_library(library_name)
        else:
            # 处理所有库
            try:
                response = requests.get(
                    f"{self.emby_server}/emby/Library/VirtualFolders",
                    headers={'X-Emby-Token': self.emby_api_key}
                )
                
                if response.status_code == 200:
                    libraries = response.json()
                    for lib in libraries:
                        self.process_library(lib['Name'])
                else:
                    logging.error(f"❌ 获取库列表失败: {response.status_code}")
                    
            except Exception as e:
                logging.error(f"❌ 获取库列表异常: {str(e)}")
        
        logging.info("✅ 类型标签映射器运行完成")

if __name__ == "__main__":
    logging.info("执行单次任务")
    gd = Get_Detail()
    gd.run() 