 #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 类型标签映射器 - 重构版本
参考原emby_scripts-master/genre_mapper/genre_mapper.py
将Emby中的英文类型标签映射为中文标签
"""
import os
import logging
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

class Get_Detail:
    """类型标签映射器主类"""
    
    def __init__(self):
        # 从配置文件获取配置
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        self.library_names = config.get('GenreMapper', 'library_names', fallback='').split(',')
        self.dry_run = config.getboolean('GenreMapper', 'dry_run', fallback=True)
        
        # 从配置文件读取类型映射（中文->英文）
        self.genre_mapping = {}
        if config.has_section('GenreMapping'):
            for key, value in config.items('GenreMapping'):
                self.genre_mapping[key] = value
            logging.info(f"🏷️ 加载类型映射: {len(self.genre_mapping)} 条规则")
        else:
            logging.warning("⚠️ 未找到类型映射配置")
        
        # 创建反向映射（英文->中文）
        self.reverse_genre_mapping = {v: k for k, v in self.genre_mapping.items()}
        logging.info(f"🔄 创建反向映射: {len(self.reverse_genre_mapping)} 条规则")
        
        # 初始化API客户端
        self.emby_api = EmbyAPI(
            emby_server=self.emby_server,
            emby_api_key=self.emby_api_key,
            emby_user_id=self.emby_user_id
        )
        
        self.process_count = 0
    
    def get_library_id(self, library_name):
        """获取库ID"""
        if not library_name.strip():
            return None
        
        try:
            response = self.emby_api._make_request('GET', '/Library/VirtualFolders')
            if response and response.status_code == 200:
                libraries = response.json()
                for lib in libraries:
                    if lib['Name'] == library_name.strip():
                        return lib['ItemId']
            
            logging.error(f"❌ 库不存在: {library_name}")
            return None
        except Exception as e:
            logging.error(f"❌ 获取库ID失败: {str(e)}")
            return None
    
    def get_library_items(self, parent_id):
        """递归获取库中的所有项目"""
        try:
            params = {
                'ParentId': parent_id,
                'fields': 'ProviderIds'
            }
            response = self.emby_api._make_request('GET', '/Items', params=params)
            if not response or response.status_code != 200:
                return []
            
            data = response.json()
            items = data.get('Items', [])
            
            # 分离文件夹和普通项目
            folders = [item for item in items if item['Type'] == 'Folder']
            normal_items = [item for item in items if item['Type'] != 'Folder']
            
            # 递归处理文件夹
            for folder in folders:
                sub_items = self.get_library_items(folder['Id'])
                normal_items.extend(sub_items)
            
            return normal_items
        except Exception as e:
            logging.error(f"❌ 获取库项目失败: {str(e)}")
            return []
    
    def update_item_genres(self, item_id, item_name):
        """更新项目的类型标签"""
        try:
            # 获取项目详情
            response = self.emby_api._make_request('GET', f'/Users/{self.emby_user_id}/Items/{item_id}?Fields=ChannelMappingInfo')
            if not response or response.status_code != 200:
                logging.error(f"❌ 获取项目详情失败: {item_name}")
                return False
            
            item_data = response.json()
            original_genres = item_data.get('Genres', [])
            original_genre_items = item_data.get('GenreItems', [])
            
            # 检查是否需要更新
            need_update = False
            new_genres = []
            new_genre_items = []
            
            # 处理Genres
            for genre in original_genres:
                if genre in self.reverse_genre_mapping:
                    new_genre = self.reverse_genre_mapping[genre]
                    new_genres.append(new_genre)
                    need_update = True
                    logging.info(f"🔄 类型映射: {genre} -> {new_genre}")
                else:
                    new_genres.append(genre)
            
            # 处理GenreItems
            for genre_item in original_genre_items:
                genre_name = genre_item.get('Name', '')
                if genre_name in self.reverse_genre_mapping:
                    new_genre_name = self.reverse_genre_mapping[genre_name]
                    new_genre_item = genre_item.copy()
                    new_genre_item['Name'] = new_genre_name
                    new_genre_items.append(new_genre_item)
                    need_update = True
                else:
                    new_genre_items.append(genre_item)
            
            if need_update:
                logging.info(f"📝 {item_name}:")
                logging.info(f"   原类型: {original_genres}")
                logging.info(f"   新类型: {new_genres}")
                
                # 更新数据
                item_data['Genres'] = new_genres
                item_data['GenreItems'] = new_genre_items
                
                if not self.dry_run:
                    # 实际更新
                    update_response = self.emby_api._make_request('POST', f'/Items/{item_id}?reqformat=json', json_data=item_data)
                    if update_response and update_response.status_code in [200, 204]:
                        self.process_count += 1
                        logging.info(f"✅ 成功更新: {item_name}")
                        return True
                    else:
                        logging.error(f"❌ 更新失败: {item_name} - {update_response.status_code if update_response else 'No response'}")
                        return False
                else:
                    # 预览模式
                    logging.info(f"🔍 预览模式 - 将更新: {item_name}")
                    self.process_count += 1
                    return True
            else:
                logging.debug(f"⏭️ 无需更新: {item_name}")
                return True
                
        except Exception as e:
            logging.error(f"❌ 更新项目类型失败 {item_name}: {str(e)}")
            return False
    
    def run(self):
        """运行类型标签映射器"""
        logging.info("🚀 开始运行类型标签映射器")
        
        if not self.library_names or not self.library_names[0].strip():
            logging.error("❌ 未配置库名称，请在config.conf中设置[GenreMapper]library_names")
            return
        
        if not self.reverse_genre_mapping:
            logging.warning("⚠️ 没有配置类型映射规则，跳过处理")
            return
        
        logging.info(f"📋 类型映射规则: {self.reverse_genre_mapping}")
        logging.info(f"🔍 预览模式: {'是' if self.dry_run else '否'}")
        
        # 处理每个库
        for library_name in self.library_names:
            library_name = library_name.strip()
            if not library_name:
                continue
            
            logging.info(f"📚 处理库: {library_name}")
            
            # 获取库ID
            library_id = self.get_library_id(library_name)
            if not library_id:
                continue
            
            # 获取库中的所有项目
            items = self.get_library_items(library_id)
            logging.info(f"📦 库 {library_name} 中共有 {len(items)} 个项目")
            
            # 只处理电影和剧集
            media_items = [item for item in items if item['Type'] in ['Movie', 'Series']]
            logging.info(f"🎬 媒体项目数量: {len(media_items)}")
            
            # 处理每个项目
            for item in media_items:
                item_id = item['Id']
                item_name = item.get('Name', 'Unknown')
                item_type = item['Type']
                
                logging.debug(f"🔍 处理项目: {item_name} ({item_type})")
                self.update_item_genres(item_id, item_name)
        
        logging.info(f"🎯 类型标签映射完成，共处理 {self.process_count} 个项目")
        logging.info("✅ 类型标签映射器运行完成")

if __name__ == "__main__":
    logging.info("执行单次任务")
    gd = Get_Detail()
    gd.run()