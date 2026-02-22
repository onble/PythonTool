import os
import subprocess
from datetime import datetime
import logging
from typing import Optional, Tuple

# 通用配置
COMMIT_MESSAGE_TEMPLATE = "自动提交于 {}"
GIT_BRANCH = "main"
GITHUB_HOST = "github.com"


class GitAutoPusher:
    """Git自动推送工具类"""

    def __init__(self, repo_path: str):
        """
        初始化推送器
        :param repo_path: Git仓库本地路径
        """
        self.repo_path = os.path.expanduser(repo_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        self._validate_path()

    def _validate_path(self) -> None:
        """验证仓库路径有效性"""
        if not os.path.exists(self.repo_path):
            raise ValueError(f"仓库路径 {self.repo_path} 不存在")
        if not os.path.exists(os.path.join(self.repo_path, ".git")):
            raise ValueError(f"{self.repo_path} 不是一个Git仓库")

    def _run_git_command(self, command: str, show_output: bool = True) -> Optional[str]:
        """执行Git命令并指定UTF-8编码"""
        self.logger.info(f"执行Git命令: {command}")

        try:
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # 指定UTF-8编码
                universal_newlines=True,
                encoding='utf-8',  # 新增编码设置
                timeout=120
            )

            if show_output and result.stdout:
                self.logger.info(f"命令输出:\n{result.stdout}")

            return result.stdout or None

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip()
            self._handle_git_error(error_msg)
            return None
        except subprocess.TimeoutExpired:
            self.logger.error("命令执行超时（120秒）")
            return None
        except UnicodeDecodeError as e:
            self.logger.error(f"解码错误: {str(e)}")
            # 尝试使用错误恢复模式重新读取
            try:
                return e.output.decode('utf-8', errors='replace')
            except:
                return None
        except Exception as e:
            self.logger.error(f"意外错误: {str(e)}", exc_info=True)
            return None

    def _handle_git_error(self, error_msg: str) -> None:
        """处理常见的Git错误"""
        error_handlers = {
            "请求的上游分支": lambda: self.logger.error("错误：上游分支不存在，尝试使用 'git push -u'"),
            "unknown option": lambda: self.logger.error("错误：Git版本不兼容，已使用备用命令"),
            "Updates were rejected": lambda: self.logger.error("错误：远程有更新，需先拉取")
        }

        for key, handler in error_handlers.items():
            if key in error_msg:
                handler()
                return
        self.logger.error(f"Git错误: {error_msg}")

    def check_ssh_connection(self) -> bool:
        """检查SSH连接状态（Windows版本）"""
        self.logger.info(f"检查与 {GITHUB_HOST} 的SSH连接...")

        try:
            # 确保Windows上安装了OpenSSH或使用其他SSH客户端
            result = subprocess.run(
                f"ssh -T git@{GITHUB_HOST}",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=10
            )

            if "Hi" in result.stdout:
                self.logger.info("SSH连接验证成功")
                return True
            self.logger.error(f"SSH连接失败: {result.stdout}")
            return False
        except Exception as e:
            self.logger.error(f"SSH检查异常: {str(e)}")
            return False

    def _get_current_branch(self) -> Optional[str]:
        """获取当前分支名称"""
        branch = self._run_git_command("git rev-parse --abbrev-ref HEAD", show_output=False)
        return branch.strip() if branch else None

    def _needs_upstream(self) -> bool:
        """检查是否需要设置上游分支"""
        status = self._run_git_command("git status -sb", show_output=False)
        return bool(status and "[no upstream branch]" in status)

    def _handle_deleted_files(self) -> bool:
        """处理已删除文件的跟踪"""
        deleted = self._run_git_command("git ls-files --deleted", show_output=False)
        if not deleted:
            return False

        for f in deleted.strip().split('\n'):
            self._run_git_command(f"git rm --cached {f}")
        return True

    def _generate_commit_message(self) -> str:
        """生成带时间戳的提交信息"""
        return COMMIT_MESSAGE_TEMPLATE.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def _create_timestamp_file(self) -> str:
        """创建时间戳文件"""
        filename = os.path.join(self.repo_path, f"{datetime.now().strftime('%Y%m%d%H%M%S')}.txt")
        with open(filename, 'w') as f:
            pass
        return filename

    def execute_push_flow(self) -> Tuple[bool, str]:
        """
        执行完整的推送流程
        :return: (是否成功, 结果描述)
        """
        # 前置检查
        if not self.check_ssh_connection():
            return False, "SSH连接失败"

        # 创建时间戳文件
        try:
            self._create_timestamp_file()
        except Exception as e:
            self.logger.error(f"创建文件失败: {str(e)}")
            return False, "文件创建失败"

        # 拉取最新代码
        if not self._run_git_command("git reset --hard HEAD && git stash clear && git pull --force origin main"):
            return False, "代码拉取失败"

        # 处理变更
        self._handle_deleted_files()
        self._run_git_command("git add .")

        # 提交变更
        commit_msg = self._generate_commit_message()
        if not self._run_git_command(f'git commit -m "{commit_msg}"'):
            return False, "提交失败"

        # 推送变更
        branch = self._get_current_branch()
        if not branch:
            return False, "分支获取失败"

        self._attempt_push(branch)
        return True, "推送结束"

    def _attempt_push(self, branch: str) -> None:
        """尝试多种推送方式"""
        # 首次推送尝试
        if self._run_git_command(f"git push origin {branch}"):
            return

        # 处理上游分支设置
        if self._needs_upstream():
            self._run_git_command(f"git push -u origin {branch}")
            return

        # 最终尝试拉取合并后推送
        self._run_git_command("git pull origin main")
        self._run_git_command(f"git push origin {branch}")
        return


def auto_push(repo_path: str) -> None:
    """
    自动推送入口函数
    :param repo_path: Git仓库本地路径
    """
    logging.info(f"启动Git自动推送流程于 {repo_path}")

    try:
        pusher = GitAutoPusher(repo_path)
        success, message = pusher.execute_push_flow()
        logging.info(f"推送结果: {message}" if success else f"推送失败: {message}")
    except ValueError as e:
        logging.error(str(e))
    except Exception as e:
        logging.error(f"自动推送异常: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    auto_push(r'C:\code\weekendAutoPush')  # 在此传入仓库路径
