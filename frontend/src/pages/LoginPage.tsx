import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthContext } from '../context/AuthContext';

export function LoginPage() {
  const auth = useAuthContext();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectTo = searchParams.get('redirect') || '/search';

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  if (auth.accessToken) {
    navigate(redirectTo, { replace: true });
    return null;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!username.trim() || !password.trim()) return;
    try {
      await auth.login(username.trim(), password);
      navigate(redirectTo, { replace: true });
    } catch {
      // error shown via auth.error
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <rect width="32" height="32" rx="8" fill="#007aff" />
              <path d="M8 22l6-12 4 8 2-4 4 8" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="login-title">电力标准知识库</h1>
          <p className="login-subtitle">请登录以继续</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label className="field-label" htmlFor="username">用户名</label>
            <input
              id="username"
              className="text-input"
              type="text"
              value={username}
              autoComplete="username"
              autoFocus
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
            />
          </div>

          <div className="login-field">
            <label className="field-label" htmlFor="password">密码</label>
            <input
              id="password"
              className="text-input"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
            />
          </div>

          {auth.error ? (
            <div className="error-banner" role="alert">{auth.error}</div>
          ) : null}

          <button
            type="submit"
            className="primary-button login-submit"
            disabled={auth.isLoggingIn || !username.trim() || !password.trim()}
          >
            {auth.isLoggingIn ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
}
