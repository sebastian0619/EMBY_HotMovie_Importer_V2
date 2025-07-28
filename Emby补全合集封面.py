import requests
import os
import base64
from configparser import ConfigParser
from tqdm import tqdm
import logging
import json

# 用子项目的封面填充父项目的封面

# 比如：合集库，随着资源的积累，你会发现这个库内有1000多个合集项目。
# 但是，并不一定每个合集都有海报和背景图，难受
# 你懒，不可能去TMDB挨个添加完善每个缺失封面的合集，
# 更不可能自己挨个编辑合集的封面图和海报。
# 这个脚本就是用来做这个的
# 它可以扫描检测整个库内没有海报背景图的合集
# 然后用该合集内的电影的图片，作为合集海报和背景图
# 有点绕？
# 比如 【钢铁侠系列】这个合集，没有合集海报和背景图
# 该合集下 有 钢铁侠1、钢铁侠2、钢铁侠3，3部电影，
# 这些电影是有封面海报的
# 随机抽取一部，比如钢铁侠1的海报和背景图
# 作为【钢铁侠】这个合集的海报和背景图

# 这样就能完美补全所有合集的封面和背景图了

config = ConfigParser()

with open('EMBY_HotMovie_Importer.conf', encoding='utf-8') as f:
    config.read_file(f)

# 从配置文件中读取 Emby 和代理信息
EMBY_SERVER = config.get('Server', 'emby_server')
EMBY_API_KEY = config.get('Server', 'emby_api_key')

# 设置代理（如果启用）
use_proxy = config.getboolean('Proxy', 'use_proxy', fallback=False)
if use_proxy:
    os.environ['http_proxy'] = config.get('Proxy', 'http_proxy', fallback='http://127.0.0.1:7890')
    os.environ['https_proxy'] = config.get('Proxy', 'https_proxy', fallback='http://127.0.0.1:7890')
else:
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)

logging.basicConfig(filename='Watcher.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# 超时时间设置（秒）
REQUEST_TIMEOUT = 10

def get_heji_id_by_name(emby_server, api_key, name='合集'):
    url = f"{emby_server}/emby/Items"
    params = {
        'IncludeItemTypes': 'CollectionFolder',
        'Recursive': 'true',
        'SearchTerm': name,
        'api_key': api_key
    }
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        items = response.json().get('Items', [])
        for item in items:
            if item['Name'] == name:
                logging.info(f"找到合集库 '{name}'，ID: {item['Id']}")
                return item['Id']
        raise Exception(f"找不到合集库名称: {name}")
    except requests.RequestException as e:
        logging.error(f"获取合集库 ID 失败: {e}")
        raise

HEJI = get_heji_id_by_name(EMBY_SERVER, EMBY_API_KEY)

def has_image_type(item_id, imgtype):
    url = f"{EMBY_SERVER}/emby/Items/{item_id}/Images?api_key={EMBY_API_KEY}"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        has_image = imgtype.lower() in [img['ImageType'].lower() for img in data]
        logging.info(f"检查项目 {item_id} 的 {imgtype} 图片: {'存在' if has_image else '不存在'}")
        return has_image
    except requests.RequestException as e:
        logging.error(f"检查项目 {item_id} 的 {imgtype} 图片失败: {e}")
        return False

def get_movies(params):
    items = []
    params["StartIndex"] = 0
    while True:
        try:
            response = requests.get(f"{EMBY_SERVER}/emby/Items", params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            items.extend(data["Items"])
            if len(items) >= data["TotalRecordCount"]:
                break
            params["StartIndex"] += params["Limit"]
        except requests.RequestException as e:
            logging.error(f"获取合集失败: {e}")
            return []
    return [item["Id"] for item in items]

def get_children(parent_id):
    try:
        response = requests.get(
            f"{EMBY_SERVER}/emby/Items",
            params={"Recursive": "true", "ParentId": parent_id, "SortBy": "SortName", "api_key": EMBY_API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        children_ids = [item["Id"] for item in response.json()["Items"]]
        logging.info(f"合集 {parent_id} 包含 {len(children_ids)} 个子项目")
        return children_ids
    except requests.RequestException as e:
        logging.error(f"获取合集 {parent_id} 的子项目失败: {e}")
        return []

def get_movies_without_backdrop(imgtype):
    params = {
        "Limit": 200,
        "ParentId": HEJI,
        "Recursive": True,
        "SortBy": "SortName",  # 使用稳定排序
        "api_key": EMBY_API_KEY
    }
    movies = get_movies(params)
    movies_without_image = []
    for movie_id in movies:
        if not has_image_type(movie_id, imgtype):
            movies_without_image.append(movie_id)
    logging.info(f"找到 {len(movies_without_image)} 个缺少 {imgtype} 的合集")
    return movies_without_image

def update_config_json(collection_id, collection_name):
    config_json_path = 'config.json'
    try:
        with open(config_json_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        config_data = {"emby_servers": [{"name": "Default Emby", "host": EMBY_SERVER, "api_key": EMBY_API_KEY}]}
    
    if 'collections' not in config_data:
        config_data['collections'] = []
    
    for collection in config_data['collections']:
        if collection['name'] == collection_name:
            collection['box_id'] = collection_id
            break
    else:
        config_data['collections'].append({'name': collection_name, 'box_id': collection_id})
    
    with open(config_json_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)
    logging.info(f"已更新 config.json，合集 '{collection_name}' ID: {collection_id}")
    print(f"已更新 config.json，合集 '{collection_name}' ID: {collection_id}")

def get_children_ids_without_backdrop(parent_ids, imgtype):
    with tqdm(total=len(parent_ids), desc='总进度') as pbar:
        for parent_id in parent_ids:
            # 获取合集名称用于 config.json
            try:
                response = requests.get(
                    f"{EMBY_SERVER}/emby/Items/{parent_id}?api_key={EMBY_API_KEY}",
                    timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                collection_name = response.json().get('Name', f"合集_{parent_id}")
            except requests.RequestException as e:
                logging.error(f"获取合集 {parent_id} 名称失败: {e}")
                collection_name = f"合集_{parent_id}"

            children = get_children(parent_id)
            if children:
                for child_id in children:
                    image_url = f"{EMBY_SERVER}/emby/Items/{child_id}/Images/{imgtype}?api_key={EMBY_API_KEY}"
                    try:
                        image_response = requests.get(image_url, timeout=REQUEST_TIMEOUT)
                        if 'image' in image_response.headers.get('Content-Type', ''):
                            parent_backdrop_url = f"{EMBY_SERVER}/emby/Items/{parent_id}/Images/{imgtype}"
                            parent_image_response = requests.get(parent_backdrop_url, timeout=REQUEST_TIMEOUT)
                            if 'image' not in parent_image_response.headers.get('Content-Type', ''):
                                image_content = image_response.content
                                base64_image = base64.b64encode(image_content).decode('utf-8')
                                url = f"{EMBY_SERVER}/emby/Items/{parent_id}/Images/{imgtype}"
                                headers = {
                                    'Content-Type': 'image/jpeg',
                                    'X-Emby-Token': EMBY_API_KEY
                                }
                                response = requests.post(url, headers=headers, data=base64_image, timeout=REQUEST_TIMEOUT)
                                if response.status_code == 204:
                                    logging.info(f"成功更新父项目 {parent_id} 的 {imgtype} 图片")
                                    print(f"成功更新父项目 {parent_id} 的 {imgtype} 图片")
                                    # 更新 config.json
                                    # update_config_json(parent_id, collection_name)
                                else:
                                    logging.warning(f"父项目 {parent_id} 的 {imgtype} 图片更新失败")
                            break
                    except requests.RequestException as e:
                        logging.error(f"获取子项目 {child_id} 的 {imgtype} 图片失败: {e}")
                else:
                    logging.warning(f"合集 {parent_id} 的子项目均无 {imgtype} 图片")
            pbar.update(1)

# 主循环：依次处理 Primary 和 Backdrop
for imgtype in ["Primary", "Backdrop"]:
    print(f"\n====== 处理类型: {imgtype} ======")
    logging.info(f"开始处理 {imgtype}")
    prev_movies_count = float("inf")
    while True:
        print(f"开始补全合集 {imgtype}，检测没有该图的项目:")
        logging.info(f"开始补全合集 {imgtype}，检测没有该图的项目")
        movies_without_backdrop_ids = get_movies_without_backdrop(imgtype)
        print(f"没有 {imgtype} 的项目数量: {len(movies_without_backdrop_ids)}")
        logging.info(f"没有 {imgtype} 的项目数量: {len(movies_without_backdrop_ids)}")
        if not movies_without_backdrop_ids:
            print(f"所有项目都已经有 {imgtype} 了")
            logging.info(f"所有项目都已经有 {imgtype} 了，跳过该类型")
            break
        if len(movies_without_backdrop_ids) == prev_movies_count:
            print(f"{imgtype} 的缺失数量未变化，退出循环")
            logging.info(f"{imgtype} 的缺失数量未变化，退出循环")
            break
        prev_movies_count = len(movies_without_backdrop_ids)
        get_children_ids_without_backdrop(movies_without_backdrop_ids, imgtype)
        print("继续下一轮")
        logging.info("继续下一轮")