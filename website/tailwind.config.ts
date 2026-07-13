import type { Config } from 'tailwindcss';

/**
 * RedForge website palette — black + blood red. Pure-black bases, cold steel
 * greys, crisp white, and a single deep "forge red" (blood red, not saffron)
 * used with restraint — glow like hot steel, never LEDs. Intentionally NOT the
 * app's dashboard theme; editorial, cinematic, intimidating.
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
        // Blood red — deep and restrained. DEFAULT is the accent; `bright` is the
        // hottest allowed tone (hover/active); `deep`/`ember` are shadow reds for
        // gradients and glows. No saffron/orange anywhere.
        forge: {
          DEFAULT: '#A11212',
          bright: '#D12A2A',
          deep: '#5A0000',
          ember: '#7A0000',
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
