import React, { Suspense, useEffect } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { Spinner } from './components/ui';

const Dashboard = React.lazy(() => import('./pages/DashboardPage'));
const Setup = React.lazy(() => import('./pages/SetupPage'));
const NewEvaluation = React.lazy(() => import('./pages/NewEvaluationPage'));
const LiveList = React.lazy(() => import('./pages/LiveListPage'));
const LiveSession = React.lazy(() => import('./pages/LiveSessionPage'));
const Reports = React.lazy(() => import('./pages/ReportsPage'));
const ReportDetail = React.lazy(() => import('./pages/ReportDetailPage'));
const Leaderboard = React.lazy(() => import('./pages/LeaderboardPage'));
const History = React.lazy(() => import('./pages/HistoryPage'));

// Browser tab title per route (branding pass — no routing change).
function titleFor(pathname: string): string {
  if (pathname.startsWith('/new')) return 'RedForge • New Evaluation';
  if (pathname.startsWith('/live')) return 'RedForge • Live Evaluation';
  if (pathname.startsWith('/reports')) return 'RedForge • Reports';
  if (pathname.startsWith('/history')) return 'RedForge • History';
  if (pathname.startsWith('/leaderboard')) return 'RedForge • Leaderboard';
  if (pathname.startsWith('/setup')) return 'RedForge • Setup';
  return 'RedForge';
}

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();

  // Keep the browser tab title in sync with the current page.
  useEffect(() => {
    document.title = titleFor(location.pathname);
  }, [location.pathname]);

  // First launch → send the user through the setup wizard once.
  useEffect(() => {
    if (localStorage.getItem('redforge_launched') !== '1' && location.pathname === '/') {
      navigate('/setup', { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AppShell>
      <Suspense fallback={<Spinner label="Loading page…" />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="/new" element={<NewEvaluation />} />
          <Route path="/live" element={<LiveList />} />
          <Route path="/live/:id" element={<LiveSession />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/reports/:id" element={<ReportDetail />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
