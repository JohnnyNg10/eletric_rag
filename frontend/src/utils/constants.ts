import type { Lane } from '../types/query';

export const APP_TITLE = import.meta.env.VITE_APP_TITLE || '电力知识库 RAG';

export const DEFAULT_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const DIMENSION_LABELS: Record<string, string> = {
  voltage_level: '电压等级',
  equipment_type: '设备类型',
  application_scene: '应用场景',
  neutral_grounding: '中性点接地方式',
  capacity_range: '容量范围',
  install_env: '安装环境',
  standard_series: '标准系列',
  protection_type: '保护类型',
};

export const LANE_META: Record<
  Lane,
  {
    icon: string;
    label: string;
    estimate: string;
    className: string;
  }
> = {
  fast: {
    icon: '⚡',
    label: '快车道',
    estimate: '预计 2-3 秒',
    className: 'is-fast',
  },
  slow: {
    icon: '🔄',
    label: '慢车道',
    estimate: '预计 5-8 秒，多步推理',
    className: 'is-slow',
  },
};
