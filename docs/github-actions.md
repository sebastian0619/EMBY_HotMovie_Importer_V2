# GitHub Actions 自动构建说明

本项目使用GitHub Actions自动构建Docker镜像并推送到GitHub Container Registry (ghcr.io)。

## 工作流程说明

工作流程文件位于 `.github/workflows/docker-publish.yml`，在以下情况下会触发自动构建：

1. 向 `main` 或 `master` 分支推送代码
2. 创建新的版本标签 (格式为 `v*.*.*`，例如 `v1.0.0`)
3. 创建针对 `main` 或 `master` 分支的Pull Request

## 构建产物

工作流程会构建以下架构的Docker镜像：
- linux/amd64（适用于大多数服务器和桌面计算机）
- linux/arm64（适用于ARM架构设备，如Raspberry Pi 4等）

## 镜像标签

自动生成的镜像标签包括：

- 分支名称（如 `main`）
- 提交的短SHA值（如 `sha-a1b2c3d`）
- 版本号（如 `v1.0.0`，仅在推送标签时）
- 主次版本号（如 `1.0`，仅在推送标签时）
- `latest`（仅适用于默认分支）

## 使用镜像

通过以下命令拉取最新镜像：

```bash
docker pull ghcr.io/YOUR_USERNAME/emby_hotmovie_importer_v2:latest
```

请将 `YOUR_USERNAME` 替换为你的GitHub用户名。

或者在docker-compose.yml中使用预构建镜像：

```yaml
services:
  emby-importer:
    image: ghcr.io/YOUR_USERNAME/emby_hotmovie_importer_v2:latest
    # ... 其他配置项 ...
```

## 必要设置

要使此工作流程正常工作，需要进行以下设置：

1. 在GitHub仓库设置中，确保已启用GitHub Actions
2. 确保已启用 `packages` 权限
3. 如果是私有仓库，需要手动设置仓库包的可见性 