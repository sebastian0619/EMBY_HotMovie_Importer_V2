#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
名称映射管理工具
用于管理配置文件中的名称映射规则
"""
import os
import argparse
from configparser import ConfigParser

def load_config():
    """加载配置文件"""
    config = ConfigParser()
    config.read('config.conf')
    return config

def save_config(config):
    """保存配置文件"""
    with open('config.conf', 'w', encoding='utf-8') as f:
        config.write(f)

def view_mappings():
    """查看当前名称映射"""
    config = load_config()
    
    if not config.has_section('NameMapping'):
        print("❌ 配置文件中没有 [NameMapping] 部分")
        return
    
    mappings = dict(config.items('NameMapping'))
    
    if not mappings:
        print("📭 没有配置任何名称映射")
        return
    
    print("📋 当前名称映射:")
    print("=" * 50)
    for original, mapped in mappings.items():
        print(f"  {original} → {mapped}")
    print("=" * 50)
    print(f"总计: {len(mappings)} 条映射规则")

def add_mapping(original, mapped):
    """添加名称映射"""
    config = load_config()
    
    # 确保NameMapping部分存在
    if not config.has_section('NameMapping'):
        config.add_section('NameMapping')
    
    # 添加映射
    config.set('NameMapping', original, mapped)
    save_config(config)
    
    print(f"✅ 成功添加映射: {original} → {mapped}")

def remove_mapping(original):
    """删除名称映射"""
    config = load_config()
    
    if not config.has_section('NameMapping'):
        print("❌ 配置文件中没有 [NameMapping] 部分")
        return
    
    if not config.has_option('NameMapping', original):
        print(f"❌ 未找到映射: {original}")
        return
    
    # 获取当前映射值用于显示
    mapped = config.get('NameMapping', original)
    
    # 删除映射
    config.remove_option('NameMapping', original)
    save_config(config)
    
    print(f"✅ 成功删除映射: {original} → {mapped}")

def clear_mappings():
    """清空所有名称映射"""
    config = load_config()
    
    if not config.has_section('NameMapping'):
        print("❌ 配置文件中没有 [NameMapping] 部分")
        return
    
    mappings = dict(config.items('NameMapping'))
    
    if not mappings:
        print("📭 没有配置任何名称映射")
        return
    
    # 删除整个NameMapping部分
    config.remove_section('NameMapping')
    save_config(config)
    
    print(f"✅ 成功清空所有名称映射 ({len(mappings)} 条)")

def search_mapping(keyword):
    """搜索名称映射"""
    config = load_config()
    
    if not config.has_section('NameMapping'):
        print("❌ 配置文件中没有 [NameMapping] 部分")
        return
    
    mappings = dict(config.items('NameMapping'))
    
    if not mappings:
        print("📭 没有配置任何名称映射")
        return
    
    # 搜索匹配的映射
    matched = []
    for original, mapped in mappings.items():
        if keyword.lower() in original.lower() or keyword.lower() in mapped.lower():
            matched.append((original, mapped))
    
    if not matched:
        print(f"❌ 未找到包含关键词 '{keyword}' 的映射")
        return
    
    print(f"🔍 找到 {len(matched)} 条包含关键词 '{keyword}' 的映射:")
    print("=" * 50)
    for original, mapped in matched:
        print(f"  {original} → {mapped}")
    print("=" * 50)

def main():
    parser = argparse.ArgumentParser(description='名称映射管理工具')
    parser.add_argument('action', choices=['view', 'add', 'remove', 'clear', 'search'], 
                       help='操作类型')
    parser.add_argument('--original', help='原始名称')
    parser.add_argument('--mapped', help='映射后的名称')
    parser.add_argument('--keyword', help='搜索关键词')
    
    args = parser.parse_args()
    
    if args.action == 'view':
        view_mappings()
    elif args.action == 'add':
        if not args.original or not args.mapped:
            print("❌ 添加映射需要指定 --original 和 --mapped 参数")
            return
        add_mapping(args.original, args.mapped)
    elif args.action == 'remove':
        if not args.original:
            print("❌ 删除映射需要指定 --original 参数")
            return
        remove_mapping(args.original)
    elif args.action == 'clear':
        clear_mappings()
    elif args.action == 'search':
        if not args.keyword:
            print("❌ 搜索需要指定 --keyword 参数")
            return
        search_mapping(args.keyword)

if __name__ == "__main__":
    main() 