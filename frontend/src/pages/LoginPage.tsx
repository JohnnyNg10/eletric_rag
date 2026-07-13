import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthContext } from '../context/AuthContext';

export function LoginPage() {
  const auth = useAuthContext();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectTo = searchParams.get('redirect') || '/search';

  useEffect(() => {
    if (auth.accessToken) {
      navigate(redirectTo, { replace: true });
    }
  }, [auth.accessToken, navigate, redirectTo]);

  return (
    <section className="page-panel login-panel">
      <div className="panel-header-row">
        <div>
          <div className="panel-eyebrow">连接与登录</div>
          <h1 className="panel-title">先完成后端联调配置，再进入阶段 B 查询台</h1>
        </div>
        {auth.accessToken ? <span className="meta-pill">登录态可用</span> : <span className="meta-pill">等待登录</span>}
      </div>

      <p className="page-description">
        右上角已经接入真实后端的连接配置、账号登录和手动 Token 校验。登录成功后会自动跳转到查询页；如需查看查询记录，可直接进入历史页。
      </p>

      <div className="feature-grid compact-grid">
        <div className="feature-card">
          <h3>真实认证流程</h3>
          <p>对接 `POST /api/v1/auth/login`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`，支持用户名密码登录与手动 Token 校验。</p>
        </div>
        <div className="feature-card">
          <h3>多页面跳转</h3>
          <p>已补齐 `连接与登录`、`阶段 B 查询台`、`查询历史` 三个页面，未登录时会自动拦截并跳转。</p>
        </div>
        <div className="feature-card">
          <h3>实际联调入口</h3>
          <p>API Base URL 可直接改为你的真实后端地址，保存后即对当前页面和后续查询生效。</p>
        </div>
      </div>

      <div className="info-card">
        <div><strong>当前 API：</strong>{auth.apiBaseUrl}</div>
        <div><strong>当前状态：</strong>{auth.user ? `已登录：${auth.user.full_name || auth.user.username}` : auth.accessToken ? '已设置 Token，正在校验或可直接使用' : '未登录'}</div>
        <div><strong>推荐操作：</strong>展开顶部“连接设置”，填入账号或 Token，随后进入查询页面。</div>
      </div>

      <div className="panel-actions">
        <button type="button" className="primary-button" onClick={() => navigate(redirectTo)} disabled={!auth.accessToken}>
          进入查询台
        </button>
        <button type="button" className="secondary-button" onClick={() => navigate('/history')} disabled={!auth.accessToken}>
          查看查询历史
        </button>
      </div>
    </section>
  );
}
