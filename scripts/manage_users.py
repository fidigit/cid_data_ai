from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import UserAccount, UserRole
from app.services.auth import hash_password


def upsert_user(username: str, display_name: str | None, role: UserRole) -> None:
    password = getpass.getpass("请输入密码（不会显示）：")
    confirmation = getpass.getpass("再次输入密码：")
    if password != confirmation:
        raise SystemExit("两次密码输入不一致。")
    encoded = hash_password(password)
    with SessionLocal() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.username == username))
        if account is None:
            account = UserAccount(username=username, password_hash=encoded)
            db.add(account)
        account.password_hash = encoded
        account.display_name = display_name or username
        account.role = role
        account.is_active = True
        db.commit()
    print(f"账号 {username} 已保存，角色：{role.value}。")


def deactivate_user(username: str) -> None:
    with SessionLocal() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.username == username))
        if account is None:
            raise SystemExit("账号不存在。")
        account.is_active = False
        db.commit()
    print(f"账号 {username} 已停用。")


def list_users() -> None:
    with SessionLocal() as db:
        accounts = db.scalars(select(UserAccount).order_by(UserAccount.username))
        for account in accounts:
            state = "active" if account.is_active else "disabled"
            print(f"{account.username}\t{account.role.value}\t{state}\t{account.display_name or ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description="管理埋点查询终端本地账号")
    subparsers = parser.add_subparsers(dest="command", required=True)
    upsert = subparsers.add_parser("upsert", help="新增账号或重置密码")
    upsert.add_argument("username")
    upsert.add_argument("--display-name")
    upsert.add_argument("--role", choices=[item.value for item in UserRole], default="member")
    deactivate = subparsers.add_parser("deactivate", help="停用账号")
    deactivate.add_argument("username")
    subparsers.add_parser("list", help="列出账号（不显示密码哈希）")
    args = parser.parse_args()
    init_db()
    if args.command == "upsert":
        upsert_user(args.username, args.display_name, UserRole(args.role))
    elif args.command == "deactivate":
        deactivate_user(args.username)
    else:
        list_users()


if __name__ == "__main__":
    main()
