import { Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import SearchBox from './SearchBox'

const NAV = [
  ['/', 'Home'],
  ['/ncrnas', 'Explore ncRNAs'],
  ['/diseases', 'Diseases'],
  ['/genes', 'Genes'],
  ['/pathways', 'Pathways'],
  ['/network', 'Interaction Network'],
  ['/sources', 'Data Sources'],
  ['/methodology', 'Methodology'],
]

export default function Layout() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand" onClick={() => setOpen(false)}>
            <img src="/favicon.svg" alt="" width="28" height="28" />
            <span>
              ncRNA<strong>Atlas</strong>
            </span>
          </Link>
          {pathname !== '/' && pathname !== '/search' && (
            <div className="topbar-search">
              <SearchBox compact />
            </div>
          )}
          <button
            type="button"
            className="menu-btn"
            aria-expanded={open}
            aria-controls="main-nav"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
            <span className="sr-only">Menu</span>
          </button>
        </div>
        <nav id="main-nav" className={`mainnav ${open ? 'open' : ''}`} aria-label="Main">
          {NAV.map(([to, text]) => (
            <NavLink key={to} to={to} end={to === '/'} onClick={() => setOpen(false)}>
              {text}
            </NavLink>
          ))}
        </nav>
      </header>
      <main id="main" className="container">
        <Outlet />
      </main>
      <footer className="footer">
        <div className="container footer-inner">
          <div>
            <strong>ncRNAAtlas</strong> — an integrated atlas of non-coding RNA–disease associations.
            <br />
            Associations are imported from HMDD and LncRNADisease; identifiers from HGNC, miRBase, RNAcentral and
            MeSH; literature from PubMed; pathways from KEGG. Evidence levels are source-reported unless a curator
            review is shown.
          </div>
          <div className="footer-links">
            <Link to="/sources">Data sources &amp; citations</Link>
            <Link to="/methodology">Methodology</Link>
            <Link to="/admin">Data import (admin)</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
