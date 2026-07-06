import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { QueryProvider } from './lib/query';
import { ToasterProvider } from './lib/toast';
import './index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <QueryProvider>
      <ToasterProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ToasterProvider>
    </QueryProvider>
  </React.StrictMode>
);
