#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 国家标签抓取器
根据TMDB数据自动添加国家和语言标签
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

# 国家映射字典
COUNTRY_DICT = {
    'KR': '韩国',
    'CN': '中国',
    'HK': '香港',
    'TW': '台湾',
    'JP': '日本',
    'US': '美国',
    'GB': '英国',
    'FR': '法国',
    'DE': '德国',
    'IN': '印度',
    'RU': '俄罗斯',
    'CA': '加拿大',
    'AU': '澳大利亚',
    'IT': '意大利',
    'ES': '西班牙',
    'BR': '巴西',
    'MX': '墨西哥',
    'TH': '泰国',
    'SG': '新加坡',
    'MY': '马来西亚',
    'ID': '印度尼西亚',
    'PH': '菲律宾',
    'VN': '越南',
    'TR': '土耳其',
    'NL': '荷兰',
    'SE': '瑞典',
    'NO': '挪威',
    'DK': '丹麦',
    'FI': '芬兰',
    'PL': '波兰',
    'CZ': '捷克',
    'HU': '匈牙利',
    'AT': '奥地利',
    'CH': '瑞士',
    'BE': '比利时',
    'PT': '葡萄牙',
    'GR': '希腊',
    'IE': '爱尔兰',
    'NZ': '新西兰',
    'ZA': '南非',
    'EG': '埃及',
    'MA': '摩洛哥',
    'NG': '尼日利亚',
    'KE': '肯尼亚',
    'IL': '以色列',
    'AE': '阿联酋',
    'SA': '沙特阿拉伯',
    'QA': '卡塔尔',
    'KW': '科威特',
    'BH': '巴林',
    'OM': '阿曼',
    'JO': '约旦',
    'LB': '黎巴嫩',
    'SY': '叙利亚',
    'IQ': '伊拉克',
    'IR': '伊朗',
    'PK': '巴基斯坦',
    'BD': '孟加拉国',
    'LK': '斯里兰卡',
    'NP': '尼泊尔',
    'MM': '缅甸',
    'KH': '柬埔寨',
    'LA': '老挝',
    'MN': '蒙古',
    'KZ': '哈萨克斯坦',
    'UZ': '乌兹别克斯坦',
    'KG': '吉尔吉斯斯坦',
    'TJ': '塔吉克斯坦',
    'TM': '土库曼斯坦',
    'AZ': '阿塞拜疆',
    'GE': '格鲁吉亚',
    'AM': '亚美尼亚',
    'BY': '白俄罗斯',
    'MD': '摩尔多瓦',
    'UA': '乌克兰',
    'RO': '罗马尼亚',
    'BG': '保加利亚',
    'HR': '克罗地亚',
    'SI': '斯洛文尼亚',
    'RS': '塞尔维亚',
    'ME': '黑山',
    'BA': '波斯尼亚和黑塞哥维那',
    'MK': '北马其顿',
    'AL': '阿尔巴尼亚',
    'XK': '科索沃',
    'MT': '马耳他',
    'CY': '塞浦路斯',
    'IS': '冰岛',
    'LU': '卢森堡',
    'LI': '列支敦士登',
    'MC': '摩纳哥',
    'AD': '安道尔',
    'SM': '圣马力诺',
    'VA': '梵蒂冈',
    'SK': '斯洛伐克',
    'LT': '立陶宛',
    'LV': '拉脱维亚',
    'EE': '爱沙尼亚',
}

# 语言映射字典
LANGUAGE_DICT = {
    'cn': '粤语',
    'zh': '国语',
    'ja': '日语',
    'en': '英语',
    'ko': '韩语',
    'fr': '法语',
    'de': '德语',
    'ru': '俄语',
    'es': '西班牙语',
    'it': '意大利语',
    'pt': '葡萄牙语',
    'nl': '荷兰语',
    'sv': '瑞典语',
    'no': '挪威语',
    'da': '丹麦语',
    'fi': '芬兰语',
    'pl': '波兰语',
    'cs': '捷克语',
    'hu': '匈牙利语',
    'ro': '罗马尼亚语',
    'bg': '保加利亚语',
    'hr': '克罗地亚语',
    'sr': '塞尔维亚语',
    'sl': '斯洛文尼亚语',
    'sk': '斯洛伐克语',
    'lt': '立陶宛语',
    'lv': '拉脱维亚语',
    'et': '爱沙尼亚语',
    'tr': '土耳其语',
    'ar': '阿拉伯语',
    'he': '希伯来语',
    'fa': '波斯语',
    'ur': '乌尔都语',
    'hi': '印地语',
    'bn': '孟加拉语',
    'ta': '泰米尔语',
    'te': '泰卢固语',
    'ml': '马拉雅拉姆语',
    'kn': '卡纳达语',
    'gu': '古吉拉特语',
    'pa': '旁遮普语',
    'mr': '马拉地语',
    'or': '奥里亚语',
    'as': '阿萨姆语',
    'ne': '尼泊尔语',
    'si': '僧伽罗语',
    'my': '缅甸语',
    'km': '高棉语',
    'lo': '老挝语',
    'th': '泰语',
    'vi': '越南语',
    'id': '印尼语',
    'ms': '马来语',
    'tl': '菲律宾语',
    'mn': '蒙古语',
    'kk': '哈萨克语',
    'uz': '乌兹别克语',
    'ky': '吉尔吉斯语',
    'tg': '塔吉克语',
    'tk': '土库曼语',
    'az': '阿塞拜疆语',
    'ka': '格鲁吉亚语',
    'hy': '亚美尼亚语',
    'be': '白俄罗斯语',
    'uk': '乌克兰语',
    'mk': '马其顿语',
    'sq': '阿尔巴尼亚语',
    'mt': '马耳他语',
    'el': '希腊语',
    'is': '冰岛语',
    'fo': '法罗语',
    'ga': '爱尔兰语',
    'cy': '威尔士语',
    'eu': '巴斯克语',
    'ca': '加泰罗尼亚语',
    'gl': '加利西亚语',
    'oc': '奥克语',
    'br': '布列塔尼语',
    'co': '科西嘉语',
    'sc': '撒丁语',
    'vec': '威尼斯语',
    'fur': '弗留利语',
    'rm': '罗曼什语',
    'lad': '拉迪诺语',
    'an': '阿拉贡语',
    'ast': '阿斯图里亚斯语',
    'ext': '埃斯特雷马杜拉语',
    'mwl': '米兰德斯语',
    'roa': '罗曼语族',
    'wa': '瓦隆语',
    'pms': '皮埃蒙特语',
    'lmo': '伦巴第语',
    'eml': '艾米利亚-罗马涅语',
    'lij': '利古里亚语',
    'nap': '那不勒斯语',
    'scn': '西西里语',
    'vec': '威尼斯语',
    'fur': '弗留利语',
    'lld': '拉登语',
    'rm': '罗曼什语',
    'gsw': '瑞士德语',
    'bar': '巴伐利亚语',
    'ksh': '科隆语',
    'pfl': '普法尔茨语',
    'swg': '施瓦本语',
    'als': '阿尔萨斯语',
    'frr': '北弗里西亚语',
    'stq': '桑特弗里西亚语',
    'fy': '西弗里西亚语',
    'nds': '低地德语',
    'li': '林堡语',
    'zea': '泽兰语',
    'vls': '西佛兰德语',
    'brx': '博多语',
    'doi': '多格拉语',
    'sat': '桑塔利语',
    'mni': '曼尼普尔语',
    'bho': '博杰普尔语',
    'awa': '阿瓦德语',
    'mag': '摩揭陀语',
    'mai': '迈蒂利语',
    'raj': '拉贾斯坦语',
    'guj': '古吉拉特语',
    'pan': '旁遮普语',
    'mar': '马拉地语',
    'ori': '奥里亚语',
    'asm': '阿萨姆语',
    'nep': '尼泊尔语',
    'sin': '僧伽罗语',
    'mya': '缅甸语',
    'khm': '高棉语',
    'lao': '老挝语',
    'tha': '泰语',
    'vie': '越南语',
    'ind': '印尼语',
    'msa': '马来语',
    'tgl': '菲律宾语',
    'mon': '蒙古语',
    'kaz': '哈萨克语',
    'uzb': '乌兹别克语',
    'kir': '吉尔吉斯语',
    'tgk': '塔吉克语',
    'tuk': '土库曼语',
    'aze': '阿塞拜疆语',
    'kat': '格鲁吉亚语',
    'hye': '亚美尼亚语',
    'bel': '白俄罗斯语',
    'ukr': '乌克兰语',
    'mkd': '马其顿语',
    'sqi': '阿尔巴尼亚语',
    'mlt': '马耳他语',
    'ell': '希腊语',
    'isl': '冰岛语',
    'fao': '法罗语',
    'gle': '爱尔兰语',
    'cym': '威尔士语',
    'eus': '巴斯克语',
    'cat': '加泰罗尼亚语',
    'glg': '加利西亚语',
    'oci': '奥克语',
    'bre': '布列塔尼语',
    'cos': '科西嘉语',
    'srd': '撒丁语',
    'vec': '威尼斯语',
    'fur': '弗留利语',
    'roh': '罗曼什语',
    'lad': '拉迪诺语',
    'arg': '阿拉贡语',
    'ast': '阿斯图里亚斯语',
    'ext': '埃斯特雷马杜拉语',
    'mwl': '米兰德斯语',
    'roa': '罗曼语族',
    'wln': '瓦隆语',
    'pms': '皮埃蒙特语',
    'lmo': '伦巴第语',
    'eml': '艾米利亚-罗马涅语',
    'lij': '利古里亚语',
    'nap': '那不勒斯语',
    'scn': '西西里语',
    'vec': '威尼斯语',
    'fur': '弗留利语',
    'lld': '拉登语',
    'rm': '罗曼什语',
    'gsw': '瑞士德语',
    'bar': '巴伐利亚语',
    'ksh': '科隆语',
    'pfl': '普法尔茨语',
    'swg': '施瓦本语',
    'als': '阿尔萨斯语',
    'frr': '北弗里西亚语',
    'stq': '桑特弗里西亚语',
    'fry': '西弗里西亚语',
    'nds': '低地德语',
    'lim': '林堡语',
    'zea': '泽兰语',
    'vls': '西佛兰德语',
}

DEFAULT_COUNTRY = '其他国家'
DEFAULT_LANGUAGE = '其他语种'

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

    def save_country(self, tmdb_id, premiere_date, name, production_countries, spoken_languages):
        """保存国家数据"""
        self.data[tmdb_id] = {
            'premiere_date': premiere_date,
            'name': name,
            'production_countries': production_countries,
            'spoken_languages': spoken_languages,
            'update_date': date.today().isoformat()
        }
        self.save()

class TMDBAPI:
    """TMDB API接口类"""
    
    def __init__(self):
        self.api_key = config.get('TMDB', 'tmdb_api_key')
        self.base_url = config.get('TMDB', 'tmdb_api_base_url', fallback='https://api.themoviedb.org/3')
        
        # 检查API密钥
        if not self.api_key:
            logging.error("❌ TMDB API密钥未设置！请在config.conf的[TMDB]部分设置tmdb_api_key")
            return
        
        # 检查API密钥格式
        if not self.api_key.startswith('eyJ') and len(self.api_key) < 100:
            logging.warning("⚠️ TMDB API密钥格式可能不正确，应该是Bearer Token格式（以eyJ开头的长字符串）")
        
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        })
        
        logging.info(f"🔑 TMDB API密钥已配置: {self.api_key[:20]}...")
        logging.info(f"🌐 TMDB API基础URL: {self.base_url}")
    
    def get_movie_info(self, tmdb_id: str) -> Optional[Dict]:
        """获取电影信息"""
        if not self.api_key:
            logging.error("❌ TMDB API密钥未设置，无法请求TMDB API")
            return None
            
        try:
            url = f"{self.base_url}/movie/{tmdb_id}?language=zh-CN"
            logging.info(f"🔗 TMDB API请求URL: {url}")
            
            response = self.session.get(url, timeout=30)
            
            logging.info(f"📊 TMDB响应状态码: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"❌ TMDB API请求失败: {response.status_code}")
                logging.error(f"🔍 TMDB错误响应: {response.text[:500]}")
                return None
            
            return response.json()
                
        except Exception as e:
            logging.error(f"❌ 获取TMDB电影数据失败: {str(e)}")
            return None
    
    def get_tv_series_info(self, tmdb_id: str) -> Optional[Dict]:
        """获取电视剧信息"""
        if not self.api_key:
            logging.error("❌ TMDB API密钥未设置，无法请求TMDB API")
            return None
            
        try:
            url = f"{self.base_url}/tv/{tmdb_id}?language=zh-CN"
            logging.info(f"🔗 TMDB API请求URL: {url}")
            
            response = self.session.get(url, timeout=30)
            logging.info(f"📊 TMDB响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                logging.error(f"❌ TMDB API请求失败: {response.status_code}")
                logging.error(f"🔍 TMDB错误响应: {response.text[:500]}")
                return None
            
            return response.json()
                
        except Exception as e:
            logging.error(f"❌ 获取TMDB电视剧数据失败: {str(e)}")
            return None

class Get_Detail:
    """国家标签抓取器主类"""
    
    def __init__(self):
        # 从配置文件获取配置
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.emby_user_id = config.get('Extra', 'emby_user_id', fallback=None)
        self.library_names = config.get('CountryScraper', 'library_names', fallback='').split(',')
        self.dry_run = config.getboolean('CountryScraper', 'dry_run', fallback=True)
        
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
        self.tmdb_db = TmdbDataBase('tmdb_countries', 'country_scraper')
        
        self.process_count = 0
    
    def get_or_default(self, _dict, key, default=None):
        """安全获取字典值"""
        return _dict.get(key, default)
    
    def get_country_info_from_tmdb(self, tmdb_id: str, series_name: str, is_movie: bool = False):
        """从TMDB获取国家信息"""
        cache_key = ('mv' if is_movie else 'tv') + f'{tmdb_id}'
        cache_data = self.tmdb_db[cache_key]
        
        if cache_data and 'production_countries' in cache_data:
            production_countries = cache_data["production_countries"]
            spoken_languages = cache_data["spoken_languages"]
            return production_countries, spoken_languages, True
        
        try:
            if is_movie:
                resp_json = self.tmdb_api.get_movie_info(tmdb_id)
            else:
                resp_json = self.tmdb_api.get_tv_series_info(tmdb_id)
            
            if not resp_json:
                return None, None, None
            
            if "production_countries" in resp_json or "spoken_languages" in resp_json:
                production_countries = resp_json.get("production_countries", [])
                spoken_languages = resp_json.get("spoken_languages", [])
                
                release_date = self.get_or_default(resp_json, 'release_date') if is_movie else self.get_or_default(
                    resp_json, 'last_air_date', default=self.get_or_default(resp_json, 'first_air_date')
                )
                
                self.tmdb_db.save_country(
                    cache_key, 
                    premiere_date=release_date, 
                    name=series_name, 
                    production_countries=production_countries, 
                    spoken_languages=spoken_languages
                )
                return production_countries, spoken_languages, False
            else:
                logging.error(f"❌ TMDB中未找到国家信息: {series_name}")
                return None, None, None
                
        except Exception as e:
            logging.error(f"❌ 获取TMDB国家数据失败: {str(e)}")
            return None, None, None
    
    def add_country_tags(self, parent_id: str, tmdb_id: str, series_name: str, is_movie: bool = False):
        """添加国家标签"""
        production_countries, spoken_languages, is_cache = self.get_country_info_from_tmdb(
            tmdb_id, series_name, is_movie=is_movie
        )
        from_cache = ' (缓存)' if is_cache else ''
        
        if not production_countries and not spoken_languages:
            if not self.dry_run:
                logging.info(f"📋 {series_name}{from_cache} 没有设置国家，跳过")
            return
        
        # 获取项目详细信息
        item_url = f"{self.emby_server}/emby/Users/{self.emby_user_id}/Items/{parent_id}?Fields=ChannelMappingInfo&api_key={self.emby_api_key}"
        response = requests.get(item_url)
        if response.status_code != 200:
            logging.error(f"❌ 获取项目详情失败: {response.status_code}")
            return
        
        item = response.json()
        series_name = item['Name']
        old_tags = item.get('TagItems', [])
        old_tags = [tag['Name'] for tag in old_tags]
        new_tags = old_tags[:]
        
        # 处理国家标签
        tmdb_countries = []
        for country in production_countries:
            tag = self.get_or_default(COUNTRY_DICT, country['iso_3166_1'], DEFAULT_COUNTRY)
            if tag not in tmdb_countries:
                tmdb_countries.append(tag)
        
        for country in tmdb_countries:
            if country not in new_tags:
                if country != DEFAULT_COUNTRY or len(tmdb_countries) <= 2:
                    new_tags.append(country)
        
        # 处理语言标签
        tmdb_languages = []
        for language in spoken_languages:
            tag = self.get_or_default(LANGUAGE_DICT, language['iso_639_1'], DEFAULT_LANGUAGE)
            if tag not in tmdb_languages:
                tmdb_languages.append(tag)
        
        for language in tmdb_languages:
            if language not in new_tags:
                if language != DEFAULT_LANGUAGE or len(tmdb_languages) <= 2:
                    new_tags.append(language)
        
        if new_tags == old_tags:
            if not self.dry_run:
                logging.info(f"📋 {series_name}{from_cache} 标签没有变化，跳过")
            return
        else:
            logging.info(f"🔄 {series_name}{from_cache} 设置标签为 {new_tags}")
        
        item['Tags'] = new_tags
        if 'TagItems' not in item:
            item['TagItems'] = []
        
        for tag in new_tags:
            if tag not in old_tags:
                item['TagItems'].append({'Name': tag})
        
        if 'LockedFields' not in item:
            item['LockedFields'] = []
        if 'Tags' not in item['LockedFields']:
            item['LockedFields'].append('Tags')
        
        if not self.dry_run:
            update_url = f"{self.emby_server}/emby/Items/{parent_id}?api_key={self.emby_api_key}&reqformat=json"
            update_response = requests.post(update_url, json=item)
            
            if update_response.status_code in [200, 204]:
                self.process_count += 1
                logging.info(f"✅ 成功更新 {series_name} 的标签")
            else:
                logging.error(f"❌ 更新失败 {series_name}: {update_response.status_code}")
    
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
        """运行抓取器"""
        logging.info("🚀 开始运行国家标签抓取器")
        
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
                
                # 只处理电影和电视剧
                if item['Type'] not in ['Movie', 'Series']:
                    logging.debug(f"⏭️ 跳过非电影/电视剧项目: {item_name} (类型: {item['Type']})")
                    continue
                
                logging.info(f"🎬 处理项目: {item_name} (TMDB: {tmdb_id})")
                self.add_country_tags(item_id, tmdb_id, item_name, is_movie)
        
        logging.info(f"✅ 国家标签抓取器运行完成，处理了 {self.process_count} 个项目")

if __name__ == "__main__":
    logging.info("执行单次任务")
    gd = Get_Detail()
    gd.run() 