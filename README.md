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
1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **配置**:
    -   **敏感信息**: 复制 `.env.example` 到 `.env` 并填写 API Key 和 Telegram Token。
    -   **监控逻辑**: 修改 `config.py` 来调整阈值、监控币种和时间间隔。
        -   `PRICE_MONITOR_CONFIGS`: 价差监控配置
        -   `VOLATILITY_MONITOR_CONFIGS`: 多交易所波动监控配置
        -   `POSITION_TICKER_CONFIGS`: 持仓监控配置

3.  **后台运行 (推荐)**:
    ```bash
    ./run.sh
    ```

4.  **停止**:
    ```bash
    ./stop.sh
    # 或者在 Telegram 中发送 /shutdown
    ```

## ☁️ 云服务器部署指南

推荐使用 Ubuntu 22.04 LTS 或其他主流 Linux 发行版。

### 1. 环境准备

根据你的操作系统选择相应的安装命令：

#### **Ubuntu / Debian (推荐)**
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 3.10+ 和 pip
sudo apt install python3 python3-pip python3-venv git -y
```

#### **Amazon Linux / CentOS / RHEL**
```bash
# 更新系统
sudo yum update -y

# 安装 Python 3 和 git
sudo yum install python3 python3-pip git -y
```

### 2. 获取代码
```bash
# 克隆仓库
git clone <repository_url> monitor_bot
cd monitor_bot
```

### 3. 安装依赖
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 4. 配置
```bash
# 复制配置文件
cp .env.example .env

# 编辑配置 (填入你的 API Key 和 Telegram Token)
nano .env
```

### 5. 运行
建议使用 `run.sh` 脚本在后台运行:
```bash
# 添加执行权限
chmod +x run.sh stop.sh

# 启动机器人 (自动后台运行，日志输出到 monitor.log)
./run.sh
```

### 6. 维护
- **查看日志**: `tail -f monitor.log`
- **停止机器人**: `./stop.sh` 或在 Telegram 中发送 `/shutdown`
- **更新代码**:
  ```bash
  git pull
  pip install -r requirements.txt
  ./stop.sh
  ./run.sh
  ```

## 📱 Telegram 命令列表

| 命令 | 说明 | 示例 |
|------|------|------|
| `/start` | 显示帮助信息 | `/start` |
| `/status` | 查看所有监控概览 | `/status` |
| `/status <id>` | 查看指定监控的详细实时数据 | `/status 1` |
| `/stop <id>` | 停止指定 ID 的警报 | `/stop 1` |
| `/continue` | 恢复所有被停止/静默的警报 | `/continue` |
| `/shutdown` | 停止整个机器人进程 | `/shutdown` |

**使用示例**:
- `/status` -> 查看警报列表，例如 `21 - Backpack SOL 波动监控`
- `/stop 21` -> 停止该波动监控警报
