import { useEffect, useId, useState, type KeyboardEvent } from 'react'

import type { Location } from '@/api/client'
import { useGeocode } from '@/api/queries'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const SEARCH_PAUSE_MS = 250

function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

interface PlaceInputProps {
  label: string
  value: Location | null
  onChange: (place: Location | null) => void
  error?: string
}

export function PlaceInput({ label, value, onChange, error }: PlaceInputProps) {
  const id = useId()
  const listId = `${id}-suggestions`
  const errorId = `${id}-error`
  const [text, setText] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const query = useDebouncedValue(value ? '' : text, SEARCH_PAUSE_MS)
  const search = useGeocode(query)
  const places = search.data?.results ?? []
  const hasSearched = query.trim().length >= 2 && !search.isFetching
  const showList = isOpen && !value && query.trim().length >= 2

  function choose(place: Location) {
    onChange(place)
    setText(place.label)
    setIsOpen(false)
    setActiveIndex(-1)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setIsOpen(false)
    } else if (event.key === 'ArrowDown' && places.length > 0) {
      event.preventDefault()
      setIsOpen(true)
      setActiveIndex((index) => (index + 1) % places.length)
    } else if (event.key === 'ArrowUp' && places.length > 0) {
      event.preventDefault()
      setActiveIndex((index) => (index <= 0 ? places.length - 1 : index - 1))
    } else if (event.key === 'Enter' && showList && places[activeIndex]) {
      event.preventDefault()
      choose(places[activeIndex])
    }
  }

  return (
    <div className="relative grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={
          activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined
        }
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        autoComplete="off"
        placeholder="City or address"
        className="bg-white"
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          setIsOpen(true)
          setActiveIndex(-1)
          if (value) onChange(null)
        }}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        onKeyDown={onKeyDown}
      />
      {error ? (
        <p id={errorId} className="text-sm font-medium text-risk-severe">
          {error}
        </p>
      ) : null}
      {showList ? (
        <div className="absolute top-full z-20 mt-1 w-full overflow-hidden rounded-md border border-asphalt/20 bg-white shadow-lg">
          <ul id={listId} role="listbox" aria-label={`${label} suggestions`}>
            {places.map((place, index) => (
              <li
                id={`${listId}-${index}`}
                key={`${place.label}-${place.lat}-${place.lon}`}
                role="option"
                aria-selected={index === activeIndex}
                className="cursor-pointer px-3 py-2 text-sm aria-selected:bg-concrete hover:bg-concrete"
                // Keep focus in the input, so choosing doesn't close the list first.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(place)}
              >
                {place.label}
              </li>
            ))}
          </ul>
          {search.isError ? (
            <p className="px-3 py-2 text-sm text-risk-severe">
              Place search is unavailable. Try again shortly.
            </p>
          ) : null}
          {hasSearched && !search.isError && places.length === 0 ? (
            <p className="px-3 py-2 text-sm text-asphalt/70">
              No places found.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
