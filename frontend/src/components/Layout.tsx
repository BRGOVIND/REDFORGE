import React from 'react';
import Navbar from './Navbar';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
        width: '100%',
      }}
    >
      <aside
        style={{
          width: '240px',
          minWidth: '240px',
          background: '#1E2433',
          borderRight: '1px solid #374151',
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          position: 'sticky',
          top: 0,
          overflowY: 'auto',
        }}
      >
        <Navbar />
      </aside>
      <main
        style={{
          flex: 1,
          background: '#0A0E1A',
          padding: '24px',
          minHeight: '100vh',
          overflowY: 'auto',
        }}
      >
        {children}
      </main>
    </div>
  );
};

export default Layout;
