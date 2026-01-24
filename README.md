# Monitor Bot

独立的加密货币价格和持仓监控机器人。

## 功能
- 价格价差监控 (Backpack vs 现货)
- 价格波动监控 (BTC等)
- 价格目标监控 (Bybit)
- 多账户持仓净敞口监控 (Backpack)
- Telegram 报警通知

## 安装

1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量:
   `.env` 文件已自动生成并配置完毕。
   如需修改，请直接编辑 `.env` 文件。
   主要配置 `TELEGRAM_ALERT_BOT_TOKEN` 和 `TELEGRAM_ALERT_CHAT_ID`。

3. 运行:
   ```bash
   python monitor.py
   ```

## 命令控制
在 Telegram 中也可以使用以下命令控制机器人：
- `/start` - 显示帮助
- `/stop` - 停止所有持续提醒
- `/continue` - 恢复波动监控
- `/status` - 查看当前监控状态
