import { useNavigate } from 'react-router-dom';

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <section className="page-panel not-found-panel">
      <div className="panel-header-row">
        <div>
          <div className="panel-eyebrow">404</div>
          <h1 className="panel-title">页面不存在</h1>
        </div>
        <span className="meta-pill">请检查当前地址</span>
      </div>

      <p className="page-description">
        你访问的前端路由不存在。可以返回登录页重新配置联调，或回到查询页继续使用阶段 B 查询台。
      </p>

      <div className="panel-actions">
        <button type="button" className="primary-button" onClick={() => navigate('/search')}>
          去查询台
        </button>
        <button type="button" className="secondary-button" onClick={() => navigate('/login')}>
          去登录页
        </button>
      </div>
    </section>
  );
}
