#!/bin/bash
# ============================================================
# 每日新闻日报 - 服务器部署脚本
# 在服务器 199.180.116.188 上执行此脚本完成部署
# 使用方式：bash deploy.sh
# ============================================================

set -e

echo "=========================================="
echo "  每日新闻日报 - 服务器部署"
echo "=========================================="

# 配置
INSTALL_DIR="/opt/news-daily"
REPO_URL="https://github.com/yanwx54/news-daily.git"
PYTHON_BIN="python3"

# 1. 检查并安装 Python3
echo ""
echo "[1/6] 检查 Python3..."
if command -v $PYTHON_BIN &> /dev/null; then
    echo "  ✓ Python3 已安装: $($PYTHON_BIN --version)"
else
    echo "  安装 Python3..."
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y python3 python3-pip
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip
    else
        echo "  [ERROR] 无法自动安装 Python3，请手动安装"
        exit 1
    fi
fi

# 2. 克隆代码
echo ""
echo "[2/6] 克隆代码仓库..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  目录已存在，拉取最新代码..."
    cd "$INSTALL_DIR"
    git pull origin main || true
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. 安装 Python 依赖
echo ""
echo "[3/6] 安装 Python 依赖..."
pip3 install -r requirements.txt --quiet

# 4. 配置环境变量
echo ""
echo "[4/6] 配置环境变量..."

# 读取用户输入
read -p "请输入微信公众号 AppID: " WECHAT_APPID
read -p "请输入微信公众号 AppSecret: " WECHAT_APP_SECRET
read -p "请输入 PushPlus Token（可留空跳过）: " PUSHPLUS_TOKEN

ENV_FILE="$INSTALL_DIR/.env"
cat > "$ENV_FILE" << EOF
# 微信公众号配置
WECHAT_APPID=$WECHAT_APPID
WECHAT_APP_SECRET=$WECHAT_APP_SECRET

# PushPlus 配置（可选）
PUSHPLUS_TOKEN=$PUSHPLUS_TOKEN

# 时区
TZ=Asia/Shanghai
EOF

chmod 600 "$ENV_FILE"
echo "  ✓ 环境变量已写入: $ENV_FILE"

# 5. 创建运行脚本
echo ""
echo "[5/6] 创建运行脚本..."
RUN_SCRIPT="$INSTALL_DIR/run.sh"
cat > "$RUN_SCRIPT" << 'EOF'
#!/bin/bash
# 加载环境变量
source /opt/news-daily/.env
export WECHAT_APPID WECHAT_APP_SECRET PUSHPLUS_TOKEN TZ

# 切换到项目目录
cd /opt/news-daily

# 运行日报生成脚本
python3 generate_report.py >> /opt/news-daily/logs/$(date +%Y%m%d).log 2>&1
EOF

chmod +x "$RUN_SCRIPT"

# 创建日志目录
mkdir -p "$INSTALL_DIR/logs"

echo "  ✓ 运行脚本已创建: $RUN_SCRIPT"

# 6. 设置 cron 定时任务
echo ""
echo "[6/6] 设置 cron 定时任务（每天 08:00 北京时间）..."
CRON_LINE="0 8 * * * /bin/bash $RUN_SCRIPT"

# 检查是否已存在
if crontab -l 2>/dev/null | grep -q "$RUN_SCRIPT"; then
    echo "  cron 任务已存在，跳过"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "  ✓ cron 任务已添加: $CRON_LINE"
fi

# 检查时区
echo ""
echo "检查服务器时区..."
if [ -f /etc/timezone ]; then
    CURRENT_TZ=$(cat /etc/timezone)
    echo "  当前时区: $CURRENT_TZ"
    if [ "$CURRENT_TZ" != "Asia/Shanghai" ]; then
        echo "  建议设置时区为 Asia/Shanghai:"
        echo "    sudo timedatectl set-timezone Asia/Shanghai"
    fi
else
    echo "  建议设置时区为 Asia/Shanghai:"
    echo "    sudo timedatectl set-timezone Asia/Shanghai"
fi

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "  项目目录: $INSTALL_DIR"
echo "  运行脚本: $RUN_SCRIPT"
echo "  环境变量: $ENV_FILE"
echo "  日志目录: $INSTALL_DIR/logs/"
echo ""
echo "  手动测试: bash $RUN_SCRIPT"
echo "  查看 cron: crontab -l"
echo "  查看日志: cat $INSTALL_DIR/logs/\$(date +%Y%m%d).log"
echo ""
echo "  每天 08:00（北京时间）自动执行："
echo "    1. 抓取 RSS 新闻"
echo "    2. 生成 HTML 日报"
echo "    3. 推送到微信公众号草稿箱"
echo "    4. 推送到 PushPlus（如已配置）"
echo "    5. 自动清理30天前的过期日报存档"
echo ""
