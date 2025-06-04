import requests
import json
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

"""
ChatAI API 性能测试脚本

这个脚本用于测试API的性能指标，包括：
1. 响应时间测试
2. 并发请求测试
3. 负载测试
4. 稳定性测试
"""

class PerformanceTester:
    """性能测试类"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.results = []
    
    def single_request_test(self, endpoint: str, method: str = "GET", 
                           payload: Dict = None, timeout: int = 30) -> Dict[str, Any]:
        """单次请求测试"""
        start_time = time.time()
        response = None
        
        try:
            if method.upper() == "GET":
                response = requests.get(f"{self.base_url}{endpoint}", timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(
                    f"{self.base_url}{endpoint}", 
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout
                )
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            end_time = time.time()
            response_time = end_time - start_time
            
            return {
                "success": True,
                "status_code": response.status_code,
                "response_time": response_time,
                "response_size": len(response.content),
                "error": None
            }
            
        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time
            
            return {
                "success": False,
                "status_code": None,
                "response_time": response_time,
                "response_size": 0,
                "error": str(e)
            }
    
    def test_health_check_performance(self, num_requests: int = 100):
        """测试健康检查接口性能"""
        print(f"\n🏃‍♂️ 健康检查性能测试 ({num_requests} 次请求)")
        print("-" * 50)
        
        response_times = []
        success_count = 0
        
        for i in range(num_requests):
            result = self.single_request_test("/health")
            response_times.append(result["response_time"])
            
            if result["success"] and result["status_code"] == 200:
                success_count += 1
            
            if (i + 1) % 20 == 0:
                print(f"已完成 {i + 1}/{num_requests} 次请求")
        
        # 计算统计数据
        avg_time = statistics.mean(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        p95_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
        
        print(f"\n📊 健康检查性能结果:")
        print(f"  成功率: {success_count}/{num_requests} ({success_count/num_requests*100:.1f}%)")
        print(f"  平均响应时间: {avg_time*1000:.2f}ms")
        print(f"  最小响应时间: {min_time*1000:.2f}ms")
        print(f"  最大响应时间: {max_time*1000:.2f}ms")
        print(f"  95%分位数: {p95_time*1000:.2f}ms")
        
        return {
            "test_type": "health_check_performance",
            "success_rate": success_count/num_requests,
            "avg_response_time": avg_time,
            "min_response_time": min_time,
            "max_response_time": max_time,
            "p95_response_time": p95_time
        }
    
    def test_concurrent_requests(self, num_threads: int = 10, requests_per_thread: int = 10):
        """测试并发请求"""
        print(f"\n🚀 并发请求测试 ({num_threads} 线程，每线程 {requests_per_thread} 次请求)")
        print("-" * 50)
        
        def worker():
            """工作线程函数"""
            thread_results = []
            for _ in range(requests_per_thread):
                result = self.single_request_test("/health")
                thread_results.append(result)
            return thread_results
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_thread = {executor.submit(worker): i for i in range(num_threads)}
            all_results = []
            
            for future in as_completed(future_to_thread):
                thread_id = future_to_thread[future]
                try:
                    thread_results = future.result()
                    all_results.extend(thread_results)
                    print(f"线程 {thread_id} 完成")
                except Exception as e:
                    print(f"线程 {thread_id} 异常: {str(e)}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 分析结果
        successful_requests = [r for r in all_results if r["success"]]
        failed_requests = [r for r in all_results if not r["success"]]
        
        if successful_requests:
            response_times = [r["response_time"] for r in successful_requests]
            avg_time = statistics.mean(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
        else:
            avg_time = max_time = min_time = 0
        
        total_requests = num_threads * requests_per_thread
        throughput = total_requests / total_time
        
        print(f"\n📊 并发测试结果:")
        print(f"  总请求数: {total_requests}")
        print(f"  成功请求: {len(successful_requests)}")
        print(f"  失败请求: {len(failed_requests)}")
        print(f"  总耗时: {total_time:.2f}s")
        print(f"  吞吐量: {throughput:.2f} 请求/秒")
        print(f"  平均响应时间: {avg_time*1000:.2f}ms")
        print(f"  最大响应时间: {max_time*1000:.2f}ms")
        print(f"  最小响应时间: {min_time*1000:.2f}ms")
        
        return {
            "test_type": "concurrent_requests",
            "total_requests": total_requests,
            "successful_requests": len(successful_requests),
            "failed_requests": len(failed_requests),
            "total_time": total_time,
            "throughput": throughput,
            "avg_response_time": avg_time
        }
    
    def test_process_endpoint_performance(self, num_requests: int = 50):
        """测试消息处理接口性能"""
        print(f"\n💬 消息处理性能测试 ({num_requests} 次请求)")
        print("-" * 50)
        
        payload = {
            "session_id": "perf_test_session",
            "user_id": "perf_test_user",
            "platform": "web",
            "language": "zh",
            "status": 0,  # 未登录，避免复杂处理
            "messages": "性能测试消息",
            "site": 1,
            "transfer_human": 0
        }
        
        response_times = []
        success_count = 0
        
        for i in range(num_requests):
            result = self.single_request_test("/process", "POST", payload, timeout=30)
            response_times.append(result["response_time"])
            
            if result["success"] and result["status_code"] == 200:
                success_count += 1
            
            if (i + 1) % 10 == 0:
                print(f"已完成 {i + 1}/{num_requests} 次请求")
        
        if response_times:
            avg_time = statistics.mean(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            if len(response_times) >= 2:
                p95_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_time
            else:
                p95_time = max_time
        else:
            avg_time = min_time = max_time = p95_time = 0
        
        print(f"\n📊 消息处理性能结果:")
        print(f"  成功率: {success_count}/{num_requests} ({success_count/num_requests*100:.1f}%)")
        print(f"  平均响应时间: {avg_time*1000:.2f}ms")
        print(f"  最小响应时间: {min_time*1000:.2f}ms")
        print(f"  最大响应时间: {max_time*1000:.2f}ms")
        print(f"  95%分位数: {p95_time*1000:.2f}ms")
        
        return {
            "test_type": "process_performance",
            "success_rate": success_count/num_requests,
            "avg_response_time": avg_time,
            "min_response_time": min_time,
            "max_response_time": max_time,
            "p95_response_time": p95_time
        }
    
    def test_load_stability(self, duration_minutes: int = 5):
        """负载稳定性测试"""
        print(f"\n⏱️  负载稳定性测试 (持续 {duration_minutes} 分钟)")
        print("-" * 50)
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        request_count = 0
        success_count = 0
        response_times = []
        
        while time.time() < end_time:
            result = self.single_request_test("/health")
            request_count += 1
            response_times.append(result["response_time"])
            
            if result["success"] and result["status_code"] == 200:
                success_count += 1
            
            if request_count % 50 == 0:
                elapsed = time.time() - start_time
                remaining = (end_time - time.time()) / 60
                print(f"已运行 {elapsed/60:.1f} 分钟，剩余 {remaining:.1f} 分钟，已发送 {request_count} 次请求")
            
            time.sleep(0.1)  # 每100ms发送一次请求
        
        total_duration = time.time() - start_time
        
        if response_times:
            avg_time = statistics.mean(response_times)
            throughput = request_count / total_duration
        else:
            avg_time = 0
            throughput = 0
        
        print(f"\n📊 负载稳定性测试结果:")
        print(f"  测试时长: {total_duration/60:.1f} 分钟")
        print(f"  总请求数: {request_count}")
        print(f"  成功请求: {success_count}")
        print(f"  成功率: {success_count/request_count*100:.1f}%")
        print(f"  平均吞吐量: {throughput:.2f} 请求/秒")
        print(f"  平均响应时间: {avg_time*1000:.2f}ms")
        
        return {
            "test_type": "load_stability",
            "duration_minutes": total_duration/60,
            "total_requests": request_count,
            "success_rate": success_count/request_count if request_count > 0 else 0,
            "throughput": throughput,
            "avg_response_time": avg_time
        }
    
    def run_all_performance_tests(self):
        """运行所有性能测试"""
        print("=" * 60)
        print("🚀 ChatAI API 性能测试套件")
        print("=" * 60)
        
        results = []
        
        # 基础性能测试
        results.append(self.test_health_check_performance(100))
        
        # 并发测试
        results.append(self.test_concurrent_requests(5, 10))
        
        # 消息处理性能测试
        results.append(self.test_process_endpoint_performance(20))
        
        # 负载稳定性测试（较短时间）
        results.append(self.test_load_stability(2))
        
        # 生成性能报告
        self.generate_performance_report(results)
    
    def generate_performance_report(self, results: List[Dict]):
        """生成性能测试报告"""
        print("\n" + "=" * 60)
        print("📈 性能测试总结报告")
        print("=" * 60)
        
        for result in results:
            test_type = result["test_type"]
            print(f"\n📋 {test_type}:")
            
            if "success_rate" in result:
                print(f"  ✅ 成功率: {result['success_rate']*100:.1f}%")
            
            if "avg_response_time" in result:
                print(f"  ⏱️  平均响应时间: {result['avg_response_time']*1000:.2f}ms")
            
            if "throughput" in result:
                print(f"  🚀 吞吐量: {result['throughput']:.2f} 请求/秒")
        
        # 保存性能测试结果
        try:
            with open("performance_test_results.json", "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": time.time(),
                    "results": results
                }, f, ensure_ascii=False, indent=2)
            print(f"\n📄 性能测试结果已保存到 performance_test_results.json")
        except Exception as e:
            print(f"⚠️  保存性能测试结果失败: {str(e)}")
        
        print("=" * 60)

def main():
    """主函数"""
    tester = PerformanceTester()
    tester.run_all_performance_tests()

if __name__ == "__main__":
    main() 