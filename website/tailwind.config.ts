import type { Config } from 'tailwindcss';

/**
 * RedForge website palette — forged steel. Near-black bases, cold steel greys,
 * crisp white, and a single expensive "forge red" used with restraint. This is
 * intentionally NOT the app's dashboard theme; it is editorial and cinematic.
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#050506', // true black base
        char: '#0B0B0D', // charcoal
        steel: {
          900: '#111114',
          800: '#17171B',
          700: '#1F1F24',
          600: '#2A2A31',
          500: '#3A3A42',
          400: '#55555F',
          300: '#7A7A85',
          200: '#A6A6AF',
        },
        bone: '#EDECE8', // warm off-white
        forge: {
          DEFAULT: '#E5484D',
          bright: '#FF5A57',
          deep: '#B0242A',
          ember: '#FF7A45',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      letterSpacing: {
        tightest: '-0.045em',
        tighter: '-0.03em',
      },
      maxWidth: {
        editorial: '1320px',
      },
      transitionTimingFunction: {
        forge: 'cubic-bezier(0.16, 1, 0.3, 1)', // expo-out, confident
      },
      keyframes: {
        'ember-flicker': {
          '0%, 100%': { opacity: '0.85', transform: 'scale(1)' },
          '50%': { opacity: '1', transform: 'scale(1.06)' },
        },
        'draw-line': {
          from: { strokeDashoffset: '1' },
          to: { strokeDashoffset: '0' },
        },
        'scan': {
          '0%': { transform: 'translateY(-100%)', opacity: '0' },
          '50%': { opacity: '0.4' },
          '100%': { transform: 'translateY(100%)', opacity: '0' },
        },
      },
      animation: {
        'ember-flicker': 'ember-flicker 3.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};

export default config;
