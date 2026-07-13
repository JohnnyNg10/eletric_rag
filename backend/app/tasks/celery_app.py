"""
Celery Application Configuration
"""
from celery import Celery
from app.config import settings

# 创建Celery实例
celery = Celery(
    'electric_rag',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Celery配置
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    task_soft_time_limit=3000,  # 50分钟软超时
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# 自动发现任务
celery.autodiscover_tasks(['app.tasks'])
