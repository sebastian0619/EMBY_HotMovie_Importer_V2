# Docker部署说明

## 环境需求

- Docker
- Docker Compose

## 快速部署

### 方式一：使用预构建镜像（推荐）

1. 确保已经配置好`config.conf`文件，填写正确的Emby服务器地址、API密钥等信息
2. 修改`docker-compose.yml`文件，使用预构建镜像：

```yaml
services:
  emby-importer:
    image: ghcr.io/YOUR_USERNAME/emby_hotmovie_importer_v2:latest
    # ... 其他配置保持不变 ...
```

3. 使用以下命令启动容器：

```bash
docker-compose up -d
```

### 方式二：本地构建镜像

1. 确保已经配置好`config.conf`文件，填写正确的Emby服务器地址、API密钥等信息
2. 使用以下命令构建并启动容器：

```bash
docker-compose up -d --build
```

3. 查看日志：

```bash
docker-compose logs -f
```

## 配置说明

### 持久化存储

docker-compose.yml中已配置以下映射：
- `./config.conf:/app/config.conf` - 配置文件映射
- `./missing_movies.csv:/app/missing_movies.csv` - 未找到电影的CSV记录

### 定时任务

如果需要定时执行导入任务，可以取消注释docker-compose.yml中的command部分。
默认配置为每天执行一次。你也可以修改sleep的值来调整执行频率。

### 环境变量

可以在docker-compose.yml的environment部分定义环境变量，常用的有：
- EMBY_SERVER - Emby服务器地址
- EMBY_API_KEY - Emby API密钥
- RSSHUB_SERVER - RSSHub服务器地址

## 常用命令

### 启动服务
```bash
docker-compose up -d
```

### 停止服务
```bash
docker-compose down
```

### 重建并启动服务
```bash
docker-compose up -d --build
```

### 手动执行脚本
```bash
docker-compose exec emby-importer python EMBY_HotMovie_Importer.py
```

### 查看日志
```bash
docker-compose logs -f
```

## GitHub Actions 自动构建

本项目配置了GitHub Actions工作流，会在代码推送或标签创建时自动构建Docker镜像并推送到GitHub Container Registry。

详细说明请参见 [GitHub Actions文档](docs/github-actions.md)。

## 故障排除

1. 如果需要使用代理，请在config.conf中设置使用代理，并在docker-compose.yml中添加相应的网络配置
2. 确保Emby服务器和RSSHub服务器的地址填写正确，包括协议前缀(http/https)
3. 如果遇到权限问题，可以修改Dockerfile中的用户配置 