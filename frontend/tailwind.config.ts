import type { Config } from 'tailwindcss'

/**
 * RedForge design system — dark-first, neutral grey surfaces with a single
 * red accent. Tuned to feel at home next to Linear / Vercel / Grafana:
 * restrained, high-contrast, no flashy color.
 */
const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Greys (near-black base -> elevated surfaces)
        base: '#0B0B0D',
        surface: '#141417',
        elevated: '#1A1A1E',
        overlay: '#202026',
        border: {
          DEFAULT: '#26262B',
          strong: '#33333A',
        },
        content: {
          DEFAULT: '#E8E8EC',
          muted: '#A1A1AA',
          subtle: '#71717A',
          faint: '#52525B',
        },
        // Red accent scale
        red: {
          50: '#FEF2F2',
          400: '#F26D70',
          500: '#E5484D',
          600: '#D22F35',
          700: '#B0242A',
          soft: 'rgba(229, 72, 77, 0.12)',
          ring: 'rgba(229, 72, 77, 0.35)',
        },
        // Semantic (verdicts / status)
        pass: '#3FB950',
        fail: '#E5484D',
        uncertain: '#D29922',
        info: '#8B8B93',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        lg: '10px',
        xl: '14px',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(-6px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'slide-in': 'slide-in 0.2s ease-out',
        'pulse-dot': 'pulse-dot 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}

export default config
