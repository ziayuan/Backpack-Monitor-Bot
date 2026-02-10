# Monitor Bot

独立的加密货币价格和持仓监控机器人，支持多交易所、多币种监控及Telegram报警通知。

## 功能

1. **多币种价差监控**
   - 监控 Backpack 现货与合约之间的价差
   - 支持多币种配置（如 SOL, BTC, ETH）
   - 当价差超过设定阈值（如 1%）时发送警报

2. **多交易所波动监控**
   - 支持监控 **Binance, Bybit, Bitget, Hyperliquid, Backpack**
   - 独立配置每个交易所和币种的波动阈值
   - 实时监控短时间内的剧烈价格波动

3. **持仓风险监控**
   - 监控 Backpack 账户的现货和合约持仓
   - 计算净敞口（Net Exposure），防止对冲失效
   - 支持多账户监控（Main, Sub1, Sub2...）

4. **Telegram 警报与控制**
   - 实时发送格式化的警报消息
   - 支持通过 Telegram 命令控制机器人

## 安装

1. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

2. **配置**:
   - **敏感信息**: 复制 `.env.example` 到 `.env` 并填写 API Key 和 Telegram Token。
   - **监控逻辑**: 修改 `config.py` 来调整阈值、监控币种和时间间隔。
     - `PRICE_MONITOR_CONFIGS`: 价差监控配置
     - `VOLATILITY_MONITOR_CONFIGS`: 多交易所波动监控配置
     - `POSITION_TICKER_CONFIGS`: 持仓监控配置

3. **后台运行 (推荐)**:
   ```bash
   ./run.sh
   ```
   
4. **停止**:
   ```bash
   ./stop.sh
   # 或者在 Telegram 中发送 /shutdown
   ```

## 命令控制

在 Telegram 中可以使用以下命令控制机器人：

| 命令 | 说明 |
|------|------|
| `/start` | 显示帮助信息 |
| `/status` | 查看所有监控器的状态及编号 |
| `/stop <编号>` | 停止指定编号的警报（不会停止进程） |
| `/continue` | 恢复所有被停止的警报 |
| `/shutdown` | 🔴 停止整个机器人进程（需手动重启） |

**使用示例**:
- `/status` -> 查看警报列表，例如 `21 - Backpack SOL 波动监控`
- `/stop 21` -> 停止该波动监控警报
