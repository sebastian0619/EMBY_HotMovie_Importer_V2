# Emby服务器自动创建热门影剧合集

啥都不会，GPT写的。 脚本大概能用，应该。。。

在大佬的改良版上修改 [https://github.com/xuanqb/EMBY_HotMovie_Importer](https://github.com/xuanqb/EMBY_HotMovie_Importer) 实现

+ 增加了合集封面创建，会自动指定合集内的某一个项目的封面作为该合集的封面，而不是默认的那种多图拼接的封面。
+ 已存在合集时，先清空合集，再添加新项目到合集内，保证每次随着榜单更新后的合集内容都是动态更新的
+ 2024年11月28日更新：未找到的电影会被记录到csv文件内，方便你添加订阅
+ - 创建的合集名前缀是✨号，是为了让新创建的合集再标题排序模式下靠前，如果不想要的话可以在主脚本内搜索替换


# 运行效果
![image](docs/创建时.png)
![image](docs/清空合集.png)
![image](https://github.com/user-attachments/assets/20c99f75-2ddb-42a1-a289-6b3a518e9e40)
![image](docs/创建完毕.png)

# 运行向导

#### 1.Docker部署rsshub或者用官方的
如果需要TOP250的榜单能够获取250个数据，则需Docker部署大佬的RSSHub，官方的默认只能抓取10条

``` Bash
docker run -d --name rsshub --restart unless-stopped -p 1200:1200 -e NODE_ENV=production xuanqb/rsshub:latest
```

#### 3. 安装依赖&运行程序
```
pip install -r requirements.txt
python EMBY_HotMovie_Importer.py
```


#### 2. 修改config.conf配置文件
``` conf
[Server]
# 这里填入你Emby服务器地址
emby_server = http://xxx.xx.xx.x:8096
# 这里填入你Emby API密钥
emby_api_key = xxxxxxx
rsshub_server = http://xx.xx.x.x:1200
# emby_user_id在浏览器链接栏获取，不知道百度
emby_user_id = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

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

rss_ids=tv_american,tv_domestic,movie_top250,tv_japanese,tv_animation
```

