import { useAttribution } from '@/api/queries'

const LINK_CLASS = 'underline underline-offset-2 hover:text-asphalt'

function CreditLink({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={LINK_CLASS}>
      {children}
    </a>
  )
}

/**
 * Open-Meteo's CC BY 4.0 licence asks for credit, a licence link, and a note of any changes.
 * TomTom's terms require its credit to come from its Copyright API, so if that fails, none shows.
 */
export function DataCredit() {
  const caption = useAttribution().data?.routing_caption
  return (
    // Room for two lines, so the form doesn't move when the routing credit arrives.
    <p className="min-h-8 text-xs text-asphalt/70">
      <CreditLink href="https://open-meteo.com/">
        Weather data by Open-Meteo.com
      </CreditLink>{' '}
      (
      <CreditLink href="https://creativecommons.org/licenses/by/4.0/">
        CC BY 4.0
      </CreditLink>
      ), used to calculate risk levels.
      {caption ? ` Routes and place search: ${caption}.` : null}
    </p>
  )
}
