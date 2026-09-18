"""
Makefile - 便捷命令
"""

.PHONY: help install dev run test clean docker-build docker-up docker-down docker-logs db-init db-migrate

help:
	@echo "GEO虚假内容检测平台 - 可用命令:"
	@echo ""
	@echo "开发命令:"
	@echo "  make install        安装依赖"
	@echo "  make dev            启动开发服务器"
	@echo "  make run            启动生产服务器"
	@echo "  make test           运行测试"
	@echo "  make clean          清理临时文件"
	@echo ""
	@echo "Docker命令:"
	@echo "  make docker-build   构建Docker镜像"
	@echo "  make docker-up      启动Docker容器"
	@echo "  make docker-down    停止Docker容器"
	@echo "  make docker-logs    查看Docker日志"
	@echo ""
	@echo "数据库命令:"
	@echo "  make db-init        初始化数据库"
	@echo "  make db-migrate     运行数据库迁移"
	@echo "  make db-reset       重置数据库"

install:
	pip install -r requirements.txt

dev:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

run:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

test:
	pytest tests/ -v --cov=api --cov-report=html

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage

docker-build:
	docker build -t geo-fake-detection:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

db-init:
	python scripts/init_db.py

db-migrate:
	python scripts/migrate.py apply

db-reset:
	dropdb geo_fake_detection || true
	createdb geo_fake_detection
	python scripts/init_db.py

streamlit:
	streamlit run app.py
