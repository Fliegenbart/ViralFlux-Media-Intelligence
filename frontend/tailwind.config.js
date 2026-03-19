/** @type {import('tailwindcss').Config} */
module.exports = {
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
        background: '#f8f9ff',
        primary: {
          DEFAULT: '#5148d8',
          dim: '#453acc',
          fixed: '#6f68f7',
          container: '#6f68f7',
        },
        surface: {
          DEFAULT: '#f8f9ff',
          low: '#eff4ff',
          container: '#e5eeff',
          high: '#dce9ff',
          highest: '#d2e4ff',
          card: '#ffffff',
        },
        ink: {
          DEFAULT: '#05345c',
          soft: '#3d618c',
          mute: '#5a7da9',
        },
        secondary: {
          DEFAULT: '#5e5d72',
          container: '#e3e0f9',
        },
        tertiary: {
          DEFAULT: '#765377',
          container: '#fed2fd',
        },
        outline: {
          DEFAULT: '#5a7da9',
          soft: '#91b4e4',
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
