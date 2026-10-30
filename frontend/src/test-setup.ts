import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Allow for the search pause and a busy machine before a query gives up.
configure({ asyncUtilTimeout: 10_000 })

afterEach(() => {
  cleanup()
})
