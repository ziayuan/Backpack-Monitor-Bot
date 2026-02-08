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

2. 配置:
   - **敏感信息**: 复制 `.env.example` 到 `.env` 并填写 API Key 和 Token。
   - **监控逻辑**: 修改 `config.py` 来调整阈值、监控币种和时间间隔。
     - 支持多币种持仓监控配置 (POSITION_TICKER_CONFIGS)。
     - 支持自定义不同币种的报警阈值。

3. 运行:
   - **后台运行 (推荐)**:
     ```bash
     ./run.sh
     ```
     日志将输出到 `monitor.log`。
   
   - **停止**:
     ```bash
     ./stop.sh
     ```

   - **手动调试**:
     ```bash
     python monitor.py
     ```

## 命令控制
在 Telegram 中也可以使用以下命令控制机器人：
- `/start` - 显示帮助
- `/status` - 查看所有警报状态（包含编号）
- `/get <编号> [时长]` - 静默指定警报
  - 例如: `/get 1 10m` 静默1号警报10分钟
  - 时长格式: `10s`(秒), `10m`(分钟), `1h`(小时), `1d`(天)
  - 默认10分钟
- `/continue` - 恢复所有警报监控
- `/stop` - 停止机器人进程 (需手动重启)

