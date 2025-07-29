#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV文件管理工具
用于查看和管理missing_movies.csv文件
"""
import os
import csv
import pandas as pd
from datetime import datetime
from configparser import ConfigParser
import argparse

def load_config():
    """加载配置文件"""
    config = ConfigParser()
    config.read('config.conf')
    return config

def view_csv():
    """查看CSV文件内容"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV文件不存在: {csv_file_path}")
        return
    
    try:
        # 使用pandas读取CSV文件
        df = pd.read_csv(csv_file_path)
        
        print(f"📊 CSV文件统计信息:")
        print(f"📁 文件路径: {csv_file_path}")
        print(f"📈 总记录数: {len(df)}")
        print(f"📅 最后修改: {datetime.fromtimestamp(os.path.getmtime(csv_file_path))}")
        
        if len(df) > 0:
            print(f"\n📋 按导入器统计:")
            importer_stats = df['导入器'].value_counts()
            for importer, count in importer_stats.items():
                print(f"  {importer}: {count} 条记录")
            
            print(f"\n📋 按合集统计 (前10个):")
            collection_stats = df['合集名称'].value_counts().head(10)
            for collection, count in collection_stats.items():
                print(f"  {collection}: {count} 条记录")
            
            print(f"\n📋 最新记录 (前10条):")
            print(df.tail(10).to_string(index=False))
        else:
            print("📭 CSV文件为空")
            
    except Exception as e:
        print(f"❌ 读取CSV文件失败: {str(e)}")

def export_by_importer(importer_name):
    """按导入器导出CSV"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV文件不存在: {csv_file_path}")
        return
    
    try:
        df = pd.read_csv(csv_file_path)
        
        # 过滤指定导入器的记录
        filtered_df = df[df['导入器'] == importer_name]
        
        if len(filtered_df) == 0:
            print(f"❌ 未找到导入器 '{importer_name}' 的记录")
            return
        
        # 导出到新文件
        output_file = f"missing_movies_{importer_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filtered_df.to_csv(output_file, index=False, encoding='utf-8')
        
        print(f"✅ 成功导出 {len(filtered_df)} 条记录到: {output_file}")
        
    except Exception as e:
        print(f"❌ 导出失败: {str(e)}")

def export_by_collection(collection_name):
    """按合集导出CSV"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV文件不存在: {csv_file_path}")
        return
    
    try:
        df = pd.read_csv(csv_file_path)
        
        # 过滤指定合集的记录
        filtered_df = df[df['合集名称'] == collection_name]
        
        if len(filtered_df) == 0:
            print(f"❌ 未找到合集 '{collection_name}' 的记录")
            return
        
        # 导出到新文件
        output_file = f"missing_movies_{collection_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filtered_df.to_csv(output_file, index=False, encoding='utf-8')
        
        print(f"✅ 成功导出 {len(filtered_df)} 条记录到: {output_file}")
        
    except Exception as e:
        print(f"❌ 导出失败: {str(e)}")

def clear_csv():
    """清空CSV文件"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV文件不存在: {csv_file_path}")
        return
    
    try:
        # 备份原文件
        backup_file = f"{csv_file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.rename(csv_file_path, backup_file)
        
        # 创建新的空文件
        with open(csv_file_path, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['电影名称', '年份', '合集名称', '导入器', '记录时间'])
        
        print(f"✅ 成功清空CSV文件")
        print(f"📁 原文件已备份到: {backup_file}")
        
    except Exception as e:
        print(f"❌ 清空失败: {str(e)}")

def backup_csv():
    """备份CSV文件"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV文件不存在: {csv_file_path}")
        return
    
    try:
        # 创建备份文件
        backup_file = f"{csv_file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        import shutil
        shutil.copy2(csv_file_path, backup_file)
        
        print(f"✅ 成功备份CSV文件")
        print(f"📁 备份文件: {backup_file}")
        
    except Exception as e:
        print(f"❌ 备份失败: {str(e)}")

def reset_csv():
    """重置CSV文件（清空但不备份）"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    try:
        # 直接创建新的空文件
        with open(csv_file_path, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['电影名称', '年份', '合集名称', '导入器', '记录时间'])
        
        print(f"✅ 成功重置CSV文件")
        print(f"📁 文件路径: {csv_file_path}")
        
    except Exception as e:
        print(f"❌ 重置失败: {str(e)}")

def search_csv(keyword):
    """搜索CSV文件"""
    config = load_config()
    csv_file_path = config.get('Output', 'csv_file_path')
    
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV文件不存在: {csv_file_path}")
        return
    
    try:
        df = pd.read_csv(csv_file_path)
        
        # 在所有文本列中搜索关键词
        mask = df.apply(lambda x: x.astype(str).str.contains(keyword, case=False, na=False)).any(axis=1)
        filtered_df = df[mask]
        
        if len(filtered_df) == 0:
            print(f"❌ 未找到包含关键词 '{keyword}' 的记录")
            return
        
        print(f"🔍 找到 {len(filtered_df)} 条包含关键词 '{keyword}' 的记录:")
        print(filtered_df.to_string(index=False))
        
    except Exception as e:
        print(f"❌ 搜索失败: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='CSV文件管理工具')
    parser.add_argument('action', choices=['view', 'export-importer', 'export-collection', 'clear', 'backup', 'reset', 'search'], 
                       help='操作类型')
    parser.add_argument('--name', help='导入器名称或合集名称')
    parser.add_argument('--keyword', help='搜索关键词')
    
    args = parser.parse_args()
    
    if args.action == 'view':
        view_csv()
    elif args.action == 'export-importer':
        if not args.name:
            print("❌ 请指定导入器名称: --name <导入器名称>")
            return
        export_by_importer(args.name)
    elif args.action == 'export-collection':
        if not args.name:
            print("❌ 请指定合集名称: --name <合集名称>")
            return
        export_by_collection(args.name)
    elif args.action == 'clear':
        clear_csv()
    elif args.action == 'backup':
        backup_csv()
    elif args.action == 'reset':
        reset_csv()
    elif args.action == 'search':
        if not args.keyword:
            print("❌ 请指定搜索关键词: --keyword <关键词>")
            return
        search_csv(args.keyword)

if __name__ == "__main__":
    main() 