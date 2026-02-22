import ctypes

import schedule
import time
import random
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import NoReturn, List, Optional
from AutoPushGitHub import auto_push

# 调整为Windows风格路径
PROJECT_PATH = r'C:\code\everydayAutoPush'
LOG_FILE_PATH = r'C:\cache\git_automation_daily.log'  # 日志文件路径
MAX_LOG_SIZE = 2 * 1024 * 1024  # 2MB


class DailyRandomScheduler:
    """每日随机时间任务调度器（新增初始化任务功能）"""

    def __init__(self, start_hour: int = 9, end_hour: int = 21):
        """
        初始化调度器
        :param start_hour: 开始小时数（包含）
        :param end_hour: 结束小时数（包含）
        """
        # 配置日志
        self.logger = logging.getLogger(__name__)

        # 私有变量
        self._start_time = timedelta(hours=start_hour)
        self._end_time = timedelta(hours=end_hour)
        self._min_interval = timedelta(minutes=10)
        self._job_count_range = (1, 3)
        self._scheduled_jobs: List[schedule.Job] = []
        self._initial_job: Optional[schedule.Job] = None  # 初始化任务引用

        # 初始化每日任务
        self._schedule_daily_jobs()
        # 安排启动后1分钟的初始化任务
        self._schedule_initial_task()

    def _schedule_initial_task(self) -> None:
        """安排启动后1分钟执行的初始化任务"""
        initial_time = datetime.now() + timedelta(minutes=1)
        try:
            self._initial_job = schedule.every().day.at(
                initial_time.strftime('%H:%M')
            ).do(self._execute_initial_task)
            self.logger.info(f"初始化任务安排在 {initial_time.strftime('%H:%M')} 执行")
        except Exception as e:
            self.logger.error(f"初始化任务安排失败: {str(e)}", exc_info=True)

    def _execute_initial_task(self) -> None:
        """执行初始化任务并自取消"""
        self.logger.info("开始执行初始化任务...")
        try:
            # 执行前检查并清理日志
            self._check_and_clean_log()
            auto_push(PROJECT_PATH)
            self.logger.info("初始化任务执行成功")
        except Exception as e:
            self.logger.error(f"初始化任务执行失败: {str(e)}", exc_info=True)
        finally:
            if self._initial_job:
                schedule.cancel_job(self._initial_job)
                self.logger.info("已移除初始化任务调度")
            self._initial_job = None

    def _generate_time_slots(self) -> List[datetime.time]:
        """生成符合条件的时间槽"""
        time_slots = []
        current_date = datetime.now().date()

        # 生成随机任务数量
        task_count = random.randint(*self._job_count_range)

        # 计算可用时间窗口（秒）
        total_seconds = (self._end_time - self._start_time).total_seconds()

        # 检查时间窗口是否足够
        min_required = (task_count - 1) * self._min_interval.total_seconds()
        if total_seconds < min_required:
            self.logger.warning(f"时间窗口不足，无法生成{task_count}个任务")
            return []

        # 生成初始随机时间
        start_point = random.randint(0, int(total_seconds - min_required))
        last_time = self._start_time + timedelta(seconds=start_point)
        time_slots.append(last_time)

        # 生成后续时间点
        for _ in range(task_count - 1):
            # 计算下一个可用时间窗口
            min_next = last_time + self._min_interval
            max_next = self._end_time - (task_count - len(time_slots) - 1) * self._min_interval

            if min_next >= max_next:
                break  # 剩余时间不足

            # 在剩余窗口中随机生成时间
            next_seconds = random.randint(
                int(min_next.total_seconds()),
                int(max_next.total_seconds())
            )
            last_time = timedelta(seconds=next_seconds)
            time_slots.append(last_time)

        # 转换为datetime.time对象
        return [(datetime.combine(current_date, datetime.min.time()) + t).time() for t in time_slots]

    def _schedule_daily_jobs(self) -> None:
        """安排每日任务"""
        # 清除旧任务
        for job in self._scheduled_jobs:
            schedule.cancel_job(job)
        self._scheduled_jobs.clear()

        # 生成新时间槽
        time_slots = self._generate_time_slots()
        if not time_slots:
            self.logger.error("未能生成有效时间槽")
            return

        self.logger.info(f"今日计划执行时间：{[t.strftime('%H:%M') for t in time_slots]}")

        # 安排每个任务
        for t in time_slots:
            job = schedule.every().day.at(t.strftime('%H:%M')).do(self._execute_work)
            self._scheduled_jobs.append(job)

        # 安排次日任务重置
        schedule.every().day.at("00:00").do(self._schedule_daily_jobs)

    def _execute_work(self) -> None:
        """执行工作任务"""
        self.logger.info("开始执行日常工作...")
        try:
            # 执行前检查并清理日志
            self._check_and_clean_log()
            auto_push(PROJECT_PATH)
            self.logger.info("日常工作执行完成")
        except Exception as e:
            self.logger.error(f"日常工作执行失败：{str(e)}", exc_info=True)

    def _check_and_clean_log(self) -> None:
        """检查并清理日志文件"""
        try:
            if os.path.exists(LOG_FILE_PATH):
                file_size = os.path.getsize(LOG_FILE_PATH)
                if file_size > MAX_LOG_SIZE:
                    self.logger.info(f"日志文件大小为 {file_size} 字节，超过 {MAX_LOG_SIZE} 字节，准备清理")

                    with open(LOG_FILE_PATH, 'r') as f:
                        lines = f.readlines()

                    if len(lines) > 1:  # 确保至少保留一行
                        half = len(lines) // 2
                        remaining_lines = lines[half:]

                        with open(LOG_FILE_PATH, 'w') as f:
                            f.writelines(remaining_lines)

                        self.logger.info(f"已删除 {half} 行日志，保留 {len(remaining_lines)} 行")
                    else:
                        self.logger.info("日志文件行数不足，跳过清理")
            else:
                self.logger.info("日志文件不存在，跳过检查")
        except Exception as e:
            self.logger.error(f"日志检查/清理失败: {str(e)}", exc_info=True)

    def run(self) -> NoReturn:
        """启动调度器主循环"""
        self.logger.info("调度器进入主循环...")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("用户中断，停止调度器")
            sys.exit(0)


class WindowsService:
    """Windows服务封装（替代Linux守护进程）"""

    def __init__(self, pidfile: str = r'C:\cache\git_automation_daily.pid'):
        self.pidfile = pidfile
        self.logger = logging.getLogger(__name__)

        # 日志配置
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - PID:%(process)d - %(levelname)s - %(message)s',
            filename=LOG_FILE_PATH
        )

    def _is_running(self) -> bool:
        """检查进程是否正在运行（Windows版本）"""
        try:
            if os.path.exists(self.pidfile):
                with open(self.pidfile, 'r') as f:
                    pid = int(f.read())
                # 在Windows中检查进程是否存在
                import ctypes
                kernel32 = ctypes.WinDLL('kernel32')
                process = kernel32.OpenProcess(1, 0, pid)
                if process:
                    kernel32.CloseHandle(process)
                    return True
            return False
        except (FileNotFoundError, ValueError, Exception):
            return False

    def start(self) -> None:
        """启动服务"""
        if self._is_running():
            self.logger.error("进程已在运行中")
            sys.exit(1)

        # 启动前检查并清理日志
        self._check_and_clean_log()

        # 记录进程PID
        with open(self.pidfile, 'w') as f:
            f.write(str(os.getpid()))
        self.logger.info(f"服务启动，PID: {os.getpid()}")

        # 启动调度器
        DailyRandomScheduler().run()

    def _check_and_clean_log(self) -> None:
        """检查并清理日志文件"""
        try:
            if os.path.exists(LOG_FILE_PATH):
                file_size = os.path.getsize(LOG_FILE_PATH)
                if file_size > MAX_LOG_SIZE:
                    self.logger.info(f"日志文件大小为 {file_size} 字节，超过 {MAX_LOG_SIZE} 字节，准备清理")

                    with open(LOG_FILE_PATH, 'r') as f:
                        lines = f.readlines()

                    if len(lines) > 1:  # 确保至少保留一行
                        half = len(lines) // 2
                        remaining_lines = lines[half:]

                        with open(LOG_FILE_PATH, 'w') as f:
                            f.writelines(remaining_lines)

                        self.logger.info(f"已删除 {half} 行日志，保留 {len(remaining_lines)} 行")
                    else:
                        self.logger.info("日志文件行数不足，跳过清理")
            else:
                self.logger.info("日志文件不存在，跳过检查")
        except Exception as e:
            self.logger.error(f"日志检查/清理失败: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # 检查是否以管理员权限运行（部分操作需要）
    if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
        print("请以管理员权限运行此程序")
        sys.exit(1)

    # 启动Windows服务
    WindowsService().start()