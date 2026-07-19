import { NavLink, useLocation } from 'react-router-dom';
import type { UserInfo } from '../../types/auth';
import { APP_TITLE } from '../../utils/constants';

interface AppHeaderProps {
  accessToken: string;
  user: UserInfo | null;
  isLoggingOut?: boolean;
  onLogout: () => Promise<void>;
}

function IconLogout() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M5 2H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h2M9 10l3-3-3-3M12 7H6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function AppHeader({ accessToken, user, onLogout }: AppHeaderProps) {
  const location = useLocation();
  const redirectTarget = encodeURIComponent(`${location.pathname}${location.search}`);

  const handleLogout = async () => {
    await onLogout();
  };

  return (
    <header className="app-header">
      <div className="header-bar">
        <div className="brand-section">
          <div className="brand-title">{APP_TITLE}</div>
          <div className="brand-subtitle">工业级电力标准知识库</div>
        </div>

        <div className="header-main-actions">
          <nav className="header-nav" aria-label="主导航">
            <NavLink
              to={accessToken ? '/search' : `/login?redirect=${redirectTarget}`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              查询
            </NavLink>
            <NavLink
              to={accessToken ? '/history' : `/login?redirect=${encodeURIComponent('/history')}`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              历史
            </NavLink>
            <NavLink
              to={accessToken ? '/documents/import' : `/login?redirect=${encodeURIComponent('/documents/import')}`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              导入
            </NavLink>
            <NavLink
              to={accessToken ? '/documents/manage' : `/login?redirect=${encodeURIComponent('/documents/manage')}`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              管理
            </NavLink>
          </nav>

          <div className="header-actions">
            {user ? (
              <div className="user-menu">
                <div className="user-avatar">
                  {(user.full_name ?? user.username).charAt(0).toUpperCase()}
                </div>
                <div className="user-info">
                  <div className="user-name">{user.full_name || user.username}</div>
                  <div className="user-role">{user.role}</div>
                </div>
                <button
                  type="button"
                  className="icon-button logout-button"
                  onClick={handleLogout}
                  aria-label="退出登录"
                  title="退出登录"
                >
                  <IconLogout />
                </button>
              </div>
            ) : accessToken ? (
              <div className="header-actions-inline">
                <div className="status-chip is-active">已连接</div>
                <button
                  type="button"
                  className="icon-button logout-button"
                  onClick={handleLogout}
                  aria-label="退出登录"
                  title="退出登录"
                >
                  <IconLogout />
                </button>
              </div>
            ) : (
              <NavLink to="/login" className="login-link">
                登录
              </NavLink>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
