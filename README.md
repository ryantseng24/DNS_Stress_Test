# DNS Load Test v1.0 - Advanced Multi-Source Attack Simulator

![Python](https://img.shields.io/badge/python-v3.6+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey.svg)

一個強大的 DNS 負載測試工具，專為測試防火牆和安全設備的 DNS 攻擊防護能力而設計。能夠模擬大量分散式 IP 來源的 DNS 查詢攻擊，完美測試 F5 AFM、Palo Alto、Fortinet 等企業級安全設備。

> **⚠️ 重要聲明：此工具僅供授權的安全測試使用，禁止用於任何未經授權的攻擊行為**

## 🚀 功能特色

### 核心功能
- **🎯 精確 QPS 控制**：可精確控制總體和每 IP 的查詢頻率
- **🌐 IP 偽造技術**：使用 RAW Socket 實現真實的 IP 偽造
- **⚡ 多進程並行**：充分利用多核心 CPU 實現高性能
- **📊 實時監控**：提供詳細的發送統計和錯誤監控
- **🔧 靈活配置**：JSON 配置檔支援複雜的測試情境

### 攻擊模擬能力
- **正常用戶模擬**：低頻率、大量 IP 的正常 DNS 查詢
- **惡意攻擊模擬**：高頻率、少量 IP 的集中式攻擊
- **混合流量**：同時模擬正常和惡意流量，測試智能防護
- **自定義比例**：可調整正常/惡意流量的比例分配

## 📋 系統需求

### 作業系統
- Linux (推薦 Ubuntu 18.04+, CentOS 7+)
- 需要 root 權限（用於 RAW Socket 和 IP 偽造）

### 軟體需求
```bash
Python 3.6+
sudo 權限
網路卡支援 IP 偽造
```

### 硬體建議
- **CPU**：4 核心以上（支援高 QPS）
- **記憶體**：8GB+ （處理大量併發連接）
- **網路**：1Gbps+ （避免頻寬成為瓶頸）

## 🛠️ 安裝使用

### 1. 下載程式
```bash
git clone https://github.com/yourusername/dns-load-test.git
cd dns-load-test
chmod +x dns_load_test_v1.0_final.py
```

### 2. 建立設定檔
```bash
sudo python3 dns_load_test_v1.0_final.py --create-config
```

### 3. 編輯測試參數
```bash
nano dns_test_config.json
```

### 4. 執行測試
```bash
# 基本執行
sudo python3 dns_load_test_v1.0_final.py <目標DNS服務器IP>

# 範例
sudo python3 dns_load_test_v1.0_final.py 10.8.38.41
```

### 5. 停止測試
按 `Ctrl+C` 優雅停止，程式會自動清理所有進程並顯示詳細統計。

## ⚙️ 配置說明

### 設定檔結構 (dns_test_config.json)

```json
{
  "total_qps": 200000,
  "ip_ranges": [
    {
      "name": "Normal_Range1",
      "start_ip": "10.201.0.1",
      "end_ip": "10.201.39.6", 
      "percentage": 9.0,
      "use_ip_spoofing": true,
      "per_ip_qps": 1.801,
      "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
    },
    {
      "name": "Malicious_Range1",
      "start_ip": "10.101.0.1",
      "end_ip": "10.101.0.100",
      "percentage": 10.0,
      "use_ip_spoofing": true,
      "per_ip_qps": 200.0,
      "comment": "100個惡意IP，每個200 QPS = 20k總QPS"
    }
  ]
}
```

### 參數說明

| 參數 | 說明 | 範例 |
|------|------|------|
| `total_qps` | 總目標 QPS | `200000` |
| `name` | 範圍名稱 | `"Normal_Range1"` |
| `start_ip` | 起始 IP | `"10.201.0.1"` |
| `end_ip` | 結束 IP | `"10.201.39.6"` |
| `percentage` | 流量佔比 (%) | `9.0` |
| `use_ip_spoofing` | 是否偽造 IP | `true` |
| `per_ip_qps` | 每 IP 的 QPS | `1.801` |

## 📖 使用範例

### 場景 1：基本 DDoS 測試
```bash
# 使用預設設定（200k QPS，99.9% 正常 + 0.1% 惡意）
sudo python3 dns_load_test_v1.0_final.py 192.168.1.100
```

### 場景 2：低強度測試
```bash
# 快速覆蓋 QPS 設定
sudo python3 dns_load_test_v1.0_final.py 192.168.1.100 --qps 50000
```

### 場景 3：自定義設定檔
```bash
# 使用自定義設定
sudo python3 dns_load_test_v1.0_final.py 192.168.1.100 --config my_test.json
```

### 場景 4：多階段測試
```bash
# 階段 1：低強度預熱
sudo python3 dns_load_test_v1.0_final.py 10.8.38.41 --qps 10000

# 階段 2：中等強度
sudo python3 dns_load_test_v1.0_final.py 10.8.38.41 --qps 100000

# 階段 3：全力攻擊
sudo python3 dns_load_test_v1.0_final.py 10.8.38.41 --qps 500000
```

## 📊 監控與分析

### 實時輸出範例
```
DNS負載測試 v1.0 Final
目標DNS伺服器: 10.8.38.41
目標總QPS: 200,000
================================================================================
[ 10.5s] 瞬時: 180,234 PPS | 平均: 175,123 PPS | 總計: 1,839,293 | 錯誤: 23
[ 13.5s] 瞬時: 195,674 PPS | 平均: 182,445 PPS | 總計: 2,463,001 | 錯誤: 31
```

### F5 日誌監控
```bash
# 監控正常流量 (10.201-210.x.x)
tail -f /var/log/ltm | grep -E "10\.20[1-9]\.|10\.210\."

# 監控惡意流量 (10.101.x.x)  
tail -f /var/log/ltm | grep "10\.101\."

# 監控所有測試流量
tail -f /var/log/ltm | grep -E "(10\.101|10\.20[1-9]|10\.210)"
```

## 🔧 高級配置

### 自定義攻擊模式

#### 模式 1：集中式攻擊
```json
{
  "total_qps": 100000,
  "ip_ranges": [
    {
      "name": "Concentrated_Attack",
      "start_ip": "172.16.1.1",
      "end_ip": "172.16.1.10",
      "percentage": 100.0,
      "per_ip_qps": 10000.0
    }
  ]
}
```

#### 模式 2：分散式攻擊
```json
{
  "total_qps": 100000, 
  "ip_ranges": [
    {
      "name": "Distributed_Attack",
      "start_ip": "192.168.0.1",
      "end_ip": "192.168.255.254",
      "percentage": 100.0,
      "per_ip_qps": 1.53
    }
  ]
}
```

#### 模式 3：混合流量測試
```json
{
  "total_qps": 200000,
  "ip_ranges": [
    {
      "name": "Normal_Users",
      "start_ip": "10.0.0.1", 
      "end_ip": "10.0.199.254",
      "percentage": 80.0,
      "per_ip_qps": 3.13
    },
    {
      "name": "Bot_Attack",
      "start_ip": "172.16.0.1",
      "end_ip": "172.16.0.200", 
      "percentage": 20.0,
      "per_ip_qps": 200.0
    }
  ]
}
```

## 🚨 故障排除

### 常見問題

#### Q1: Permission denied 錯誤
```bash
# 錯誤：[Errno 1] Operation not permitted
# 解決：確保使用 sudo 執行
sudo python3 dns_load_test_v1.0_final.py 10.8.38.41
```

#### Q2: Ctrl+C 無法停止程式
```bash
# 解決：使用強制終止腳本
pkill -f "dns_load_test"
```

#### Q3: QPS 達不到目標
```bash
# 檢查：
# 1. 網路頻寬是否足夠
# 2. CPU 使用率是否過高  
# 3. 目標伺服器是否有限流
```

#### Q4: IP 偽造不生效
```bash
# 檢查：
# 1. 是否有 root 權限
# 2. 防火牆是否阻擋了 RAW socket
# 3. 網路卡是否支援偽造

# 測試方法：關閉 IP 偽造進行對比測試
"use_ip_spoofing": false
```

### 效能調整

#### 提升 QPS 效能
```json
{
  "total_qps": 500000,
  "ip_ranges": [
    {
      "per_ip_qps": 5.0,  // 適當提高每IP QPS
      "use_ip_spoofing": false  // 關閉偽造提升效能
    }
  ]
}
```

#### 系統調整
```bash
# 增加檔案描述符限制
ulimit -n 65536

# 調整網路緩衝區
echo 'net.core.rmem_max = 134217728' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 134217728' >> /etc/sysctl.conf
sysctl -p
```

## 📚 技術原理

### IP 偽造實現
- 使用 `socket.SOCK_RAW` 建立原始 socket
- 手動構造 IP 頭部和 UDP 頭部
- 設定 `IP_HDRINCL` 選項控制 IP 頭部
- 每個偽造 IP 獨立計算 QPS 限制

### QPS 控制算法
- **每 IP 限制**：記錄每個 IP 的上次發送時間
- **總體控制**：動態調整進程間的發送間隔
- **平滑發送**：避免突發流量造成的網路擁塞

### 多進程架構
```
主進程 (監控統計)
├── Worker 1 (Normal_Range1)
├── Worker 2 (Normal_Range2)  
├── ...
└── Worker N (Malicious_Range)
```

## 📋 命令參考

### 基本命令
```bash
# 顯示幫助
python3 dns_load_test_v1.0_final.py --help

# 建立設定檔
sudo python3 dns_load_test_v1.0_final.py --create-config

# 基本執行
sudo python3 dns_load_test_v1.0_final.py <DNS_IP>

# 指定QPS
sudo python3 dns_load_test_v1.0_final.py <DNS_IP> --qps 100000

# 使用自定義設定檔
sudo python3 dns_load_test_v1.0_final.py <DNS_IP> --config custom.json
```

### 監控命令
```bash
# 監控進程狀態
ps aux | grep dns_load_test

# 監控網路流量
iftop -i eth0

# 監控系統資源
htop

# 監控目標伺服器回應
ping <目標IP>
nslookup test.com <目標IP>
```

## ⚖️ 法律聲明

### 🚨 重要警告
此工具專為**授權的安全測試**而設計，包括但不限於：
- 企業內部安全評估
- 滲透測試服務
- 安全設備效能測試
- 學術研究和教育

### 禁止用途
❌ **嚴禁用於以下用途：**
- 未經授權的網路攻擊
- 對他人基礎設施的惡意測試
- 任何形式的網路犯罪活動
- 違反當地法律法規的行為

### 使用者責任
- ✅ 使用前務必取得目標系統擁有者的明確授權
- ✅ 遵守所在地區的相關法律法規
- ✅ 僅在受控環境下進行測試
- ✅ 測試完畢後立即停止工具運行

### 免責聲明
- 作者不對此工具的誤用或濫用承擔任何責任
- 使用者需自行承擔使用此工具的所有法律風險
- 此工具按「現狀」提供，不提供任何形式的保證

## 🤝 貢獻指南

歡迎提交 Issue 和 Pull Request！

### 開發環境設置
```bash
git clone https://github.com/yourusername/dns-load-test.git
cd dns-load-test

# 建立開發分支
git checkout -b feature/your-feature
```

### 提交規範
- 遵循 PEP 8 程式碼風格
- 添加適當的註解和文檔
- 確保向後相容性
- 添加相應的測例

## 📄 授權協議

MIT License - 詳見 [LICENSE](LICENSE) 檔案

## 📧 聯絡方式

- **問題回報**：[GitHub Issues](https://github.com/yourusername/dns-load-test/issues)
- **功能建議**：[GitHub Discussions](https://github.com/yourusername/dns-load-test/discussions)

---

**⭐ 如果這個專案對你有幫助，請給個 Star！**

**🔒 記住：負責任地使用，僅限授權測試！**
