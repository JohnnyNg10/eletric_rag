"""
检索引擎层 (Retrieval Layer)

职责：
- 路由决策（快慢车道）
- 快车道：固定流水线检索
- 慢车道：自适应多跳检索
"""
from .router import Router, RouteDecision
from .fast_lane import FastLane, FastLaneResult
from .slow_lane import SlowLane, SlowLaneResult

__all__ = [
    'Router',
    'RouteDecision',
    'FastLane',
    'FastLaneResult',
    'SlowLane',
    'SlowLaneResult',
]
