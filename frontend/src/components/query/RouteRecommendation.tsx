import type { Lane } from '../../types/query';
import { LANE_META } from '../../utils/constants';
import { getEffectiveLane } from '../../utils/query';

interface RouteRecommendationProps {
  lane: Lane;
  confidence: number;
  reason: string;
  userLane: Lane | null;
  onToggle: () => void;
}

function getConfidenceLevel(confidence: number) {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.6) return 'medium';
  return 'low';
}

export default function RouteRecommendation({
  lane,
  confidence,
  reason,
  userLane,
  onToggle,
}: RouteRecommendationProps) {
  const effectiveLane = getEffectiveLane(lane, userLane);
  const suggestedMeta = LANE_META[lane];
  const effectiveMeta = LANE_META[effectiveLane];
  const confidencePercent = Math.round(confidence * 100);
  const confidenceLevel = getConfidenceLevel(confidence);

  return (
    <section className="route-card" aria-labelledby="route-title">
      <div className="route-header">
        <div>
          <div className="section-title" id="route-title">
            推荐路由
          </div>
          <div className={`lane-badge ${effectiveMeta.className}`}>
            <span aria-hidden="true">{effectiveMeta.icon}</span>
            <span>{effectiveMeta.label}</span>
            <span className="lane-estimate">{effectiveMeta.estimate}</span>
          </div>
        </div>
        <button type="button" className="secondary-button" onClick={onToggle} aria-pressed={userLane !== null}>
          {userLane === null
            ? `切换为${lane === 'fast' ? '慢车道' : '快车道'}`
            : '恢复系统建议'}
        </button>
      </div>

      {userLane !== null ? (
        <div className="info-banner subtle">
          您已选择{effectiveMeta.label}（系统建议：{suggestedMeta.label}）
        </div>
      ) : null}

      <div className="confidence-row">
        <span>置信度：{confidencePercent}%</span>
        <span>
          {confidenceLevel === 'high'
            ? '建议直接采用'
            : confidenceLevel === 'medium'
              ? '建议核对'
              : '不确定，请主动选择'}
        </span>
      </div>
      <div className="confidence-bar" aria-hidden="true">
        <div
          className={`confidence-fill level-${confidenceLevel}`}
          style={{ width: `${Math.min(Math.max(confidencePercent, 0), 100)}%` }}
        />
      </div>

      <p className="route-reason">理由：{reason || '当前没有提供额外路由说明。'}</p>
    </section>
  );
}
