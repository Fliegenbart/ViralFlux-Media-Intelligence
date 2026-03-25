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
        headline: ['Manrope', 'Inter', 'system-ui', 'sans-serif'],
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
        'soft': '0 12px 30px rgba(5, 52, 92, 0.05)',
        'medium': '0 20px 40px rgba(5, 52, 92, 0.06)',
        'strong': '0 28px 64px rgba(5, 52, 92, 0.08)',
        'brand': '0 18px 36px rgba(81, 72, 216, 0.18)',
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
        'xl': '24px',
        '2xl': '32px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 6s ease-in-out infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
      },
    },
  },
  plugins: [],
}
