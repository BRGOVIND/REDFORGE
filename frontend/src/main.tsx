import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { QueryProvider } from './lib/query';
import { ToasterProvider } from './lib/toast';
import { TaskManagerProvider } from './components/TaskManager';
import './index.css';

// Injected at build time from the repo-root VERSION file (vite.config.ts).
// Diagnostic only — surfaces the exact build in the console and bundle.
console.info(`RedForge ${__APP_VERSION__}`);

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryProvider>
        <ToasterProvider>
          <TaskManagerProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </TaskManagerProvider>
        </ToasterProvider>
      </QueryProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
