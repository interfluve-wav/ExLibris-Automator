const withMT = require("@material-tailwind/html/utils/withMT");

/** @type {import('tailwindcss').Config} */
module.exports = withMT({
  content: ["./templates/**/*.html"],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: 'var(--surface)',
          soft: 'var(--surface-soft)',
          soft2: 'var(--surface-soft-2)',
        },
        txt: {
          DEFAULT: 'var(--text)',
          muted: 'var(--text-muted)',
        },
        bdr: 'var(--border)',
        primary: {
          DEFAULT: 'var(--primary)',
          2: 'var(--primary-2)',
        },
        success: 'var(--success)',
        warn: 'var(--warn)',
        danger: 'var(--danger)',
        idle: 'var(--idle)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', "'Segoe UI'", 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', '"Liberation Mono"', '"Courier New"', 'monospace'],
      },
      boxShadow: {
        lg: 'var(--shadow-lg)',
        md: 'var(--shadow-md)',
      },
      keyframes: {
        gradientShift: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
        pulse: {
          '0%, 100%': { boxShadow: '0 0 0 4px color-mix(in srgb, currentColor 14%, transparent)' },
          '50%': { boxShadow: '0 0 0 8px color-mix(in srgb, currentColor 8%, transparent)' },
        },
        waitingPulse: {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 0 0 rgba(53, 184, 91, 0.4)' },
          '50%': { opacity: '0.85', boxShadow: '0 0 0 10px rgba(53, 184, 91, 0)' },
        },
        fadeSlideIn: {
          from: { opacity: '0', transform: 'translateY(-6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        fadeSlideOut: {
          from: { opacity: '1', transform: 'translateY(0)' },
          to: { opacity: '0', transform: 'translateY(-6px)' },
        },
      },
      animation: {
        'gradient-shift': 'gradientShift 8s ease infinite',
        'status-pulse': 'pulse 1.8s ease-in-out infinite',
        'waiting-pulse': 'waitingPulse 2s ease-in-out infinite',
        'fade-in': 'fadeSlideIn 0.3s ease forwards',
        'fade-out': 'fadeSlideOut 0.25s ease forwards',
      },
    },
  },
  plugins: [],
});
