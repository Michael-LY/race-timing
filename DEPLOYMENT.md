# 自动打包与部署

这个仓库已调整为适合 Ubuntu + Nginx + systemd 的部署方式：

- 生成发布压缩包：scripts/build_release.sh
- 通过 SSH 部署到远程 Ubuntu 服务器：scripts/deploy.sh
- GitHub Actions 工作流：.github/workflows/deploy.yml
- systemd 服务配置：deploy/race-timing.service
- Nginx 反向代理配置：deploy/nginx/race-timing.conf
- Docker 打包入口：Dockerfile

## 1. GitHub Actions 配置

在 GitHub 仓库的 Settings → Secrets and variables → Actions 中添加以下 Secrets：

- DEPLOY_HOST：远程服务器地址
- DEPLOY_USER：SSH 用户名（建议使用 root 或具有 sudo 权限的用户）
- DEPLOY_PATH：部署目录，例如 /opt/race-timing
- DEPLOY_PORT：SSH 端口，默认 22（可选）

## 2. 触发方式

- 推送到 main 分支时触发
- 推送 tag（例如 v1.0.0）时会创建 GitHub Release
- 也可以在 Actions 页面手动运行 workflow_dispatch

## 3. 生成产物

每次成功执行后，会生成：

- dist/race-timing-release.tar.gz：可发布的压缩包
- ghcr.io/<owner>/race-timing:latest：Docker 镜像

## 4. 远端部署要求

远端 Ubuntu 服务器需要满足：

- Python 3.12+
- Python venv 与 pip
- Nginx
- systemd
- SSH 服务

部署脚本会：

- 在远端安装 Python 与 Nginx 依赖
- 把应用部署到 DEPLOY_PATH/current
- 使用 systemd 启动 Gunicorn
- 使用 Nginx 反向代理到 127.0.0.1:8000
- 持久化实例数据目录：
  - DEPLOY_PATH/shared/instance
  - DEPLOY_PATH/shared/uploads

## 5. 本地手动执行

```bash
chmod +x scripts/build_release.sh scripts/deploy.sh
./scripts/build_release.sh
DEPLOY_HOST=1.2.3.4 DEPLOY_USER=root DEPLOY_PATH=/opt/race-timing ./scripts/deploy.sh dist/race-timing-release.tar.gz
```
