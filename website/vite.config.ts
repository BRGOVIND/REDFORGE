import { readFileSync } from 'fs';
import { resolve } from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Single source of truth for the version: the repo-root VERSION file.
function readVersion(): string {
  try {
    return readFileSync(resolve(__dirname, '..', 'VERSION'), 'utf-8').trim();
  } catch {
    return '0.0.0';
  }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(readVersion()),
  },
  server: {
    port: 5174,
  },
});
