/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy:  { DEFAULT: '#0B1120', 50: '#1A2235', 100: '#243044', 200: '#2D3B52' },
        brand: { 50:'#E3F2FD', 100:'#BBDEFB', 500:'#3B82F6', 600:'#2563EB', 700:'#1D4ED8', 900:'#0B1120' },
        surface: { 0:'#0B1120', 1:'#111827', 2:'#1A2235', 3:'#243044', 4:'#2D3B52' },
      },
      fontFamily: {
        display: ['Satoshi', 'Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
        '3xl': '20px',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s cubic-bezier(0.4,0,0.2,1) forwards',
        'slide-up': 'slideUp 0.5s cubic-bezier(0.16,1,0.3,1) forwards',
        'shimmer': 'shimmer 1.5s infinite',
      },
    }
  },
  plugins: []
}
