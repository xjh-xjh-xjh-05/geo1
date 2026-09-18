"""
数据库迁移脚本
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic.config import Config
from alembic import command
from api.core.config import settings


def init_alembic():
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    
    command.init(alembic_cfg, "alembic")
    print("Alembic initialized.")


def generate_migration(message: str):
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    
    command.revision(alembic_cfg, autogenerate=True, message=message)
    print(f"Migration generated: {message}")


def apply_migrations():
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    
    command.upgrade(alembic_cfg, "head")
    print("Migrations applied.")


def rollback_migration(steps: int = 1):
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    
    command.downgrade(alembic_cfg, f"-{steps}")
    print(f"Rolled back {steps} migration(s).")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database migration tool")
    parser.add_argument("command", choices=["init", "migrate", "apply", "rollback"])
    parser.add_argument("--message", "-m", help="Migration message")
    parser.add_argument("--steps", "-s", type=int, default=1, help="Rollback steps")
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_alembic()
    elif args.command == "migrate":
        if not args.message:
            print("Error: --message is required for migrate command")
            sys.exit(1)
        generate_migration(args.message)
    elif args.command == "apply":
        apply_migrations()
    elif args.command == "rollback":
        rollback_migration(args.steps)
