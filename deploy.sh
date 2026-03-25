#!/bin/bash
# 任务管理系统部署脚本

cd /root/.openclaw/workspace/projects/task-app/backend

# 安装依赖
pip install -q -r requirements.txt

# 安装 Flask-CORS
pip install -q flask-cors

# 准备 systemd 服务
cat > /etc/systemd/system/task-app.service << EOF
[Unit]
Description=Task App Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/.openclaw/workspace/projects/task-app/backend
ExecStart=/usr/bin/python3 /root/.openclaw/workspace/projects/task-app/backend/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd 并启动
systemctl daemon-reload
systemctl enable task-app
systemctl restart task-app

# 开放防火墙
ufw allow 5000/tcp 2>/dev/null || iptables -A INPUT -p tcp --dport 5000 -j ACCEPT 2>/dev/null || true

echo "========== 部署完成 =========="
echo "服务状态: systemctl status task-app"
echo "访问地址: http://$(curl -s ifconfig.me):5000"
