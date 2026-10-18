/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: '#090d16',
          900: '#0f1523',
          850: '#151d30',
          800: '#1c263e',
          700: '#2b3a5c',
          600: '#3d507a',
        },
        neon: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          DEFAULT: '#00dc82',
          hover: '#05c774',
          glow: 'rgba(0, 220, 130, 0.28)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'glow-neon': '0 0 24px -2px rgba(0, 220, 130, 0.35)',
        'glow-neon-sm': '0 0 12px -1px rgba(0, 220, 130, 0.4)',
        'glow-rose': '0 0 24px -2px rgba(244, 63, 94, 0.3)',
        'glow-rose-sm': '0 0 12px -1px rgba(244, 63, 94, 0.4)',
        surface: '0 4px 24px -2px rgba(0, 0, 0, 0.45)',
      }
    },
  },
  plugins: [],
}
