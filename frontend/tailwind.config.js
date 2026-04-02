/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy:  { DEFAULT: '#1B3A5C', light: '#2E75B6' },
        brand: { 50:'#E3F2FD', 100:'#BBDEFB', 500:'#2E75B6', 700:'#1B3A5C', 900:'#0D2137' },
        crypto:{ green:'#00C853', red:'#FF1744', amber:'#FFD600' }
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'], mono: ['JetBrains Mono', 'monospace'] }
    }
  },
  plugins: []
}
