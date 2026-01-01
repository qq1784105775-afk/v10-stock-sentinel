#!/bin/bash
# V8 Ultra Pro 一键部署脚本
# 使用方法: chmod +x install.sh && ./install.sh

set -e

echo "=========================================="
echo "   V8 Ultra Pro 一键部署脚本"
echo "=========================================="

# 配置
PROJECT_DIR="/www/wwwroot/v8_ultra_pro"
SERVICE_NAME="v8"
SENTINEL_SERVICE="v8_sentinel"
PYTHON_VERSION="python3"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

# 1. 检查 root 权限
if [ "$EUID" -ne 0 ]; then 
    print_error "请使用 root 权限运行: sudo ./install.sh"
    exit 1
fi

# 2. 停止旧服务
print_status "停止旧服务..."
systemctl stop $SERVICE_NAME 2>/dev/null || true
systemctl stop $SENTINEL_SERVICE 2>/dev/null || true

# 3. 备份旧版本（保留数据库）
OLD_DB=""
if [ -d "$PROJECT_DIR" ]; then
    # 保留旧数据库
    if [ -f "$PROJECT_DIR/v8_data.db" ]; then
        print_warning "保留现有数据库..."
        cp "$PROJECT_DIR/v8_data.db" /tmp/v8_data.db.bak
        OLD_DB="/tmp/v8_data.db.bak"
    fi
    BACKUP_NAME="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    print_warning "发现旧版本，备份到: $BACKUP_NAME"
    mv "$PROJECT_DIR" "$BACKUP_NAME"
fi

# 4. 创建项目目录
print_status "创建项目目录..."
mkdir -p "$PROJECT_DIR"

# 5. 复制文件
print_status "复制项目文件..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp -r "$SCRIPT_DIR"/* "$PROJECT_DIR/"
rm -f "$PROJECT_DIR/install.sh"

# 6. 恢复旧数据库（如果有）
if [ -n "$OLD_DB" ] && [ -f "$OLD_DB" ]; then
    print_status "恢复数据库..."
    cp "$OLD_DB" "$PROJECT_DIR/v8_data.db"
    rm -f "$OLD_DB"
fi

# 7. 创建虚拟环境
print_status "创建 Python 虚拟环境..."
cd "$PROJECT_DIR"
$PYTHON_VERSION -m venv venv
source venv/bin/activate

# 8. 安装依赖
print_status "安装 Python 依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple

# 9. 初始化数据库（如果不存在）
if [ ! -f "$PROJECT_DIR/v8_data.db" ]; then
    print_status "初始化数据库..."
    $PYTHON_VERSION -c "
from database.db_manager import DatabaseManager
db = DatabaseManager('v8_data.db')
print('数据库初始化完成')
"
fi

# 10. 创建主服务
print_status "配置主服务..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=V8 Ultra Pro Stock System
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 11. 创建哨兵服务（微信推送）
print_status "配置哨兵服务..."
cat > /etc/systemd/system/$SENTINEL_SERVICE.service << EOF
[Unit]
Description=V8 Cloud Sentinel (WeChat Push)
After=network.target $SERVICE_NAME.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python cloud_sentinel.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 12. 启动服务
print_status "启动服务..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl enable $SENTINEL_SERVICE
systemctl start $SERVICE_NAME

sleep 2
if systemctl is-active --quiet $SERVICE_NAME; then
    print_status "主服务启动成功！"
    systemctl start $SENTINEL_SERVICE
    print_status "哨兵服务启动成功！"
else
    print_error "服务启动失败，请检查日志: journalctl -u $SERVICE_NAME -f"
    exit 1
fi

# 13. 获取 IP
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=========================================="
echo -e "${GREEN}   部署完成！${NC}"
echo "=========================================="
echo ""
echo "访问地址: http://$IP:9000"
echo ""
echo "常用命令:"
echo "  查看主服务状态: systemctl status $SERVICE_NAME"
echo "  查看哨兵状态:   systemctl status $SENTINEL_SERVICE"
echo "  查看日志:       journalctl -u $SERVICE_NAME -f"
echo "  重启服务:       systemctl restart $SERVICE_NAME"
echo "  停止服务:       systemctl stop $SERVICE_NAME"
echo ""
echo "项目目录: $PROJECT_DIR"
echo "=========================================="
