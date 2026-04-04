import { useState, useEffect } from 'react'

export function useMobile() {
  const [isMobile,  setIsMobile]  = useState(() => window.innerWidth < 768)
  const [isTablet,  setIsTablet]  = useState(() => window.innerWidth < 1024)
  const [isTouched, setIsTouched] = useState(false)

  useEffect(() => {
    const handler = () => {
      setIsMobile(window.innerWidth < 768)
      setIsTablet(window.innerWidth < 1024)
    }
    const ro = new ResizeObserver(handler)
    ro.observe(document.body)
    window.addEventListener('touchstart', () => setIsTouched(true), { once: true })
    return () => ro.disconnect()
  }, [])

  return { isMobile, isTablet, isTouch: isTouched }
}
