import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0A0E1A',
        surface: '#1E2433',
        border: '#374151',
        muted: '#9CA3AF',
        accent: {
          red: '#EF4444',
          blue: '#3B82F6',
          amber: '#F59E0B',
          green: '#10B981',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
