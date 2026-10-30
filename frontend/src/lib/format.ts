const milesFormat = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 1,
})

export function formatMiles(miles: number): string {
  return `${milesFormat.format(miles)} mi`
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours} h ${minutes} min` : `${minutes} min`
}

export function formatEta(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
    timeZone,
  }).format(new Date(iso))
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** Turn a `datetime-local` value into ISO 8601 with the browser's offset on that date. */
export function localInputToOffsetIso(value: string): string {
  const offsetMinutes = -new Date(value).getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absolute = Math.abs(offsetMinutes)
  const offset = `${sign}${pad(Math.floor(absolute / 60))}:${pad(absolute % 60)}`
  return `${value}:00${offset}`
}

export function nextHourLocalInput(now: Date): string {
  const next = new Date(now)
  next.setHours(now.getHours() + 1, 0, 0, 0)
  const date = `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`
  return `${date}T${pad(next.getHours())}:00`
}
