"""
把 state/ + 代码变更打包推到 GitHub 私有仓库做备份。

用法：
  python3 scripts/backup_state.py                # commit + push
  python3 scripts/backup_state.py --state-only   # 只 add state/
  python3 scripts/backup_state.py --dry-run      # 看会做啥不真做

依赖：当前 repo 已配 origin remote（私有 GitHub 仓库），且 state/ 已从 .gitignore 移除。
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def _run(cmd: list[str], dry: bool, capture: bool = False) -> str:
    print("$", " ".join(cmd))
    if dry:
        return ""
    if capture:
        return subprocess.check_output(cmd, cwd=_ROOT, text=True)
    return subprocess.check_call(cmd, cwd=_ROOT) and ""


def main() -> None:
    parser = argparse.ArgumentParser(description="备份 state/ 到 GitHub")
    parser.add_argument("--state-only", action="store_true", help="只 add state/")
    parser.add_argument("--dry-run",    action="store_true", help="只打印不执行")
    args = parser.parse_args()

    # 1. 检查 remote
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=_ROOT, text=True
        ).strip()
    except subprocess.CalledProcessError:
        print("没找到 origin remote。先跑：gh repo create CaufieldZ/agents-personal --private --source=. --remote=origin")
        sys.exit(1)
    print(f"remote: {remote}")

    # 2. add
    target = ["state/"] if args.state_only else ["-A"]
    _run(["git", "add", *target], args.dry_run)

    # 3. 是否有变化
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=_ROOT
    ).returncode
    if diff == 0 and not args.dry_run:
        print("没有变化，跳过 commit/push")
        return

    # 4. commit
    msg = f"backup: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    _run(["git", "commit", "-m", msg], args.dry_run)

    # 5. push
    _run(["git", "push", "origin", "HEAD"], args.dry_run)

    print(f"\n✓ 备份完成：{msg}")


if __name__ == "__main__":
    main()
