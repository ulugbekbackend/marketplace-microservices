import { useEffect, useState } from 'react'

const secondsUntil = (deadline: number | null) =>
  deadline === null ? 0 : Math.max(0, Math.ceil((deadline - Date.now()) / 1000))

/** Seconds left until `deadline` (epoch ms), ticking once per second; 0 when passed or null. */
export function useCountdown(deadline: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  const left = deadline === null ? 0 : Math.max(0, Math.ceil((deadline - now) / 1000))

  useEffect(() => {
    if (secondsUntil(deadline) === 0) return
    const timer = window.setInterval(() => {
      setNow(Date.now())
      if (secondsUntil(deadline) === 0) window.clearInterval(timer)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [deadline])

  return left
}

/** 75 -> "01:15" */
export function formatMmSs(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}
