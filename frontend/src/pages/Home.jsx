import { BookOpen, Dna, GitBranch, Info, Microscope, Network, Stethoscope } from 'lucide-react'
import { Link } from 'react-router-dom'
import RankedBarChart from '../components/RankedBarChart'
import SearchBox from '../components/SearchBox'
import { EmptyState, ErrorState, EvidenceBadge, Loading, Section, StatCard, ValidationBadge } from '../components/common'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { ASSOCIATION_TYPES, RNA_TYPE_COLORS, formatDate, label } from '../utils/labels'

export function DataNotice() {
  return (
    <aside className="notice" aria-label="Evidence and data-source limitations">
      <Info size={18} aria-hidden />
      <div>
        <strong>How to read this atlas.</strong> Associations are imported from curated public databases (HMDD,
        LncRNADisease) and from a small hand-curated set. The <em>evidence level</em> reflects what the source record
        reports; it is not an independent validation. Only associations marked <em>Curator confirmed</em> have passed
        the ncRNAAtlas literature review. KEGG pathways are inferred through genes and do not by themselves establish
        an ncRNA–disease link. See <Link to="/methodology">Methodology</Link> for details and limitations.
      </div>
    </aside>
  )
}

function Onboarding() {
  return (
    <Section title="The database is empty">
      <EmptyState title="No data has been imported yet" icon={Dna}>
        <p>Initialize the database and load data from the project root:</p>
        <pre className="code">
          {`python scripts/initialize_database.py --sample   # offline demo excerpt of real records
python scripts/download_sources.py                 # real data mode: fetch HMDD, LncRNADisease, HGNC
python scripts/import_data.py real
python scripts/map_pathways.py`}
        </pre>
        <p>
          Administrators can also upload CSV/TSV files on the <Link to="/admin">data import page</Link>.
        </p>
      </EmptyState>
    </Section>
  )
}

export default function Home() {
  const { data: s, error, loading, reload } = useApi(() => api.statistics(), [])

  return (
    <>
      <div className="hero">
        <h1>
          ncRNA<span>Atlas</span>
        </h1>
        <p className="lead">
          An integrated atlas of non-coding RNA–disease associations — connecting microRNAs and long non-coding RNAs
          with human diseases, genes, KEGG pathways and the PubMed literature that supports each claim.
        </p>
        <SearchBox autoFocus />
        <p className="hero-examples small">
          Try: <Link to="/search?q=hsa-mir-21">hsa-mir-21</Link> · <Link to="/search?q=MALAT1">MALAT1</Link> ·{' '}
          <Link to="/search?q=hepatocellular">hepatocellular</Link> · <Link to="/search?q=PTEN">PTEN</Link> ·{' '}
          <Link to="/search?q=17681183">17681183</Link>
        </p>
      </div>

      <DataNotice />

      {loading && <Loading text="Loading statistics…" />}
      <ErrorState error={error} onRetry={reload} what="statistics" />

      {s && s.is_empty && <Onboarding />}

      {s && !s.is_empty && (
        <>
          {s.dataset_labels.includes('sample') && (
            <p className="banner-sample">
              <strong>Sample mode:</strong> this database contains a small excerpt of real source records for
              demonstration. Counts describe the excerpt, not the full resources.
            </p>
          )}
          <div className="stats-grid">
            <StatCard icon={Dna} label="ncRNAs" value={s.totals.ncrnas}
              hint={`${s.ncrna_type_distribution.miRNA || 0} miRNA · ${s.ncrna_type_distribution.lncRNA || 0} lncRNA`} />
            <StatCard icon={Stethoscope} label="Disease associations" value={s.totals.associations}
              hint={`${s.totals.human_associations.toLocaleString()} human · ${s.totals.diseases.toLocaleString()} diseases`} />
            <StatCard icon={Microscope} label="Genes" value={s.totals.genes}
              hint={`${s.totals.ncrna_gene_interactions.toLocaleString()} ncRNA–gene relationships`} />
            <StatCard icon={BookOpen} label="Publications" value={s.totals.publications}
              hint={`${s.totals.publications_with_metadata.toLocaleString()} with PubMed metadata`} />
            <StatCard icon={GitBranch} label="Mapped KEGG pathways" value={s.totals.mapped_pathways}
              hint={`${s.totals.genes_with_pathway_mapping} genes mapped`} />
          </div>

          <div className="grid-2">
            <Section title="Most frequently associated diseases" subtitle="Human associations per disease">
              {s.top_diseases.length ? (
                <RankedBarChart rows={s.top_diseases} nameKey="canonical_name" valueKey="association_count"
                  valueLabel="Associations" linkPrefix="/diseases" />
              ) : <EmptyState title="No human associations" />}
            </Section>
            <Section title="Most represented ncRNAs" subtitle="Human associations per ncRNA">
              {s.top_ncrnas.length ? (
                <RankedBarChart rows={s.top_ncrnas} nameKey="canonical_name" valueKey="association_count"
                  valueLabel="Associations" linkPrefix="/ncrnas"
                  colorFor={(r) => RNA_TYPE_COLORS[r.ncrna_type]}
                  legend={Object.entries(RNA_TYPE_COLORS)} />
              ) : <EmptyState title="No human associations" />}
            </Section>
          </div>

          <div className="grid-3">
            <Section title="RNA type distribution" subtitle="Entities and associations">
              <table className="table compact">
                <thead>
                  <tr><th scope="col">Type</th><th scope="col" className="num">ncRNAs</th><th scope="col" className="num">Associations</th></tr>
                </thead>
                <tbody>
                  {['miRNA', 'lncRNA'].map((t) => (
                    <tr key={t}>
                      <td><span className="swatch" style={{ background: RNA_TYPE_COLORS[t] }} aria-hidden /> {t}</td>
                      <td className="num">{(s.ncrna_type_distribution[t] || 0).toLocaleString()}</td>
                      <td className="num">{(s.associations_by_ncrna_type[t] || 0).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted">Organisms: {Object.entries(s.organism_distribution).map(([k, v]) => `${k} (${v})`).join(', ')}</p>
            </Section>
            <Section title="Evidence levels" subtitle="As reported by source records">
              <table className="table compact">
                <tbody>
                  {Object.entries(s.evidence_level_distribution).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <tr key={k}><td><EvidenceBadge level={k} /></td><td className="num">{v.toLocaleString()}</td></tr>
                  ))}
                </tbody>
              </table>
            </Section>
            <Section title="Curator review status" subtitle="ncRNAAtlas literature review">
              <table className="table compact">
                <tbody>
                  {Object.entries(s.validation_status_distribution).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <tr key={k}><td><ValidationBadge status={k} /></td><td className="num">{v.toLocaleString()}</td></tr>
                  ))}
                </tbody>
              </table>
            </Section>
          </div>

          <div className="grid-2">
            <Section title="Association types">
              <table className="table compact">
                <tbody>
                  {Object.entries(s.association_type_distribution).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <tr key={k}><td>{label(ASSOCIATION_TYPES, k)}</td><td className="num">{v.toLocaleString()}</td></tr>
                  ))}
                </tbody>
              </table>
            </Section>
            <Section title="Recent successful imports" actions={<Link to="/sources" className="btn btn-small">All sources</Link>}>
              {s.recent_imports.length ? (
                <div className="table-wrap">
                  <table className="table compact">
                    <thead>
                      <tr><th scope="col">Source</th><th scope="col">Version</th><th scope="col">Completed</th><th scope="col" className="num">Records</th></tr>
                    </thead>
                    <tbody>
                      {s.recent_imports.map((j) => (
                        <tr key={j.id}>
                          <td>{j.source_database} <span className="badge org">{j.dataset_label}</span></td>
                          <td className="small">{j.source_version || '—'}</td>
                          <td className="small">{formatDate(j.completed_at)}</td>
                          <td className="num">{j.records_processed.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState title="No completed imports" />}
            </Section>
          </div>

          <div className="cta-row">
            <Link to="/network" className="btn btn-primary"><Network size={16} aria-hidden /> Open the interaction network</Link>
            <Link to="/associations" className="btn">Browse all associations</Link>
          </div>
        </>
      )}
    </>
  )
}
