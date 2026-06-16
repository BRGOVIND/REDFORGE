import React, { Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';

const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Models = React.lazy(() => import('./pages/Models'));
const Attacks = React.lazy(() => import('./pages/Attacks'));
const RunTests = React.lazy(() => import('./pages/RunTests'));
const Hallucination = React.lazy(() => import('./pages/Hallucination'));
const Reports = React.lazy(() => import('./pages/Reports'));

const Fallback = () => (
  <div className="flex items-center justify-center h-full w-full text-gray-400 text-sm">
    Loading...
  </div>
);

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<Fallback />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/models" element={<Models />} />
          <Route path="/attacks" element={<Attacks />} />
          <Route path="/run" element={<RunTests />} />
          <Route path="/hallucination" element={<Hallucination />} />
          <Route path="/reports" element={<Reports />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
