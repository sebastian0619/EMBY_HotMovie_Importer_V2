# Emby服务器自动创建热门影剧合集

啥都不会，GPT写的。 脚本大概能用，应该。。。

在大佬的改良版上修改 [https://github.com/xuanqb/EMBY_HotMovie_Importer](https://github.com/xuanqb/EMBY_HotMovie_Importer) 实现

+ 增加了合集封面创建，会自动指定合集内的某一个项目的封面作为该合集的封面，而不是默认的那种多图拼接的封面。
+ 已存在合集时，先清空合集，再添加新项目到合集内，保证每次随着榜单更新后的合集内容都是动态更新的


# 运行效果
![image](docs/创建时.png)
![image](docs/清空合集.png)
![image](docs/创建完毕.png)

# 前期准备
如果需要TOP250的榜单能够获取250个数据，则需Docker部署大佬的RSSHub，官方的默认只能抓取10条，

### 部署方式1
``` Bash
docker run -d --name rsshub --restart unless-stopped -p 1200:1200 -e NODE_ENV=production xuanqb/rsshub:latest
```

### 或者部署方式2：
``` docker-compose
version: '3'
services:
  rsshub:
    image: xuanqb/rsshub:latest
    restart: unless-stopped
    ports:
      - 1200:1200
    environment:
      NODE_ENV: production
    container_name: rsshub
```

# 先进行下方配置文件的修改，再运行
```
pip install -r requirements.txt
python EMBY_HotMovie_Importer.py
```


# 配置文件的修改
``` conf
[Server]
# 这里填入你Emby服务器地址
emby_server = http://xxx.xx.xx.x:8096
# 这里填入你Emby API密钥
emby_api_key = xxxxxxx
rsshub_server = http://xx.xx.x.x:1200

```

``` conf
[Collection]
#各种榜单 按需选择

# 实时热门书影音	subject_real_time_hotest
# 影院热映	movie_showing
# 实时热门电影	movie_real_time_hotest
# 实时热门电视	tv_real_time_hotest
# 一周口碑电影榜	movie_weekly_best
# 一周热门电影榜	movie_hot_gaia
# 一周热门剧集榜	tv_hot
# 一周热门综艺榜	show_hot
# 豆瓣TOPO250	movie_top250
# 华语口碑剧集榜	tv_chinese_best_weekly
# 全球口碑剧集榜	tv_global_best_weekly
# 国内口碑综艺榜	show_chinese_best_weekly
# 国外口碑综艺榜	show_global_best_weekly
# 热播新剧国产剧	tv_domestic
# 热播新剧欧美剧	tv_american
# 热播新剧日剧	tv_japanese
# 热播新剧韩剧	tv_korean
# 热播新剧动画	tv_animation
# 

rss_ids=tv_american,tv_domestic,movie_top250,tv_japanese,tv_animation
```
``` conf
# 额外配置
[Extra]
# 忽略播放过的视频，（不加入合集）
ignore_played = false
# emby_user_id在浏览器链接栏获取，不知道百度
emby_user_id = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
