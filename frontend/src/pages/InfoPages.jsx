import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, ExtLink, Loading, PageHeader, Section } from '../components/common'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { formatDate } from '../utils/labels'

export function DataSources() {
  const { data, error, loading, reload } = useApi(() => api.sources(), [])
  const jobs = useApi(() => api.importJobs({ per_page: 20 }), [])
  return (
    <>
      <PageHeader eyebrow="Provenance" title="Data sources">
        <p className="muted">What each resource contributes, what it is <em>not</em> used for, how it is accessed, and how to cite it.</p>
      </PageHeader>
      {loading && <Loading />}
      <ErrorState error={error} onRetry={reload} what="data sources" />
      {data && (
        <div className="source-cards">
          {data.map((s) => (
            <Section key={s.key} title={s.name} subtitle={s.role}>
              <p>{s.purpose}</p>
              {s.not_used_for && <p className="small"><strong>Limitation:</strong> {s.not_used_for}</p>}
              <dl className="kv">
                {s.access && <div><dt>Access</dt><dd className="small">{s.access}</dd></div>}
                {s.url && <div><dt>Website</dt><dd className="small"><ExtLink href={s.url}>{s.url}</ExtLink></dd></div>}
                {s.citation && <div><dt>Citation</dt><dd className="small">{s.citation}{s.citation_pmids?.length > 0 && <> (PMID {s.citation_pmids.map((p, i) => <span key={p}>{i > 0 && ', '}<ExtLink href={`https://pubmed.ncbi.nlm.nih.gov/${p}/`}>{p}</ExtLink></span>)})</>}</dd></div>}
                {s.license && <div><dt>Licence / terms</dt><dd className="small">{s.license}</dd></div>}
                <div><dt>Records in atlas</dt><dd className="small">{s.association_source_records.toLocaleString()} association source records · {s.ncrna_gene_records.toLocaleString()} ncRNA–gene records</dd></div>
                <div><dt>Last import</dt><dd className="small">{s.last_import ? `${formatDate(s.last_import.completed_at)} · ${s.last_import.source_version || 'version not recorded'} · ${s.last_import.dataset_label} (job #${s.last_import.job_id})` : 'Not imported as a bulk source'}</dd></div>
              </dl>
            </Section>
          ))}
        </div>
      )}
      <Section title="Import history" subtitle="Every import is logged and auditable">
        {jobs.loading ? <Loading /> : jobs.error ? <ErrorState error={jobs.error} onRetry={jobs.reload} /> :
          jobs.data.length === 0 ? <EmptyState title="No imports yet" /> : (
            <div className="table-wrap">
              <table className="table compact">
                <thead><tr><th scope="col">#</th><th scope="col">Source</th><th scope="col">File / version</th><th scope="col">Dataset</th><th scope="col">Status</th><th scope="col">Completed</th><th scope="col" className="num">Processed</th><th scope="col" className="num">Inserted</th><th scope="col" className="num">Merged</th><th scope="col" className="num">Skipped</th></tr></thead>
                <tbody>
                  {jobs.data.map((j) => (
                    <tr key={j.id}>
                      <td>{j.id}</td><td>{j.source_database}</td>
                      <td className="small">{j.source_file}<br /><span className="muted">{j.source_version}</span></td>
                      <td><span className="badge org">{j.dataset_label}</span></td>
                      <td><span className={`badge job-${j.status}`}>{j.status.replaceAll('_', ' ')}</span>{j.error_summary && <div className="small muted">{j.error_summary}</div>}</td>
                      <td className="small">{formatDate(j.completed_at)}</td>
                      <td className="num">{j.records_processed.toLocaleString()}</td>
                      <td className="num">{j.records_inserted.toLocaleString()}</td>
                      <td className="num">{j.records_updated.toLocaleString()}</td>
                      <td className="num">{j.records_skipped.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Section>
    </>
  )
}

export function Methodology() {
  return (
    <>
      <PageHeader eyebrow="Documentation" title="Methodology">
        <p className="muted">How records are collected, normalized, deduplicated, classified and reviewed. Full details: <code>docs/methodology.md</code>.</p>
      </PageHeader>
      <Section title="1. Data collection">
        <ul>
          <li><strong>miRNA–disease:</strong> HMDD v3.2 bulk file (<code>alldata.txt</code>): category, miRNA precursor, MeSH-style disease name, PMID, evidence sentence. Some lines are not valid UTF-8 and are decoded with documented fallbacks (counted in each import report).</li>
          <li><strong>lncRNA–disease:</strong> LncRNADisease v3.0 (<code>website_alldata.tsv</code>): lncRNA rows only (circRNA rows are skipped and counted); species, dysfunction pattern, validation method, description, causality and PMID are preserved.</li>
          <li><strong>Curated records:</strong> a small hand-curated set in which every claim was checked against the PubMed abstract of the cited PMID.</li>
          <li><strong>Uploads:</strong> CSV/TSV files in the documented generic schema, miRTarBase MTI exports, or miRBase <code>miRNA.dat</code>.</li>
          <li>Every source record is stored verbatim (<em>original record</em>) with source name, record ID, version, import time and import job.</li>
        </ul>
      </Section>
      <Section title="2. Standardization">
        <ul>
          <li>Whitespace, wrapping quotes and Unicode dashes are normalized; case is preserved (<code>miR</code> vs <code>mir</code> is meaningful).</li>
          <li><strong>miRNAs</strong> are stored at precursor/locus level (e.g. <code>hsa-mir-21</code>), resolved through HGNC to a miRBase accession. Mature names (<code>hsa-miR-21-5p</code>) map to their precursor only when exactly one locus exists; names that omit the locus (e.g. <code>hsa-mir-16</code> → MIR16-1/MIR16-2) are kept but flagged <em>ambiguous</em>.</li>
          <li><strong>lncRNAs and genes</strong> resolve to HGNC: approved symbol, then a <em>unique</em> previous symbol, then a <em>unique</em> alias. A lncRNA name that resolves to a protein-coding gene is not merged.</li>
          <li><strong>Diseases</strong> are linked to a MeSH descriptor only on an exact label match; there is no fuzzy matching.</li>
          <li>Non-human records keep their organism, are excluded from human statistics and are labelled wherever shown.</li>
        </ul>
      </Section>
      <Section title="3. Deduplication">
        <p>An association is identified by <em>(ncRNA entity, disease entity, association type)</em>; organism is part of the ncRNA entity. Records describing the same association are merged and keep every source record and PMID. Re-importing a file is idempotent. Names that merely look similar are never merged.</p>
      </Section>
      <Section title="4. Evidence classification">
        <table className="table compact">
          <thead><tr><th scope="col">Level</th><th scope="col">Rule</th></tr></thead>
          <tbody>
            <tr><td>Experimental (source-reported)</td><td>HMDD experimental category, or LncRNADisease validation method, with a PMID.</td></tr>
            <tr><td>Literature, validation unclear</td><td>A PMID without a stated experimental method (e.g. HMDD category “other”).</td></tr>
            <tr><td>Computational prediction</td><td>Declared prediction in an uploaded dataset.</td></tr>
            <tr><td>Conflicting</td><td>Different records report up- and down-regulation for the same ncRNA, disease and association type.</td></tr>
            <tr><td>Unverified</td><td>No PMID and no method.</td></tr>
          </tbody>
        </table>
        <p className="small">Evidence levels describe what the sources report. They are separate from the <strong>curator review status</strong>, which changes only when a curator records a decision in the literature-review workflow. No confidence score is computed.</p>
      </Section>
      <Section title="5. Literature review workflow">
        <ol>
          <li>Retrieve the association’s publications and their PubMed metadata.</li>
          <li>Automated triage records whether the title/abstract mention the ncRNA and disease — as hints only.</li>
          <li>A curator reads each publication and records an outcome (direct experimental support, indirect support, prediction only, does not support, insufficient, conflicting) with the evidence type and date.</li>
          <li>The status becomes <em>Curator confirmed</em> only with at least one direct-experimental review and no contradicting review.</li>
        </ol>
      </Section>
      <Section title="6. KEGG pathway mapping">
        <p>Genes with an HGNC-resolved NCBI Gene ID are mapped with the KEGG REST API (<code>link/pathway/hsa:&lt;id&gt;</code>). Gene–pathway links are <em>direct</em>; pathways shown for ncRNAs, diseases and associations are <em>inferred via genes</em> and labelled as such. Genes without a reliable identifier are reported as unmapped.</p>
      </Section>
      <Section title="7. Interaction network">
        <p>Edges come only from stored records: associations (ncRNA–disease), ncRNA–gene relationships, and gene–disease links where a source record names the gene for that association. Genes are never connected to diseases just because they share an ncRNA.</p>
      </Section>
      <Section title="8. Known limitations">
        <ul>
          <li>Source curation quality and coverage are inherited; database membership is not proof of validity.</li>
          <li>HMDD reports miRNAs at precursor level and often without locus; such entries remain ambiguous.</li>
          <li>Disease names that are MeSH entry terms rather than descriptor headings remain unresolved.</li>
          <li>No bulk miRNA–target database is imported by default (miRTarBase requires a manual download); gene coverage is therefore limited to curated and uploaded records.</li>
          <li>miRBase was unreachable during development; sequences come from RNAcentral or a user-supplied <code>miRNA.dat</code>.</li>
          <li>KEGG mappings reflect the date of retrieval.</li>
        </ul>
        <p>See <Link to="/sources">Data sources</Link> for citations and licence terms.</p>
      </Section>
    </>
  )
}

export function NotFound() {
  return (
    <EmptyState title="Page not found">
      <Link to="/">Return to the dashboard</Link>
    </EmptyState>
  )
}
