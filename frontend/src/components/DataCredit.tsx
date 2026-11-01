const LINK_CLASS = 'underline underline-offset-2 hover:text-asphalt'

function CreditLink({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={LINK_CLASS}>
      {children}
    </a>
  )
}

/** Open-Meteo's CC BY 4.0 licence asks for credit, a licence link, and a note of any changes. */
export function DataCredit() {
  return (
    <p className="text-xs text-asphalt/70">
      <CreditLink href="https://open-meteo.com/">
        Weather data by Open-Meteo.com
      </CreditLink>{' '}
      (
      <CreditLink href="https://creativecommons.org/licenses/by/4.0/">
        CC BY 4.0
      </CreditLink>
      ), used to calculate risk levels. Routes and place search by{' '}
      <CreditLink href="https://www.tomtom.com/">TomTom</CreditLink>.
    </p>
  )
}
