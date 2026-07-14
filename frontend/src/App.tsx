import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import AppHeader from './components/layout/AppHeader';
import { useAuthContext } from './context/AuthContext';
import { HistoryPage } from './pages/HistoryPage';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SearchPage } from './pages/SearchPage';

function AppLayout() {
  const auth = useAuthContext();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await auth.logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="app-shell">
      <AppHeader
        accessToken={auth.accessToken}
        user={auth.user}
        onLogout={handleLogout}
      />

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

function RequireAuth() {
  const auth = useAuthContext();
  const location = useLocation();

  if (auth.isLoading && auth.accessToken && !auth.user) {
    return (
      <section className="page-panel">
        <div className="info-banner">正在校验登录态...</div>
      </section>
    );
  }

  if (!auth.accessToken) {
    const redirect = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?redirect=${encodeURIComponent(redirect)}`} replace />;
  }

  return <Outlet />;
}

function HomeRedirect() {
  const auth = useAuthContext();
  return <Navigate to={auth.accessToken ? '/search' : '/login'} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomeRedirect />} />
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/search" element={<SearchPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

