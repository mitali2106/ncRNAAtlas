import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AdminPage from './pages/AdminPage'
import { AssociationDetail, AssociationList, PublicationDetail } from './pages/AssociationPages'
import { DiseaseDetail, DiseaseList } from './pages/DiseasePages'
import { GeneDetail, GeneList } from './pages/GenePages'
import Home from './pages/Home'
import { DataSources, Methodology, NotFound } from './pages/InfoPages'
import { NcRNADetail, NcRNAList } from './pages/NcRNAPages'
import NetworkPage from './pages/NetworkPage'
import { PathwayDetail, PathwayList } from './pages/PathwayPages'
import SearchPage from './pages/SearchPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="ncrnas" element={<NcRNAList />} />
        <Route path="ncrnas/:id" element={<NcRNADetail />} />
        <Route path="diseases" element={<DiseaseList />} />
        <Route path="diseases/:id" element={<DiseaseDetail />} />
        <Route path="genes" element={<GeneList />} />
        <Route path="genes/:id" element={<GeneDetail />} />
        <Route path="associations" element={<AssociationList />} />
        <Route path="associations/:id" element={<AssociationDetail />} />
        <Route path="publications/:pmid" element={<PublicationDetail />} />
        <Route path="pathways" element={<PathwayList />} />
        <Route path="pathways/:id" element={<PathwayDetail />} />
        <Route path="network" element={<NetworkPage />} />
        <Route path="sources" element={<DataSources />} />
        <Route path="methodology" element={<Methodology />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
