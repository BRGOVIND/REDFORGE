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
const RuntimeManager = React.lazy(() => import('./pages/RuntimeManagerPage'));
const ModelManager = React.lazy(() => import('./pages/ModelManagerPage'));
const Onboarding = React.lazy(() => import('./pages/OnboardingPage'));
const Studio = React.lazy(() => import('./pages/StudioPage'));
const ProjectOverview = React.lazy(() => import('./pages/ProjectOverviewPage'));
const Playground = React.lazy(() => import('./pages/PlaygroundPage'));
const DatasetLab = React.lazy(() => import('./pages/DatasetLabPage'));
const TrainingLab = React.lazy(() => import('./pages/TrainingLabPage'));
const BenchmarkCenter = React.lazy(() => import('./pages/BenchmarkCenterPage'));

/** First-run completion flag. Remove this key to re-run onboarding. */
const ONBOARDED_KEY = 'redforge_onboarded';

// Browser tab title per route (branding pass — no routing change).
function titleFor(pathname: string): string {
  if (pathname.startsWith('/new')) return 'RedForge • New Evaluation';
  if (pathname.startsWith('/live')) return 'RedForge • Live Evaluation';
  if (pathname.startsWith('/reports')) return 'RedForge • Reports';
  if (pathname.startsWith('/history')) return 'RedForge • History';
  if (pathname.startsWith('/leaderboard')) return 'RedForge • Leaderboard';
  if (pathname.startsWith('/runtime')) return 'RedForge • Runtime Manager';
  if (pathname.startsWith('/models')) return 'RedForge • Model Manager';
  if (pathname.startsWith('/studio')) return 'RedForge • AI Studio';
  if (pathname.startsWith('/playground')) return 'RedForge • Playground';
  if (pathname.startsWith('/datasets')) return 'RedForge • Dataset Lab';
  if (pathname.startsWith('/training')) return 'RedForge • Training Lab';
  if (pathname.startsWith('/onboarding')) return 'RedForge • Welcome';
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

  // First launch → send the user through the first-run onboarding once.
  useEffect(() => {
    if (localStorage.getItem(ONBOARDED_KEY) !== '1' && location.pathname === '/') {
      navigate('/onboarding', { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Onboarding is a focused, full-screen experience (outside the app shell).
  if (location.pathname === '/onboarding') {
    return (
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center bg-base">
            <Spinner label="Loading…" />
          </div>
        }
      >
        <Onboarding />
      </Suspense>
    );
  }

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
          <Route path="/runtime" element={<RuntimeManager />} />
          <Route path="/models" element={<ModelManager />} />
          <Route path="/studio" element={<Studio />} />
          <Route path="/projects/:id" element={<ProjectOverview />} />
          <Route path="/playground" element={<Playground />} />
          <Route path="/datasets" element={<DatasetLab />} />
          <Route path="/training" element={<TrainingLab />} />
          <Route path="/benchmarks" element={<BenchmarkCenter />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
