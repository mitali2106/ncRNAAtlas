import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssociationTable from '../components/AssociationTable'
import SearchBox from '../components/SearchBox'
import { ErrorState } from '../components/common'
import Home from '../pages/Home'
import { NcRNADetail } from '../pages/NcRNAPages'
import NetworkPage from '../pages/NetworkPage'
import { ApiError, api, buildQuery } from '../services/api'
import { association, page, statistics } from './fixtures'

vi.mock('../services/api', async (orig) => {
  const actual = await orig()
  const fn = () => vi.fn()
  return {
    ...actual,
    api: {
      statistics: fn(), suggest: fn(), network: fn(), ncrna: fn(), ncrnaPathways: fn(), ncrnaPublications: fn(),
      ncrnaAssociations: fn(), ncrnaGenes: fn(),
    },
  }
})

// Cytoscape needs a real canvas; the stub exposes what the page passes in.
vi.mock('../components/NetworkGraph', async () => {
  const { forwardRef } = await import('react')
  return {
    default: forwardRef(function Stub({ elements }, _ref) {
      return <div data-testid="network-stub">{elements.length} elements</div>
    }),
  }
})

const renderAt = (ui, path = '/') => render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('api helpers', () => {
  it('builds query strings without empty values', () => {
    expect(buildQuery({ q: 'mir 21', empty: '', none: null, list: ['a', 'b'], page: 2 })).toBe('?q=mir+21&list=a%2Cb&page=2')
  })
  it('classifies errors', () => {
    expect(new ApiError('x').isNetwork).toBe(true)
    expect(new ApiError('x', { status: 503, code: 'external_unavailable' }).isExternal).toBe(true)
    expect(new ApiError('x', { status: 404, code: 'not_found' }).isNotFound).toBe(true)
  })
})

describe('ErrorState', () => {
  it('distinguishes unreachable backend, external outage and missing record', () => {
    const { rerender } = render(<ErrorState error={new ApiError('down')} />)
    expect(screen.getByText(/API is unreachable/)).toBeInTheDocument()
    rerender(<ErrorState error={new ApiError('KEGG is down', { status: 503, code: 'external_unavailable' })} />)
    expect(screen.getByText(/external resource is unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/stored in ncRNAAtlas is unaffected/)).toBeInTheDocument()
    rerender(<ErrorState error={new ApiError('nope', { status: 404, code: 'not_found' })} />)
    expect(screen.getByText('Record not found')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })
})

describe('SearchBox', () => {
  it('shows debounced suggestions from the API', async () => {
    api.suggest.mockResolvedValue({ data: [{ type: 'ncrna', id: 1, label: 'hsa-mir-21', detail: 'miRNA · Homo sapiens' }] })
    renderAt(<SearchBox />)
    await userEvent.type(screen.getByRole('combobox'), 'mir-2')
    expect(await screen.findByText('hsa-mir-21')).toBeInTheDocument()
    expect(api.suggest).toHaveBeenCalledTimes(1)
    expect(api.suggest.mock.calls[0][0]).toBe('mir-2')
  })
  it('reports when nothing matches instead of inventing results', async () => {
    api.suggest.mockResolvedValue({ data: [] })
    renderAt(<SearchBox />)
    await userEvent.type(screen.getByRole('combobox'), 'zzzz')
    expect(await screen.findByText(/No matching records/)).toBeInTheDocument()
  })
  it('does not query for a single character', async () => {
    renderAt(<SearchBox />)
    await userEvent.type(screen.getByRole('combobox'), 'm')
    await new Promise((r) => setTimeout(r, 350))
    expect(api.suggest).not.toHaveBeenCalled()
  })
})

describe('AssociationTable', () => {
  it('renders rows and passes filters to the fetcher', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([association]))
    renderAt(<AssociationTable fetcher={fetcher} />)
    expect(await screen.findByText('hsa-mir-21')).toBeInTheDocument()
    expect(screen.getByText('Carcinoma, Hepatocellular')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /hsa-mir-21/ })).toHaveTextContent('Experimental (source-reported)')
    await userEvent.selectOptions(screen.getByLabelText('Evidence level'), 'conflicting')
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.objectContaining({ evidence_level: 'conflicting', page: 1 })))
    await userEvent.selectOptions(screen.getByLabelText('RNA type'), 'lncRNA')
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.objectContaining({ ncrna_type: 'lncRNA', evidence_level: 'conflicting' })))
    await userEvent.click(screen.getByRole('button', { name: /clear filters/i }))
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.objectContaining({ ncrna_type: '', evidence_level: '' })))
  })
  it('distinguishes "no matches for filters" from "no associations"', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([]))
    renderAt(<AssociationTable fetcher={fetcher} emptyText="Exists, but no associations." />)
    expect(await screen.findByText('No recorded associations')).toBeInTheDocument()
    expect(screen.getByText('Exists, but no associations.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Source database'), 'HMDD')
    expect(await screen.findByText('No associations match these filters')).toBeInTheDocument()
  })
  it('shows a retryable error state on failure', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new ApiError('down')).mockResolvedValue(page([association]))
    renderAt(<AssociationTable fetcher={fetcher} />)
    await userEvent.click(await screen.findByRole('button', { name: /try again/i }))
    expect(await screen.findByText('hsa-mir-21')).toBeInTheDocument()
  })
})

describe('Home dashboard', () => {
  it('shows statistics from the backend', async () => {
    api.statistics.mockResolvedValue(statistics())
    renderAt(<Home />)
    expect(await screen.findByText('Disease associations')).toBeInTheDocument()
    const tile = screen.getByText('Disease associations').closest('.stat')
    expect(tile).toHaveTextContent('120')
    expect(tile).toHaveTextContent('115 human')
    expect(screen.getByText(/Sample mode/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Evidence and data-source limitations/)).toBeInTheDocument()
  })
  it('shows onboarding when the database is empty', async () => {
    api.statistics.mockResolvedValue(statistics({ is_empty: true }))
    renderAt(<Home />)
    expect(await screen.findByText('No data has been imported yet')).toBeInTheDocument()
    expect(screen.getByText(/initialize_database.py --sample/)).toBeInTheDocument()
  })
  it('explains an unreachable backend', async () => {
    api.statistics.mockRejectedValue(new ApiError('Cannot reach the ncRNAAtlas API.'))
    renderAt(<Home />)
    expect(await screen.findByText(/API is unreachable/)).toBeInTheDocument()
  })
})

describe('ncRNA detail page', () => {
  const ncrna = {
    id: 1, canonical_name: 'hsa-mir-21', ncrna_type: 'miRNA', organism: 'Homo sapiens', stable_identifier: 'MI0000077',
    identifier_namespace: 'miRBase', identifier_url: 'https://www.mirbase.org/hairpin/MI0000077', resolution_status: 'resolved',
    sequence: null, description: 'microRNA 21', source_database: 'HMDD',
    aliases: { names: [{ alias: 'MIR21', alias_type: 'synonym', source_database: 'HMDD' }], identifiers: [{ alias: 'HGNC:31586', namespace: 'HGNC', url: 'x' }] },
    counts: { associations: 1, diseases: 1, gene_relationships: 1, publications: 3 },
  }
  const routes = (
    <Routes>
      <Route path="/ncrnas/:id" element={<NcRNADetail />} />
    </Routes>
  )
  it('renders identity, aliases and evidence-linked associations', async () => {
    api.ncrna.mockResolvedValue({ data: ncrna })
    api.ncrnaPathways.mockResolvedValue({ data: { pathways: [], genes_without_mapping: [], gene_count: 0, notes: 'n' } })
    api.ncrnaPublications.mockResolvedValue(page([]))
    api.ncrnaAssociations.mockResolvedValue(page([association]))
    api.ncrnaGenes.mockResolvedValue({ data: { interactions: [], association_gene_links: [] }, pagination: { page: 1, pages: 1, total: 0 } })
    renderAt(routes, '/ncrnas/1')
    expect(await screen.findByRole('heading', { level: 1, name: 'hsa-mir-21' })).toBeInTheDocument()
    expect(screen.getByText('miRBase MI0000077')).toBeInTheDocument()
    expect(screen.getByText('MIR21')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Evidence' })).toHaveAttribute('href', '/associations/7')
    expect(screen.getByText(/No related genes, so no pathways can be inferred/)).toBeInTheDocument()
  })
  it('shows not-found for a missing ncRNA', async () => {
    api.ncrna.mockRejectedValue(new ApiError('ncRNA 99 not found', { status: 404, code: 'not_found' }))
    api.ncrnaPathways.mockResolvedValue({ data: null })
    api.ncrnaPublications.mockResolvedValue(page([]))
    renderAt(routes, '/ncrnas/99')
    expect(await screen.findByText('Record not found')).toBeInTheDocument()
  })
})

describe('Network page', () => {
  const graph = {
    nodes: [
      { id: 'ncrna-1', kind: 'ncrna', entity_id: 1, label: 'hsa-mir-21', ncrna_type: 'miRNA', degree: 2 },
      { id: 'disease-3', kind: 'disease', entity_id: 3, label: 'Carcinoma, Hepatocellular', degree: 1 },
      { id: 'gene-5', kind: 'gene', entity_id: 5, label: 'PTEN', degree: 1 },
    ],
    edges: [
      { id: 'assoc-7', source: 'ncrna-1', target: 'disease-3', kind: 'ncrna_disease', evidence_level: 'experimental', source_databases: ['HMDD'] },
      { id: 'int-1', source: 'ncrna-1', target: 'gene-5', kind: 'ncrna_gene', relationship: 'experimentally_validated_target', source_databases: ['x'], pmids: [] },
    ],
    meta: { associations_matching: 1, associations_shown: 1, truncated: false },
  }
  it('builds the graph from API data and re-queries when filters change', async () => {
    api.network.mockResolvedValue({ data: graph })
    renderAt(<NetworkPage />, '/network')
    expect(await screen.findByTestId('network-stub')).toHaveTextContent('5 elements')
    await userEvent.selectOptions(screen.getByLabelText('ncRNA type'), 'lncRNA')
    await waitFor(() => expect(api.network).toHaveBeenLastCalledWith(expect.objectContaining({ ncrna_type: 'lncRNA' })))
    const relTypes = screen.getByRole('group', { name: /Relationship types/ })
    await userEvent.click(within(relTypes).getByLabelText(/ncRNA–gene relationships/))
    await waitFor(() => expect(api.network).toHaveBeenLastCalledWith(expect.objectContaining({ include: ['ncrna_disease', 'gene_disease'] })))
    await userEvent.click(screen.getByLabelText(/Conflicting evidence/))
    await waitFor(() => expect(api.network).toHaveBeenLastCalledWith(expect.objectContaining({ evidence_level: ['conflicting'] })))
  })
  it('shows an empty state when filters match nothing', async () => {
    api.network.mockResolvedValue({ data: { nodes: [], edges: [], meta: {} } })
    renderAt(<NetworkPage />, '/network')
    expect(await screen.findByText('No relationships match these filters')).toBeInTheDocument()
  })
})
