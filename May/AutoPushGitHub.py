import os
import subprocess
from datetime import datetime, timedelta  # 导入 datetime 类和 timedelta 类
import logging
import time
import random
from typing import List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='cache/git_automation.log'
)

# 配置信息
REPO_PATH = "/root/code/weekendAutoPush"  # 替换为你的仓库路径
COMMIT_MESSAGE = "自动提交于 {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
GIT_BRANCH = "main"  # 替换为你的分支名
GITHUB_HOST = "github.com"


def check_ssh_connection():
    """检查SSH连接是否正常"""
    logging.info(f"正在检查与 {GITHUB_HOST} 的SSH连接...")

    try:
        # 尝试SSH连接测试
        cmd = f"ssh -T git@{GITHUB_HOST} 2>&1"
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=10
        )

        # 检查输出中是否包含成功信息
        if "Hi" in result.stdout:
            logging.info(f"与 {GITHUB_HOST} 的SSH连接成功")
            return True
        else:
            logging.error(f"SSH连接失败: {result.stdout}")
            return False

    except subprocess.TimeoutExpired:
        logging.error(f"检查与 {GITHUB_HOST} 的SSH连接时超时")
        return False
    except Exception as e:
        logging.error(f"检查SSH连接时出错: {str(e)}")
        return False


def run_git_command(command, show_output=True, critical=True):
    """执行Git命令并返回输出"""
    logging.info(f"正在执行Git命令: {command}")

    try:
        # 执行命令
        result = subprocess.run(
            command,
            cwd=REPO_PATH,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=120  # 设置超时时间，避免无限等待
        )

        if show_output and result.stdout:
            logging.info(f"命令输出:\n{result.stdout}")
            if critical:
                print(f"命令输出:\n{result.stdout}")

        return result.stdout or result

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        if "请求的上游分支" in error_msg:
            logging.error("错误：请求的上游分支不存在。尝试使用 'git push -u' 推送分支并配置上游关联。")
            print("错误：请求的上游分支不存在。将尝试自动设置上游分支...")
            return None
        elif "unknown option" in error_msg and "--show-current" in error_msg:
            logging.error("错误：当前Git版本不支持 'git branch --show-current' 命令，已使用 'git rev-parse --abbrev-ref HEAD' 替代。")
            return None
        elif "Updates were rejected because" in error_msg:
            logging.error("错误：远程仓库有新的提交，需要先拉取再推送。")
            print("错误：远程仓库有新的提交，正在尝试自动拉取...")
            return None
        else:
            logging.error(f"执行命令出错：{error_msg}")
            if critical:
                print(f"执行命令出错：{error_msg}", e)
            return None
    except subprocess.TimeoutExpired:
        logging.error(f"命令在120秒后超时。")
        print(f"命令在120秒后超时。")
        return None
    except Exception as e:
        logging.error(f"发生意外错误：{str(e)}")
        print(f"发生意外错误：{str(e)}")
        return None


def get_current_branch():
    """获取当前分支名，兼容旧版本Git"""
    logging.info("使用 'git rev-parse --abbrev-ref HEAD' 获取当前分支。")
    branch = run_git_command("git rev-parse --abbrev-ref HEAD", show_output=False)
    if branch:
        return branch.strip()
    logging.error("无法确定当前分支。请手动检查仓库的分支设置。")
    print("无法确定当前分支。请手动检查仓库的分支设置。")
    return None


def needs_upstream_setting():
    """检查是否需要设置上游分支"""
    status = run_git_command("git status -sb", show_output=False)
    if status and "[no upstream branch]" in status:
        return True
    return False


def handle_deleted_files():
    """处理已删除的文件，确保Git跟踪这些删除"""
    logging.info("检查并处理已删除的文件...")
    deleted_files = run_git_command("git ls-files --deleted", show_output=False)
    if deleted_files:
        files = deleted_files.strip().split('\n')
        for file in files:
            run_git_command(f"git rm --cached {file}", show_output=False)
        print(f"已处理 {len(files)} 个删除的文件")
        return True
    return False


def auto_push():
    print(f"开始git自动提交于 {datetime.now()}")
    logging.info(f"开始git自动提交于 {datetime.now()}")

    # 检查仓库目录是否存在
    if not os.path.exists(REPO_PATH):
        logging.error(f"错误：仓库路径 {REPO_PATH} 不存在。")
        print(f"错误：仓库路径 {REPO_PATH} 不存在。")
        return

    # 检查远程仓库类型
    remote_output = run_git_command("git remote -v", show_output=False)
    if not remote_output:
        logging.error("错误：无法获取远程仓库信息。")
        print("错误：无法获取远程仓库信息。")
        return

    # 统一使用SSH协议，简化检查逻辑
    if "git@github.com" not in remote_output:
        logging.error("错误：远程仓库未使用SSH协议。请切换到SSH协议。")
        print("错误：远程仓库未使用SSH协议。请切换到SSH协议。")
        return

    # 检查SSH连接
    if not check_ssh_connection():
        logging.error("错误：SSH连接有问题，操作终止。")
        print("错误：SSH连接有问题，操作终止。")
        return

    # 检查是否为git仓库
    if not os.path.exists(os.path.join(REPO_PATH, ".git")):
        logging.error(f"错误：{REPO_PATH} 不是一个Git仓库。")
        print(f"错误：{REPO_PATH} 不是一个Git仓库。")
        return

    # 拉取最新变更（避免冲突）
    print("正在拉取远程仓库最新变更...")
    run_git_command("git reset --hard HEAD && git stash clear && git pull --force origin main")
    # run_git_command("git fetch origin main && git merge -X theirs origin/main")
    # run_git_command("git pull --rebase origin main")
    # run_git_command("git pull origin main")

    # 创建以当前时间命名的txt文件
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_name = os.path.join(REPO_PATH, f"{current_time}.txt")
    with open(file_name, 'w') as f:
        pass

    # 检查仓库是否有变更
    status = run_git_command("git status --porcelain", show_output=False)
    if not status:
        logging.info("没有需要提交的变更。")
        print("没有需要提交的变更。")
        return

    # 处理已删除的文件
    # handle_deleted_files()

    # 添加所有变更（包括新文件和修改的文件）
    run_git_command("git add.")

    # 提交变更
    commit_output = run_git_command('git commit -m "{}"'.format(COMMIT_MESSAGE))

    # 获取当前分支
    current_branch = get_current_branch()
    if not current_branch:
        logging.error("由于分支检测失败，无法设置上游分支。")
        print("由于分支检测失败，无法设置上游分支。")
        return

    print(f"当前分支: {current_branch}")

    # 推送变更
    print(f"正在推送到 {GIT_BRANCH} 分支...")
    logging.info(f"正在推送到 {GIT_BRANCH} 分支...")

    # 尝试普通推送
    push_output = run_git_command(f"git push origin {current_branch}", critical=False)
    print('push_output', push_output)

    if push_output:
        print("推送成功！")
        logging.info("推送成功！")
    else:
        # 检查是否需要设置上游分支
        if needs_upstream_setting():
            print("检测到需要设置上游分支，尝试使用 -u 选项...")
            push_output = run_git_command(f"git push -u origin {current_branch}")
            if push_output:
                print("上游分支设置成功并推送完成！")
                logging.info("上游分支设置成功并推送完成！")
            else:
                # 最后尝试拉取并合并后再推送
                print("尝试拉取远程变更并合并...")
                run_git_command("git pull origin main")
                push_output = run_git_command(f"git push origin {current_branch}")
                if push_output:
                    print("拉取合并后推送成功！")
                    logging.info("拉取合并后推送成功！")
                else:
                    logging.error("推送失败。请检查之前的错误详情。")
                    print("推送失败。请检查之前的错误详情。")
        else:
            # 最后尝试拉取并合并后再推送
            print("尝试拉取远程变更并合并...")
            run_git_command("git pull origin main")
            push_output = run_git_command(f"git push origin {current_branch}")
            if push_output:
                print("拉取合并后推送成功！")
                logging.info("拉取合并后推送成功！")
            else:
                logging.error("推送失败。请检查之前的错误详情。")
                print("推送失败。请检查之前的错误详情。")

    print("Git自动化完成。")
    logging.info("Git自动化完成。")


def my_test():
    pass


def is_weekend() -> bool:
    """判断今天是否是周末"""
    today = datetime.now().weekday()
    return today >= 5  # 5是周六，6是周日


def generate_random_times() -> List[datetime]:
    """
    生成随机执行时间
    返回: 随机时间列表
    """
    # 今天的9点和21点
    now = datetime.now()
    start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=21, minute=0, second=0, microsecond=0)

    # 如果9点已过，则从明天开始
    if now > start_time:
        start_time = start_time + timedelta(days=1)
        end_time = end_time + timedelta(days=1)

    # 随机确定执行次数
    count = random.randint(1, 3)

    # 生成随机时间（秒数）
    delta_seconds = (end_time - start_time).total_seconds()
    interval_min = 10 * 60  # 10分钟的秒数

    # 生成不重叠的随机时间
    times = []
    while len(times) < count:
        # 生成一个随机时间点
        random_second = random.randint(0, int(delta_seconds))
        random_time = start_time + timedelta(seconds=random_second)

        # 检查是否与已有时间间隔足够
        if all(abs((random_time - t).total_seconds()) >= interval_min for t in times):
            times.append(random_time)

    # 按时间排序
    times.sort()
    return times


def run_once(target_time: datetime):
    """等待并执行一次任务"""
    now = datetime.now()
    wait_seconds = (target_time - now).total_seconds()

    if wait_seconds <= 0:
        logging.warning(f"目标时间已过: {target_time}")
        return

    logging.info(f"等待 {wait_seconds:.2f} 秒后执行任务")
    time.sleep(wait_seconds)

    # 执行任务
    auto_push()


def run_daily():
    """每天运行的主循环"""
    logging.info("程序启动，开始每日调度")

    while True:
        try:
            # 今天是否是周末
            weekend = is_weekend()
            logging.info(f"今日是否周末: {weekend}")

            if weekend:
                # 生成今天的随机时间
                times = generate_random_times()
                logging.info(f"生成的执行时间: {[t.strftime('%Y-%m-%d %H:%M:%S') for t in times]}")

                # 执行今天的所有任务
                for target_time in times:
                    run_once(target_time)

            # 等待到第二天的9点
            now = datetime.now()
            tomorrow = now + timedelta(days=1)
            next_start = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
            wait_seconds = (next_start - now).total_seconds()

            logging.info(f"今日任务执行完毕，等待 {wait_seconds / 3600:.2f} 小时到次日9点")
            time.sleep(wait_seconds)

        except Exception as e:
            logging.error(f"发生错误: {str(e)}")
            # 等待一段时间再重试
            time.sleep(60)


if __name__ == "__main__":
    # 设置程序在后台运行
    try:
        pid = os.fork()
        if pid > 0:
            # 父进程退出
            print(f"程序已在后台运行，PID: {pid}")
            exit(0)
        # 分离会话
        os.setsid()
        # 执行主循环
        run_daily()
        # 捕获异常
    except OSError:
        logging.error("创建子进程失败")
        exit(1)
    except Exception as e:
        logging.error(f"发生错误: {str(e)}")