import random
import os
import sys
import logging
import subprocess
import time
import requests
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta
from typing import Tuple

# ==================== 你只需要改这里 ====================
PROJECT_PATH = "/ql/git_repo/everydayAutoPush"
LOG_FILE_PATH = "/ql/log/git_auto_push.log"
START_HOUR = 9                                   # 随机开始时间
END_HOUR = 21                                    # 随机结束时间
GIT_BRANCH = "main"
GITHUB_HOST = "github.com"
COMMIT_MESSAGE_TEMPLATE = "自动提交于 {}"

# 钉钉机器人Webhook地址
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=这里换成你自己的token"
# ======================================================

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== 钉钉通知 ====================
def send_dingtalk(msg: str):
    if not DINGTALK_WEBHOOK or "access_token=" not in DINGTALK_WEBHOOK:
        logger.info("未配置钉钉机器人，跳过通知")
        return
    try:
        # 加签逻辑（替换成你的机器人密钥）
        secret = "你的机器人加签密钥"  # 机器人设置页复制的密钥
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = f"{timestamp}\n{secret}"
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        # 拼接加签后的Webhook
        webhook = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"

        data = {
            "msgtype": "text",
            "text": {
                "content": msg
            }
        }
        headers = {"Content-Type": "application/json"}
        requests.post(webhook, json=data, headers=headers, timeout=10)
        logger.info("钉钉通知已发送")
    except Exception as e:
        logger.error(f"钉钉发送失败: {e}")

# ==================== Git 推送工具 ====================
class GitAutoPusher:
    def __init__(self, repo_path: str):
        self.repo_path = os.path.expanduser(repo_path)

    def _run_git(self, cmd: str):
        try:
            return subprocess.run(
                cmd,
                cwd=self.repo_path,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                timeout=120
            )
        except Exception as e:
            logger.error(f"Git命令失败: {cmd} | {str(e)}")
            return None

    def _create_ts_file(self):
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        fn = os.path.join(self.repo_path, f"auto_{ts}.txt")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(ts)

    def push(self) -> Tuple[bool, str]:
        try:
            self._create_ts_file()
            self._run_git("git add .")
            msg = COMMIT_MESSAGE_TEMPLATE.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self._run_git(f'git commit -m "{msg}"')
            self._run_git(f"git push origin {GIT_BRANCH}")
            return True, "推送成功 ✅"
        except Exception as e:
            return False, f"推送失败 ❌: {str(e)}"

# ==================== 生成今天随机时间 ====================
def get_random_today_time() -> datetime:
    now = datetime.now()
    start = now.replace(hour=START_HOUR, minute=0, second=0, microsecond=0)
    end = now.replace(hour=END_HOUR, minute=0, second=0, microsecond=0)

    delta = end - start
    random_sec = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_sec)

# ==================== 主函数 ====================
def main():
    # 1. 生成随机时间
    run_time = get_random_today_time()
    now = datetime.now()
    wait_sec = max(0.0, (run_time - now).total_seconds())

    logger.info(f"今日执行时间：{run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"等待 {wait_sec:.0f} 秒")

    # 2. 等待
    if wait_sec > 0:
        time.sleep(wait_sec)

    # 3. 执行推送
    pusher = GitAutoPusher(PROJECT_PATH)
    ok, msg = pusher.push()
    logger.info(f"结果：{msg}")

    # 4. 发钉钉
    title = "✅ 发钉钉Git自动推送成功" if ok else "❌ Git自动推送失败"
    content = f"{title}\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n结果：{msg}"
    send_dingtalk(content)

if __name__ == "__main__":
    main()