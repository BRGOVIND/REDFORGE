import React, { Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { Spinner } from './components/ui';

const Dashboard = React.lazy(() => import('./pages/DashboardPage'));
const NewEvaluation = React.lazy(() => import('./pages/NewEvaluationPage'));
const LiveList = React.lazy(() => import('./pages/LiveListPage'));
const LiveSession = React.lazy(() => import('./pages/LiveSessionPage'));
const Reports = React.lazy(() => import('./pages/ReportsPage'));
const ReportDetail = React.lazy(() => import('./pages/ReportDetailPage'));
const Leaderboard = React.lazy(() => import('./pages/LeaderboardPage'));
const History = React.lazy(() => import('./pages/HistoryPage'));

export default function App() {
  return (
    <AppShell>
      <Suspense fallback={<Spinner label="Loading page…" />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
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
