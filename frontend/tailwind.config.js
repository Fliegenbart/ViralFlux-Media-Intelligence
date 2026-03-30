/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class', '[data-theme="dark"]'],
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        headline: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      colors: {
        background: 'var(--bg-primary)',
        primary: {
          DEFAULT: 'var(--color-primary)',
          dim: 'var(--color-primary-hover)',
          fixed: 'var(--accent-blue)',
          container: 'var(--accent-blue)',
        },
        surface: {
          DEFAULT: 'var(--bg-primary)',
          low: 'var(--bg-secondary)',
          container: 'var(--bg-secondary)',
          high: 'var(--bg-card)',
          highest: 'var(--bg-card-hover)',
          card: 'var(--bg-card)',
        },
        ink: {
          DEFAULT: 'var(--text-primary)',
          soft: 'var(--text-secondary)',
          mute: 'var(--text-muted)',
        },
        secondary: {
          DEFAULT: 'var(--accent-pink)',
          container: 'var(--bg-secondary)',
        },
        tertiary: {
          DEFAULT: 'var(--accent-pink)',
          container: 'var(--bg-secondary)',
        },
        outline: {
          DEFAULT: 'var(--border-color)',
          soft: 'var(--border-light)',
        },
      },
      boxShadow: {
        'xs': '0 1px 2px rgba(0, 0, 0, 0.04)',
        'soft': '0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
        'medium': '0 4px 12px rgba(0, 0, 0, 0.06)',
        'strong': '0 8px 24px rgba(0, 0, 0, 0.08)',
        'brand': '0 1px 3px rgba(99, 102, 241, 0.2)',
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
        'xl': '20px',
        '2xl': '24px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      transitionTimingFunction: {
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
}
