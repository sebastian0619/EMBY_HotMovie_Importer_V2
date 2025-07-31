#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 媒体导入器主控制器
支持动态导入和配置不同的导入器组件
"""
import os
import sys
import importlib
import logging
import csv
from configparser import ConfigParser
from typing import List, Dict, Any
import time
import schedule
from datetime import datetime
from croniter import croniter
import requests
import threading
import fcntl
import tempfile
import pytz

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('emby_importer.log'),
        logging.StreamHandler()
    ]
)

class TaskLock:
    """任务锁，防止多个进程同时运行"""
    def __init__(self, lock_file='/tmp/emby_importer.lock'):
        self.lock_file = lock_file
        self.lock_fd = None
    
    def acquire(self):
        """获取锁"""
        try:
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            logging.info("🔒 成功获取任务锁")
            return True
        except (IOError, OSError):
            logging.warning("⚠️ 任务已在运行中，跳过本次执行")
            return False
    
    def release(self):
        """释放锁"""
        if self.lock_fd:
            try:
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
                logging.info("🔓 释放任务锁")
            except:
                pass

class ImporterController:
    def __init__(self):
        self.config = self._load_config()
        self.importers = self._load_importers()
        self.task_lock = TaskLock()
        self.schedules = self._load_schedules()
        self.timezone = self._get_timezone()
    
    def _get_timezone(self):
        """获取时区配置"""
        # 优先从环境变量获取
        tz_env = os.environ.get('TZ')
        if tz_env:
            try:
                return pytz.timezone(tz_env)
            except pytz.exceptions.UnknownTimeZoneError:
                logging.warning(f"⚠️ 环境变量TZ指定的时区无效: {tz_env}")
        
        # 从配置文件获取
        tz_config = self.config.get('Schedule', 'timezone', fallback='Asia/Shanghai')
        try:
            return pytz.timezone(tz_config)
        except pytz.exceptions.UnknownTimeZoneError:
            logging.warning(f"⚠️ 配置文件指定的时区无效: {tz_config}，使用默认时区")
            return pytz.timezone('Asia/Shanghai')
    
    def _load_config(self) -> ConfigParser:
        """加载配置文件"""
        config = ConfigParser()
        config.read('config.conf')
        logging.info("📋 主控制器配置文件加载成功")
        return config
    
    def _load_importers(self) -> Dict[str, Any]:
        """动态加载启用的导入器"""
        importers = {}
        available_importers = {
            'hotmovie': {'module': 'EMBY_HotMovie_Importer', 'class': 'Get_Detail', 'enabled': self.config.getboolean('Importers', 'enable_hotmovie', fallback=True), 'description': '热门电影导入器'},
            'bangumi': {'module': 'EMBY_Bangumi_Importer', 'class': 'Get_Detail', 'enabled': self.config.getboolean('Importers', 'enable_bangumi', fallback=False), 'description': 'Bangumi导入器'},
            'doulist': {'module': 'EMBY_Doulist_Importer', 'class': 'Get_Detail', 'enabled': self.config.getboolean('Importers', 'enable_doulist', fallback=False), 'description': '豆列导入器'},
            'season_renamer': {'module': 'EMBY_Season_Renamer', 'class': 'Get_Detail', 'enabled': self.config.getboolean('Importers', 'enable_season_renamer', fallback=False), 'description': '季节重命名器'},
            'country_scraper': {'module': 'EMBY_Country_Scraper', 'class': 'Get_Detail', 'enabled': self.config.getboolean('Importers', 'enable_country_scraper', fallback=False), 'description': '国家标签抓取器'}
        }
        
        for importer_name, importer_config in available_importers.items():
            if importer_config['enabled']:
                try:
                    module = importlib.import_module(importer_config['module'])
                    importer_class = getattr(module, importer_config['class'])
                    importers[importer_name] = {
                        'class': importer_class,
                        'description': importer_config['description']
                    }
                    logging.info(f"✅ 成功加载导入器: {importer_name} - {importer_config['description']}")
                except ImportError as e:
                    logging.error(f"❌ 导入器模块加载失败 {importer_name}: {str(e)}")
                except AttributeError as e:
                    logging.error(f"❌ 导入器类加载失败 {importer_name}: {str(e)}")
                except Exception as e:
                    logging.error(f"❌ 导入器加载异常 {importer_name}: {str(e)}")
        
        return importers
    
    def _load_schedules(self) -> Dict[str, str]:
        """加载各导入器的调度配置"""
        schedules = {}
        global_cron = self.config.get('Schedule', 'global_cron', fallback='0 3 * * *')
        
        # 导入器调度配置映射
        schedule_mapping = {
            'hotmovie': 'HotMovie_cron',
            'bangumi': 'Bangumi_cron', 
            'doulist': 'Doulist_cron',
            'season_renamer': 'SeasonRenamer_cron',
            'country_scraper': 'CountryScraper_cron'
        }
        
        for importer_name, cron_key in schedule_mapping.items():
            cron = self.config.get('Schedule', cron_key, fallback='').strip()
            if cron:
                schedules[importer_name] = cron
                logging.info(f"⏰ {importer_name} 使用自定义调度: {cron}")
            else:
                schedules[importer_name] = global_cron
                logging.info(f"⏰ {importer_name} 使用全局调度: {global_cron}")
        
        return schedules
    
    def run_importer(self, importer_name: str) -> bool:
        """运行指定的导入器"""
        if importer_name not in self.importers:
            logging.error(f"❌ 导入器不存在: {importer_name}")
            return False
        
        try:
            logging.info(f"🚀 开始运行导入器: {importer_name}")
            logging.info(f"📋 导入器描述: {self.importers[importer_name]['description']}")
            logging.info("=" * 60)
            
            start_time = time.time()
            importer_class = self.importers[importer_name]['class']
            importer_instance = importer_class()
            importer_instance.run()
            
            end_time = time.time()
            duration = end_time - start_time
            
            logging.info("=" * 60)
            logging.info(f"✅ 导入器运行完成: {importer_name} (耗时: {duration:.2f}秒)")
            return True
        except Exception as e:
            logging.error(f"❌ 导入器运行失败 {importer_name}: {str(e)}")
            return False
    
    def _check_emby_status(self) -> bool:
        """检查 Emby 服务器状态"""
        try:
            emby_server = self.config.get('Server', 'emby_server')
            emby_api_key = self.config.get('Server', 'emby_api_key')
            
            # 测试系统信息
            system_url = f"{emby_server}/emby/System/Info?api_key={emby_api_key}"
            response = requests.get(system_url, timeout=10)
            
            if response.status_code == 200:
                logging.info("✅ Emby 服务器状态正常")
                return True
            else:
                logging.error(f"❌ Emby 服务器状态异常: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"❌ 检查 Emby 状态失败: {str(e)}")
            return False
    
    def _init_csv_file(self):
        """初始化CSV文件（在每轮运行开始时清空并写入表头）"""
        try:
            csv_file_path = self.config.get('Output', 'csv_file_path', fallback='./missing_movies.csv')
            
            # 清空文件并写入表头
            with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['importer', 'collection_name', 'movie_name', 'year', 'reason', 'timestamp']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            
            logging.info(f"📝 CSV文件已清空并重新初始化: {csv_file_path}")
        except Exception as e:
            logging.error(f"❌ 初始化CSV文件失败: {str(e)}")

    def run_all_importers(self) -> Dict[str, bool]:
        """顺序运行所有启用的导入器"""
        results = {}
        logging.info("🚀 开始顺序运行所有导入器")
        
        # 先检查 Emby 服务器状态
        if not self._check_emby_status():
            logging.error("❌ Emby 服务器状态异常，跳过所有导入器")
            return {name: False for name in self.importers.keys()}
        
        # 在开始运行所有导入器之前，清空CSV文件
        self._init_csv_file()
        
        # 按顺序运行导入器
        for importer_name in self.importers.keys():
            logging.info(f"🔄 准备运行导入器: {importer_name}")
            result = self.run_importer(importer_name)
            results[importer_name] = result
            
            if result:
                logging.info(f"✅ 导入器 {importer_name} 成功完成")
            else:
                logging.error(f"❌ 导入器 {importer_name} 运行失败")
            
            # 在导入器之间添加短暂延迟，避免对Emby服务器造成过大压力
            if list(self.importers.keys()).index(importer_name) < len(self.importers) - 1:
                logging.info("⏳ 等待5秒后运行下一个导入器...")
                time.sleep(5)
        
        # 统计结果
        success_count = sum(results.values())
        total_count = len(results)
        logging.info(f"🎯 所有导入器运行完成: {success_count}/{total_count} 成功")
        
        return results
    
    def run_scheduled_task(self):
        """定时任务执行函数（所有导入器）"""
        logging.info("⏰ 开始执行定时任务")
        
        # 尝试获取任务锁
        if not self.task_lock.acquire():
            logging.warning("⚠️ 检测到任务已在运行，跳过本次定时任务")
            return
        
        try:
            self.run_all_importers()
        except Exception as e:
            logging.error(f"❌ 执行任务时发生错误: {str(e)}")
        finally:
            # 确保释放锁
            self.task_lock.release()
        
        logging.info("⏰ 定时任务执行完成")
    
    def run_single_importer_task(self, importer_name: str):
        """运行单个导入器的定时任务"""
        logging.info(f"⏰ 开始执行 {importer_name} 定时任务")
        
        # 尝试获取任务锁
        if not self.task_lock.acquire():
            logging.warning(f"⚠️ 检测到任务已在运行，跳过 {importer_name} 定时任务")
            return
        
        try:
            success = self.run_importer(importer_name)
            if success:
                logging.info(f"✅ {importer_name} 定时任务执行完成")
            else:
                logging.error(f"❌ {importer_name} 定时任务执行失败")
        except Exception as e:
            logging.error(f"❌ {importer_name} 执行任务时发生错误: {str(e)}")
        finally:
            # 确保释放锁
            self.task_lock.release()
        
        logging.info(f"⏰ {importer_name} 定时任务执行完成")

def main():
    """主函数"""
    controller = ImporterController()
    
    # 检查是否有启用的导入器
    if not controller.importers:
        logging.error("❌ 没有启用的导入器，请检查配置文件")
        sys.exit(1)
    
    # 检查是否有启用的调度
    has_schedule = any(controller.schedules.values())
    
    if has_schedule:
        logging.info("🔄 启动守护模式")
        
        # 启动时立即执行一次全量任务
        logging.info("🚀 程序启动，立即执行一次全量任务")
        try:
            controller.run_all_importers()
            logging.info("✅ 首次全量任务执行完成")
        except Exception as e:
            logging.error(f"❌ 首次全量任务执行失败: {str(e)}")
        
        # 进入守护模式
        logging.info("🔄 进入守护模式，等待下次定时执行...")
        
        # 为每个导入器设置单独的调度
        for importer_name, cron_expression in controller.schedules.items():
            if importer_name in controller.importers and cron_expression:
                try:
                    # 检查cron表达式是否为空
                    if not cron_expression or cron_expression.strip() == '':
                        logging.warning(f"⚠️ {importer_name} 未配置cron表达式，跳过调度")
                        continue
                    
                    # 获取当前UTC时间，然后转换为目标时区
                    now_utc = datetime.utcnow()
                    now = controller.timezone.fromutc(now_utc)
                    
                    # 解析cron表达式（使用UTC时间）
                    cron = croniter(cron_expression, now_utc)
                    next_run_utc = cron.get_next(datetime)
                    
                    # 转换为目标时区
                    next_run = controller.timezone.fromutc(next_run_utc)
                    
                    logging.info(f"⏰ {importer_name} 调度: {cron_expression}")
                    logging.info(f"⏰ {importer_name} 时区: {controller.timezone}")
                    logging.info(f"⏰ {importer_name} 下次运行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    
                    # 设置定时任务
                    # 根据cron表达式设置不同的调度
                    if cron_expression.startswith('0 */'):
                        # 每小时执行
                        hour_interval = int(cron_expression.split()[1].replace('*/', ''))
                        schedule.every(hour_interval).hours.do(
                            controller.run_single_importer_task, importer_name
                        )
                        logging.info(f"⏰ {importer_name} 设置为每{hour_interval}小时执行一次")
                    elif cron_expression.startswith('0 0 */'):
                        # 每天执行
                        day_interval = int(cron_expression.split()[2].replace('*/', ''))
                        schedule.every(day_interval).days.do(
                            controller.run_single_importer_task, importer_name
                        )
                        logging.info(f"⏰ {importer_name} 设置为每{day_interval}天执行一次")
                    else:
                        # 默认每天执行
                        schedule.every().day.at(next_run.strftime("%H:%M")).do(
                            controller.run_single_importer_task, importer_name
                        )
                        logging.info(f"⏰ {importer_name} 设置为每天{next_run.strftime('%H:%M')}执行")
                    
                except Exception as e:
                    logging.error(f"❌ {importer_name} cron表达式解析失败: {str(e)}")
        
        # 主循环
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # 每30秒检查一次
            except KeyboardInterrupt:
                logging.info("🛑 收到退出信号，程序退出")
                break
            except Exception as e:
                logging.error(f"❌ 运行出错: {str(e)}")
                time.sleep(60)  # 出错后等待1分钟再继续
    else:
        logging.info("🚀 执行单次任务")
        controller.run_all_importers()

if __name__ == "__main__":
    main() 