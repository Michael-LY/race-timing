# 部署指南 — Race Timing

每次推送 `master` 分支到 GitHub，会自动构建并部署到你的 Ubuntu 服务器。

## 目录

1. [Ubuntu 服务器初始配置](#1-ubuntu-服务器初始配置)
2. [GitHub 仓库设置](#2-github-仓库设置)
3. [触发部署](#3-触发部署)
4. [手动部署](#4-手动部署)
5. [运维命令](#5-运维命令)
6. [常见问题](#6-常见问题)

---

## 1. Ubuntu 服务器初始配置

### 1.1 创建专用部署用户（推荐）

```bash
# 登录服务器
ssh root@你的服务器IP

# 创建用户（非 root 运行更安全）
sudo useradd -m -s /bin/bash deploy

# 设置密码（可选）
sudo passwd deploy

# 赋予 sudo 权限（部署脚本需要安装依赖和重启服务）
sudo usermod -aG sudo deploy
```

### 1.2 安装必要软件

```bash
# Python 3.12（如 Ubuntu 24.04 自带 3.12）
python3 --version       # 确认 ≥ 3.12

# 如版本过低，安装 Python 3.12
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

### 1.3 创建部署目录

```bash
sudo mkdir -p /opt/race-timing/current
sudo mkdir -p /opt/race-timing/shared/instance
sudo mkdir -p /opt/race-timing/shared/uploads

# 将目录所有权交给 deploy 用户
sudo chown -R deploy:deploy /opt/race-timing
```

### 1.4 配置 SSH 密钥（关键！）

在**你的本地开发机**上生成一对专门用于部署的 SSH 密钥：

```bash
# 在本地执行，不要用服务器上已有的密钥
ssh-keygen -t ed25519 -f ~/.ssh/race-timing-deploy -C "github-actions-deploy"
```

这会生成两个文件：
- `~/.ssh/race-timing-deploy` — **私钥**（后续添加到 GitHub Secrets）
- `~/.ssh/race-timing-deploy.pub` — **公钥**（添加到服务器）

将公钥添加到服务器的 `deploy` 用户：

```bash
# 在本地执行
ssh-copy-id -i ~/.ssh/race-timing-deploy.pub deploy@你的服务器IP

# 如果 ssh-copy-id 不可用，手动操作：
# 先登录服务器，然后：
# mkdir -p ~deploy/.ssh && chmod 700 ~deploy/.ssh
# 把公钥内容写入 ~deploy/.ssh/authorized_keys
# chmod 600 ~deploy/.ssh/authorized_keys
# chown -R deploy:deploy ~deploy/.ssh
```

**验证 SSH 免密登录：**

```bash
ssh -i ~/.ssh/race-timing-deploy deploy@你的服务器IP "echo OK"
# 输出 OK 表示成功
```

### 1.5 开放防火墙端口

```bash
sudo ufw allow 22/tcp       # SSH
sudo ufw allow 80/tcp       # HTTP
sudo ufw allow 443/tcp      # HTTPS（如需）
sudo ufw --force enable
```

### 1.6 配置 Nginx

部署脚本会自动安装 Nginx 配置，但如果 Nginx 已运行，你手动做一次也可：

```bash
# 将项目中的 nginx 配置复制到 Nginx
sudo cp deploy/nginx/race-timing.conf /etc/nginx/sites-available/race-timing.conf
sudo ln -sf /etc/nginx/sites-available/race-timing.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

> **注意：** 部署脚本在每次部署时会自动执行以上步骤，所以首次配置后一般无需手动操作。
> 但如果你已有 Nginx 在运行其他站点，需要手动编辑 `/etc/nginx/sites-available/race-timing.conf`，把 `server_name` 改成你的域名。

### 1.7 查看当前状态（可选）

Ubuntu 上的 Nginx 服务默认已运行，检查：

```bash
sudo systemctl status nginx
```

---

## 2. GitHub 仓库设置

### 2.1 添加 Secrets

在 GitHub 仓库页面进入：

**Settings → Secrets and variables → Actions → New repository secret**

依次添加以下 **6 个 Secret**：

| Secret 名称 | 说明 | 示例值 |
|---|---|---|
| `DEPLOY_SSH_KEY` | 部署用的 SSH 私钥全文 | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `DEPLOY_HOST` | 服务器 IP 或域名 | `123.45.67.89` 或 `race.example.com` |
| `DEPLOY_USER` | SSH 登录用户名 | `deploy` |
| `DEPLOY_PATH` | 部署路径 | `/opt/race-timing` |
| `DEPLOY_PORT` | SSH 端口（默认 22） | `22` |

**获取 DEPLOY_SSH_KEY 的值：**

在本地开发机上执行：

```bash
cat ~/.ssh/race-timing-deploy
```

复制全部内容（包括 `-----BEGIN OPENSSH PRIVATE KEY-----` 和 `-----END OPENSSH PRIVATE KEY-----`），粘贴到 Secret 的值中。

> ⚠️ **不要**使用`~/.ssh/id_rsa`或其他个人密钥。单独生成一把部署专用密钥，方便吊销。

---

## 3. 触发部署

### 自动触发

```bash
git add .
git commit -m "some changes"
git push origin master
```

GitHub Actions 会自动执行：
1. ✅ 安装依赖
2. ✅ 运行测试
3. ✅ 构建发布包
4. ✅ （如推送 tag）构建 Docker 镜像并推送到 GHCR
5. ✅ SSH 连接到你的服务器
6. ✅ 上传发布包、systemd 配置、Nginx 配置
7. ✅ 在服务器上安装依赖
8. ✅ 重启 Gunicorn + Nginx

### 手动触发

在 GitHub 仓库的 **Actions → Build and deploy → Run workflow** 中手动触发。

### 查看部署日志

1. 打开仓库的 **Actions** 标签
2. 点击最新的 workflow run
3. 展开 **Deploy to remote server** 步骤查看实时输出

---

## 4. 手动部署

如果不想通过 GitHub Actions，也可以在本地直接部署：

```bash
# 1. 构建
./scripts/build_release.sh

# 2. 部署（需设置环境变量）
export DEPLOY_HOST=你的服务器IP
export DEPLOY_USER=deploy
export DEPLOY_PATH=/opt/race-timing
export DEPLOY_PORT=22

./scripts/deploy.sh dist/race-timing-release.tar.gz
```

---

## 5. 运维命令

在服务器上：

```bash
# 查看应用状态
sudo systemctl status race-timing

# 查看实时日志
sudo journalctl -u race-timing -f

# 查看最近 100 行日志
sudo journalctl -u race-timing -n 100

# 重启应用
sudo systemctl restart race-timing

# 停止应用
sudo systemctl stop race-timing

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# 测试 Nginx 配置
sudo nginx -t

# 重载 Nginx（不中断连接）
sudo systemctl reload nginx

# 查看数据库位置
ls -la /opt/race-timing/shared/instance/

# 数据库备份
cp /opt/race-timing/shared/instance/timing.db /opt/race-timing/shared/instance/timing.db.bak
```

---

## 6. 常见问题

### Q: 部署失败，SSH 连接超时

检查：
- 服务器是否已开启：`ping 你的服务器IP`
- SSH 端口是否正确：`ssh -p 22 deploy@你的服务器IP`
- 防火墙是否放行：`sudo ufw status`
- Secret 中的 DEPLOY_SSH_KEY 格式是否正确（以 `-----BEGIN` 开头，换行为 `\n`）

### Q: 部署成功但页面无法访问

```bash
# 检查 Gunicorn 是否运行
sudo systemctl status race-timing

# 检查 Nginx 是否运行
sudo systemctl status nginx

# 检查 Nginx 配置
sudo nginx -t

# 看应用日志
sudo journalctl -u race-timing -n 50 --no-pager
```

### Q: 数据库在哪？会不会被部署覆盖？

数据库存储在 `/opt/race-timing/shared/instance/timing.db`，每次部署只更新 `/opt/race-timing/current/`，`shared/` 目录里的数据**不会**被覆盖。

### Q: SECRET_KEY 在哪？

首次部署时自动生成，存储在 `/opt/race-timing/shared/.env`。如需重新生成，删除该文件后下次部署会自动创建新密钥（⚠️ 会导致所有用户会话失效）。

### Q: 不想每次 push 都部署？

在 `.github/workflows/deploy.yml` 中把 `push` 下的 `branches` 配置改为只对 tag 触发：

```yaml
on:
  push:
    tags:
      - 'v*'
```

这样只有推送 `v1.0.0` 这样的 tag 才会部署。

### Q: 如何更换部署服务器？

1. 在服务器上为新用户配置 SSH 公钥
2. 在 GitHub Secrets 中更新 `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_PORT`
3. 推送一次触发重新部署

### Q: 如何在已有域名下配置？

编辑 `/etc/nginx/sites-available/race-timing.conf`，修改 `server_name`：

```nginx
server {
    listen 80;
    server_name timing.yourdomain.com;
    ...
}
```

然后运行 `sudo systemctl reload nginx`。
