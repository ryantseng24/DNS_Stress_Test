#!/usr/bin/env python3

import sys
import time
import multiprocessing
import random
import socket
import signal
import struct
import argparse
import json
from multiprocessing import Process, Value, Array, Manager

class EnhancedDNSLoadTest:
    def __init__(self, target_dns, config):
        self.target_dns = target_dns
        self.config = config
        self.total_qps = config['total_qps']
        
        # 計算每個範圍的QPS
        self.ranges = []
        for range_config in config['ip_ranges']:
            qps = int(self.total_qps * range_config['percentage'] / 100)
            self.ranges.append({
                'name': range_config['name'],
                'start_ip': range_config['start_ip'],
                'end_ip': range_config['end_ip'],
                'qps': qps,
                'percentage': range_config['percentage'],
                'use_ip_spoofing': range_config.get('use_ip_spoofing', False),
                'per_ip_qps': range_config.get('per_ip_qps', 2.0)
            })
    
    def ip_to_int(self, ip_str):
        """IP字串轉整數"""
        parts = ip_str.split('.')
        return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])
    
    def int_to_ip(self, ip_int):
        """整數轉IP字串"""
        return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
    
    def build_dns_queries(self, range_name, count=500):
        """建立DNS查詢快取"""
        queries = []
        for i in range(count):
            query_id = random.randint(1, 65535)
            domain = f"{range_name.lower()}{i:04d}.testdomain.com"
            
            # DNS Header: ID, Flags, QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT
            header = struct.pack('!HHHHHH', query_id, 0x0100, 1, 0, 0, 0)
            
            # DNS Question
            question = b''
            for part in domain.split('.'):
                question += struct.pack('!B', len(part)) + part.encode()
            question += b'\x00'  # 結束符
            question += struct.pack('!HH', 1, 1)  # A record, IN class
            
            queries.append(header + question)
        return queries

def worker_process(process_id, range_config, target_dns, shared_stats, shared_running, shared_errors):
    """工作進程 - 真正模擬每個IP的QPS限制"""
    # 子進程忽略SIGINT，只由主進程處理
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    range_name = range_config['name']
    target_pps = range_config['qps']
    start_ip_int = range_config['start_ip_int']
    end_ip_int = range_config['end_ip_int']
    use_spoofing = range_config['use_ip_spoofing']
    per_ip_qps = range_config.get('per_ip_qps', 2.0)  # 每個IP的QPS限制
    
    ip_count = end_ip_int - start_ip_int + 1
    
    print(f"進程 {process_id} ({range_name}) 啟動")
    print(f"  IP數量: {ip_count:,} 個")
    print(f"  每IP QPS: {per_ip_qps}")
    print(f"  總目標QPS: {target_pps:,}")
    print(f"  IP範圍: {range_config['start_ip']} - {range_config['end_ip']}")
    print(f"  IP偽造: {'是' if use_spoofing else '否'}")
    
    # 建立DNS查詢快取
    test = EnhancedDNSLoadTest(target_dns, {'total_qps': 0, 'ip_ranges': []})
    queries = test.build_dns_queries(range_name, 500)
    
    # 建立socket池
    sockets = []
    socket_count = min(50, max(10, target_pps // 2000))  # 動態調整socket數量
    
    for i in range(socket_count):
        try:
            if use_spoofing:
                # RAW socket for IP spoofing (需要root權限)
                sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_UDP)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            else:
                # 普通UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)  # 增大發送緩衝區
            sockets.append(sock)
        except Exception as e:
            if i == 0:  # 第一個socket建立失敗才報告
                print(f"進程 {process_id} socket建立失敗: {e}")
    
    if not sockets:
        print(f"進程 {process_id} 無法建立任何socket，退出")
        return
    
    sent_count = 0
    error_count = 0
    
    # IP發送計數器和時間戳記錄（用於控制每個IP的QPS）
    ip_last_send_time = {}
    ip_send_count = {}
    
    print(f"進程 {process_id} 開始發送，使用 {len(sockets)} 個socket")
    
    while shared_running.value:
        loop_start = time.time()
        
        # 本輪要處理的IP數量（循環所有IP）
        ips_to_process = min(ip_count, 10000)  # 每輪最多處理1萬個IP
        
        packets_sent_this_loop = 0
        
        for ip_idx in range(ips_to_process):
            if not shared_running.value:
                break
                
            # 計算當前IP
            current_ip_int = start_ip_int + (ip_idx % ip_count)
            current_time = time.time()
            
            # 檢查這個IP是否可以發送（QPS限制）
            if current_ip_int in ip_last_send_time:
                time_since_last = current_time - ip_last_send_time[current_ip_int]
                if time_since_last < (1.0 / per_ip_qps):  # 太頻繁，跳過
                    continue
            
            # 記錄發送時間
            ip_last_send_time[current_ip_int] = current_time
            ip_send_count[current_ip_int] = ip_send_count.get(current_ip_int, 0) + 1
            
            try:
                if use_spoofing and len(sockets) > 0:
                    # 檢查是否需要停止
                    if not shared_running.value:
                        break
                        
                    # IP偽造模式
                    src_ip = test.int_to_ip(current_ip_int)
                    
                    # 建立DNS查詢
                    query = queries[ip_idx % len(queries)]
                    
                    # IP Header (20 bytes)
                    ip_header = struct.pack('!BBHHHBBH4s4s',
                        0x45,           # Version + IHL
                        0,              # Type of Service
                        20 + 8 + len(query),  # Total Length
                        random.randint(1, 65535),  # ID
                        0,              # Flags + Fragment Offset
                        64,             # TTL
                        17,             # Protocol (UDP)
                        0,              # Checksum (kernel will fill)
                        socket.inet_aton(src_ip),     # Source IP
                        socket.inet_aton(target_dns)  # Dest IP
                    )
                    
                    # UDP Header (8 bytes)
                    src_port = random.randint(1024, 65535)
                    udp_header = struct.pack('!HHHH',
                        src_port,       # Source Port
                        53,             # Dest Port (DNS)
                        8 + len(query), # Length
                        0               # Checksum
                    )
                    
                    packet = ip_header + udp_header + query
                    
                    sock = sockets[ip_idx % len(sockets)]
                    try:
                        sock.sendto(packet, (target_dns, 0))
                    except (OSError, socket.error):
                        # 忽略socket錯誤，避免程式中斷時的錯誤訊息
                        error_count += 1
                        continue
                        
                else:
                    # 檢查是否需要停止
                    if not shared_running.value:
                        break
                        
                    # 普通模式（不偽造IP）
                    query = queries[ip_idx % len(queries)]
                    sock = sockets[ip_idx % len(sockets)]
                    try:
                        sock.sendto(query, (target_dns, 53))
                    except (OSError, socket.error):
                        # 忽略socket錯誤，避免程式中斷時的錯誤訊息
                        error_count += 1
                        continue
                
                sent_count += 1
                packets_sent_this_loop += 1
                
            except Exception as e:
                error_count += 1
                # 減少錯誤報告頻率，避免洗螢幕
                if error_count % 5000 == 0 and shared_running.value:
                    print(f"進程 {process_id} 發送錯誤 {error_count}: {e}")
        
        # 更新統計（安全方式）
        try:
            shared_stats[process_id] = sent_count
            shared_errors[process_id] = error_count
        except:
            # 在程式關閉時可能會出現shared memory錯誤，忽略即可
            pass
        
        # 控制總體發送速率（粗略控制）
        loop_elapsed = time.time() - loop_start
        
        # 如果發送太快，稍作延遲
        if packets_sent_this_loop > 0:
            target_loop_time = packets_sent_this_loop / target_pps if target_pps > 0 else 0.001
            if loop_elapsed < target_loop_time:
                sleep_time = target_loop_time - loop_elapsed
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.1))  # 限制最大睡眠時間
        else:
            time.sleep(0.001)  # 避免CPU 100%
    
    # 清理
    for sock in sockets:
        try:
            sock.close()
        except:
            pass  # 忽略socket關閉錯誤
    
    # 統計每個IP的發送情況
    unique_ips_used = len(ip_send_count)
    avg_per_ip = sum(ip_send_count.values()) / unique_ips_used if unique_ips_used > 0 else 0
    
    # 最後一次更新統計
    try:
        shared_stats[process_id] = sent_count
        shared_errors[process_id] = error_count
    except:
        pass
    
    print(f"進程 {process_id} ({range_name}) 完成:")
    print(f"  總發送: {sent_count:,}, 錯誤: {error_count:,}")
    print(f"  使用IP數: {unique_ips_used:,}/{ip_count:,}")
    print(f"  平均每IP: {avg_per_ip:.1f} 個封包")

def load_config():
    """載入設定檔或使用預設設定"""
    default_config = {
        "total_qps": 200000,
        "ip_ranges": [
            {
                "name": "Normal_Range1",
                "start_ip": "10.201.0.1",
                "end_ip": "10.201.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range2", 
                "start_ip": "10.202.0.1",
                "end_ip": "10.202.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range3",
                "start_ip": "10.203.0.1", 
                "end_ip": "10.203.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range4",
                "start_ip": "10.204.0.1",
                "end_ip": "10.204.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range5",
                "start_ip": "10.205.0.1",
                "end_ip": "10.205.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range6",
                "start_ip": "10.206.0.1", 
                "end_ip": "10.206.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range7",
                "start_ip": "10.207.0.1",
                "end_ip": "10.207.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range8",
                "start_ip": "10.208.0.1",
                "end_ip": "10.208.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range9",
                "start_ip": "10.209.0.1",
                "end_ip": "10.209.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Normal_Range10",
                "start_ip": "10.210.0.1",
                "end_ip": "10.210.39.6",
                "percentage": 9.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 1.801,
                "comment": "9990個正常IP，每個1.801 QPS = 18k總QPS"
            },
            {
                "name": "Malicious_Range1",
                "start_ip": "10.101.0.1",
                "end_ip": "10.101.0.100",
                "percentage": 10.0,
                "use_ip_spoofing": True,
                "per_ip_qps": 200.0,
                "comment": "100個惡意IP，每個200 QPS = 20k總QPS"
            }
        ]
    }
    
    return default_config

def create_sample_config():
    """建立範例設定檔"""
    config = load_config()
    
    with open('dns_test_config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print("✓ 已建立範例設定檔: dns_test_config.json")
    print("✓ 你可以編輯此檔案來調整測試參數")

def main():
    parser = argparse.ArgumentParser(description='Enhanced DNS Load Test v1.0 Final')
    parser.add_argument('target_dns', help='Target DNS server IP')
    parser.add_argument('--config', '-c', help='Config file path', default='dns_test_config.json')
    parser.add_argument('--create-config', action='store_true', help='Create sample config file')
    parser.add_argument('--qps', type=int, help='Override total QPS')
    
    args = parser.parse_args()
    
    if args.create_config:
        create_sample_config()
        return
    
    # 載入設定
    try:
        if args.config and args.config != 'dns_test_config.json':
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = load_config()
    except FileNotFoundError:
        print(f"設定檔不存在，使用預設設定")
        config = load_config()
    
    # 覆蓋QPS設定
    if args.qps:
        config['total_qps'] = args.qps
    
    target_dns = args.target_dns
    total_qps = config['total_qps']
    
    print(f"DNS負載測試 v1.0 Final")
    print(f"目標DNS伺服器: {target_dns}")
    print(f"目標總QPS: {total_qps:,}")
    print("="*80)
    
    # 建立測試物件並處理IP範圍
    test = EnhancedDNSLoadTest(target_dns, config)
    
    # 顯示範圍資訊
    print("IP範圍設定:")
    total_percentage = 0
    total_expected_ips = 0
    for i, range_info in enumerate(test.ranges):
        start_ip_int = test.ip_to_int(range_info['start_ip'])
        end_ip_int = test.ip_to_int(range_info['end_ip'])
        ip_count = end_ip_int - start_ip_int + 1
        per_ip_qps = range_info.get('per_ip_qps', 2.0)
        total_expected_ips += ip_count
        
        print(f"  {i+1:2d}. {range_info['name']:18s}: {range_info['start_ip']:15s} - {range_info['end_ip']:15s}")
        print(f"      IP數量: {ip_count:5,} | 每IP QPS: {per_ip_qps:4.1f} | 總QPS: {range_info['qps']:6,} | 偽造: {'是' if range_info['use_ip_spoofing'] else '否'}")
        total_percentage += range_info['percentage']
    
    print(f"\n總比例: {total_percentage}%")
    print(f"總IP數量: {total_expected_ips:,}")
    print(f"預期總QPS: {sum(r['qps'] for r in test.ranges):,}")
    
    if total_percentage != 100:
        print(f"⚠️  警告: 總比例不等於100%")
    
    # 準備多進程參數
    cpu_count = multiprocessing.cpu_count()
    process_count = len(test.ranges)
    
    print(f"\nCPU核心數: {cpu_count}")
    print(f"進程數量: {process_count}")
    print("="*80)
    
    # 共享變數
    shared_stats = Array('i', [0] * process_count)
    shared_errors = Array('i', [0] * process_count)
    shared_running = Value('i', 1)
    
    # 準備進程參數
    processes = []
    for i, range_info in enumerate(test.ranges):
        # 添加IP整數範圍
        range_config = range_info.copy()
        range_config['start_ip_int'] = test.ip_to_int(range_info['start_ip'])
        range_config['end_ip_int'] = test.ip_to_int(range_info['end_ip'])
        
        p = Process(
            target=worker_process,
            args=(i, range_config, target_dns, shared_stats, shared_running, shared_errors)
        )
        processes.append(p)
    
    # 定義信號處理函數
    def signal_handler(signum, frame):
        print(f"\n收到停止信號，正在優雅地關閉所有進程...")
        shared_running.value = 0
    
    # 註冊信號處理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 啟動所有進程
    for p in processes:
        p.start()
        time.sleep(0.1)  # 縮短啟動間隔
    
    print(f"✓ 啟動了 {len(processes)} 個工作進程")
    print("按 Ctrl+C 停止測試")
    print("="*80)
    
    # 統計監控
    start_time = time.time()
    last_total = 0
    
    try:
        while shared_running.value:
            time.sleep(3)  # 每3秒統計一次
            
            current_total = sum(shared_stats[:])
            total_errors = sum(shared_errors[:])
            elapsed = time.time() - start_time
            
            instant_pps = (current_total - last_total) / 3
            avg_pps = current_total / elapsed if elapsed > 0 else 0
            
            print(f"[{elapsed:6.1f}s] 瞬時: {instant_pps:8,.0f} PPS | 平均: {avg_pps:8,.0f} PPS | 總計: {current_total:10,} | 錯誤: {total_errors:,}")
            
            last_total = current_total
            
    except KeyboardInterrupt:
        # 這個except應該不會被觸發，因為我們已經設定了信號處理器
        print("\n捕獲到KeyboardInterrupt，正在停止...")
        shared_running.value = 0
    
    # 等待所有進程結束
    print("等待所有進程完成...")
    for i, p in enumerate(processes):
        try:
            p.join(timeout=5)  # 給每個進程5秒時間結束
            if p.is_alive():
                print(f"進程 {i} 未在時限內結束，強制終止...")
                p.terminate()
                p.join(timeout=2)  # 再給2秒時間
                if p.is_alive():
                    print(f"進程 {i} 強制終止失敗，嘗試kill...")
                    try:
                        import os
                        os.kill(p.pid, 9)
                    except:
                        pass
        except Exception as e:
            print(f"處理進程 {i} 時出錯: {e}")
    
    # 最終統計
    final_total = sum(shared_stats[:])
    final_errors = sum(shared_errors[:])
    final_time = time.time() - start_time
    
    print("\n" + "="*80)
    print("測試完成！")
    print(f"總發送封包: {final_total:,}")
    print(f"總錯誤數: {final_errors:,}")
    print(f"測試時間: {final_time:.1f} 秒")
    if final_time > 0:
        print(f"平均QPS: {final_total/final_time:,.0f}")
        success_rate = (final_total - final_errors) / final_total * 100 if final_total > 0 else 0
        print(f"成功率: {success_rate:.1f}%")
    
    # 顯示各範圍統計
    print("\n各範圍統計:")
    for i, range_info in enumerate(test.ranges):
        sent = shared_stats[i]
        errors = shared_errors[i]
        pps = sent / final_time if final_time > 0 else 0
        
        # 計算IP數量和每IP平均QPS
        start_ip_int = test.ip_to_int(range_info['start_ip'])
        end_ip_int = test.ip_to_int(range_info['end_ip'])
        ip_count = end_ip_int - start_ip_int + 1
        per_ip_actual_qps = pps / ip_count if ip_count > 0 else 0
        per_ip_target_qps = range_info.get('per_ip_qps', 2.0)
        
        print(f"  {range_info['name']:18s}: {sent:8,} 封包 ({pps:6,.0f} PPS) | 錯誤: {errors:,}")
        print(f"    {'':20s}每IP實際: {per_ip_actual_qps:.2f} QPS (目標: {per_ip_target_qps:.1f} QPS)")
    
    print("="*80)
    print("程式已安全退出")  # 確認程式正常結束

if __name__ == "__main__":
    main()
