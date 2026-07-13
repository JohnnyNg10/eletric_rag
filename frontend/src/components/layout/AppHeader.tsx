import { useEffect, useState, type FormEvent as ReactFormEvent } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import type { UserInfo } from '../../types/auth';
import { APP_TITLE } from '../../utils/constants';

interface AppHeaderProps {
  apiBaseUrl: string;
  accessToken: string;
  user: UserInfo | null;
  isLoading: boolean;
  isLoggingIn: boolean;
  error: string | null;
  onApiBaseUrlChange: (value: string) => void;
  onLogin: (username: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
  onManualTokenChange: (value: string) => void;
}

export default function AppHeader({
  apiBaseUrl,
  accessToken,
  user,
  isLoading,
  isLoggingIn,
  error,
  onApiBaseUrlChange,
  onLogin,
  onLogout,
  onManualTokenChange,
}: AppHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [expanded, setExpanded] = useState(!accessToken);
  const [baseUrlDraft, setBaseUrlDraft] = useState(apiBaseUrl);
  const [tokenDraft, setTokenDraft] = useState(accessToken);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  useEffect(() => {
    setBaseUrlDraft(apiBaseUrl);
  }, [apiBaseUrl]);

  useEffect(() => {
    setTokenDraft(accessToken);
    if (!accessToken) {
      setExpanded(true);
    }
  }, [accessToken]);

  const handleLoginSubmit = async (event: ReactFormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!username.trim() || !password.trim()) return;
    await onLogin(username.trim(), password);
    setPassword('');
  };

  const handleBaseUrlSave = () => {
    onApiBaseUrlChange(baseUrlDraft);
  };

  const handleTokenSave = () => {
    onManualTokenChange(tokenDraft);
  };

  const handleLogoutClick = async () => {
    setIsLoggingOut(true);
    try {
      await onLogout();
      navigate('/login', { replace: true });
    } finally {
      setIsLoggingOut(false);
    }
  };

  const statusLabel = user
    ? `已登录：${user.full_name || user.username}`
    : accessToken
      ? '已设置 Token'
      : '未登录';

  const redirectTarget = encodeURIComponent(`${location.pathname}${location.search}`);

  return (
    <header className="app-header">
      <div className="header-bar">
        <div>
          <div className="brand-title">{APP_TITLE}</div>
          <div className="brand-subtitle">阶段 B“后确认”查询与真实后端联调版本</div>
        </div>

        <div className="header-main-actions">
          <nav className="header-nav" aria-label="主导航">
            <NavLink to="/login" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              连接与登录
            </NavLink>
            <NavLink
              to={accessToken ? '/search' : `/login?redirect=${redirectTarget}`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              查询台
            </NavLink>
            <NavLink
              to={accessToken ? '/history' : `/login?redirect=${encodeURIComponent('/history')}`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              查询历史
            </NavLink>
          </nav>

          <div className="header-actions">
            <div className={`status-chip ${user || accessToken ? 'is-active' : ''}`}>{statusLabel}</div>
            <button
              type="button"
              className="toolbar-button"
              onClick={() => setExpanded((previous) => !previous)}
            >
              {expanded ? '收起连接设置' : '打开连接设置'}
            </button>
          </div>
        </div>
      </div>

      {expanded ? (
        <div className="header-panel">
          <div className="header-grid">
            <section className="config-section">
              <h2 className="section-title">连接配置</h2>
              <label className="field-label" htmlFor="api-base-url">
                API Base URL
              </label>
              <input
                id="api-base-url"
                className="text-input"
                value={baseUrlDraft}
                onChange={(event) => setBaseUrlDraft(event.target.value)}
                placeholder="http://localhost:8000/api/v1"
              />
              <div className="panel-actions">
                <button type="button" className="secondary-button" onClick={handleBaseUrlSave}>
                  保存地址
                </button>
              </div>
              <p className="panel-note">默认对接本地 `FastAPI` 的 `/api/v1` 前缀。</p>
            </section>

            <section className="config-section">
              <h2 className="section-title">账户登录</h2>
              <form className="stack-form" onSubmit={handleLoginSubmit}>
                <label className="field-label" htmlFor="login-username">
                  用户名
                </label>
                <input
                  id="login-username"
                  className="text-input"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="请输入用户名"
                />
                <label className="field-label" htmlFor="login-password">
                  密码
                </label>
                <input
                  id="login-password"
                  className="text-input"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="请输入密码"
                />
                <div className="panel-actions">
                  <button type="submit" className="primary-button" disabled={isLoggingIn || isLoggingOut}>
                    {isLoggingIn ? '登录中...' : '登录并保存 Token'}
                  </button>
                  {user || accessToken ? (
                    <button type="button" className="ghost-button" onClick={handleLogoutClick} disabled={isLoggingOut}>
                      {isLoggingOut ? '退出中...' : '退出登录'}
                    </button>
                  ) : null}
                </div>
              </form>
              {user ? (
                <div className="info-card compact">
                  <div>角色：{user.role}</div>
                  <div>邮箱：{user.email}</div>
                  {typeof user.query_count === 'number' ? <div>累计查询：{user.query_count}</div> : null}
                </div>
              ) : null}
            </section>

            <section className="config-section">
              <h2 className="section-title">手动 Token</h2>
              <label className="field-label" htmlFor="manual-token">
                Access Token
              </label>
              <textarea
                id="manual-token"
                className="text-area small"
                value={tokenDraft}
                onChange={(event) => setTokenDraft(event.target.value)}
                placeholder="如后端已提供 Bearer Token，可直接粘贴到这里"
              />
              <div className="panel-actions">
                <button type="button" className="secondary-button" onClick={handleTokenSave}>
                  保存 Token
                </button>
              </div>
              <p className="panel-note">保存后会自动请求 `/auth/me` 校验当前登录态。</p>
            </section>
          </div>

          {isLoading ? <div className="info-banner">正在验证登录状态...</div> : null}
          {error ? <div className="error-banner">{error}</div> : null}
        </div>
      ) : null}
    </header>
  );
}

