import { useEffect, useRef, useState, type MouseEvent } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

declare global {
  interface Window { google?: any }
}
import {
  ArrowDownToLine,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Cloud,
  Command,
  Copy,
  Crosshair,
  Database,
  FileText,
  FileImage,
  Filter,
  Gauge,
  LayoutDashboard,
  LocateFixed,
  MapPin,
  Menu,
  MoreHorizontal,
  Network,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Upload,
  WandSparkles,
  X,
  Zap,
} from 'lucide-react'

type View = 'home' | 'document' | 'evidence' | 'observation' | 'overview' | 'search' | 'memory' | 'sync'
type Connection = 'online' | 'offline'
type GeoPoint = { lat: number, lng: number }
type FieldLocation = { id: string, name: string, region: string, country?: string, lat: number, lng: number, tag: string, description: string }
type PlaceDocument = { id: string, title: string, kind: string, text: string, source?: string, source_url?: string, site_id?: string, citation?: string, metadata?: Record<string, unknown> }
type SearchArea = { center: GeoPoint, north: number, south: number, east: number, west: number, radiusKm: number }
const API = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'
const GOOGLE_MAPS_API_KEY = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)?.trim()

const nav = [
  { id: 'home' as View, label: 'Home', icon: LayoutDashboard },
  { id: 'evidence' as View, label: 'Evidence Search', icon: Search },
  { id: 'observation' as View, label: 'Observation', icon: FileText },
]

const manualLocations: FieldLocation[] = [
  { id: 'yellowstone-backcountry', name: 'Yellowstone backcountry', region: 'Wyoming · USA', lat: 44.428, lng: -110.588, description: 'Remote geyser basins, wildlife corridors, and sparse cellular coverage.', tag: 'LOW CONNECTIVITY' },
  { id: 'great-smoky-mountains', name: 'Great Smoky Mountains', region: 'Tennessee · USA', lat: 35.611, lng: -83.489, description: 'High-use research trails with valleys where connectivity drops quickly.', tag: 'FIELD RESEARCH' },
  { id: 'yosemite-high-country', name: 'Yosemite high country', region: 'California · USA', lat: 37.865, lng: -119.538, description: 'Alpine trail systems, sparse services, and long offline stretches.', tag: 'REMOTE TERRAIN' },
]

const catalogRecords = [
  { category: 'Biodiversity', kind: 'biodiversity_record', title: 'Species observations around selected area', source: 'GBIF Occurrence API', detail: 'Plants, animals, taxonomy, event dates, coordinates, and occurrence evidence.', tone: 'violet' },
  { category: 'Water', kind: 'water_record', title: 'Streams, river gauges, and water quality', source: 'USGS Water Data APIs', detail: 'Monitoring locations, real-time sensor readings, daily values, and discrete samples.', tone: 'teal' },
  { category: 'Weather', kind: 'weather_record', title: 'Station weather and climate context', source: 'NOAA NCEI Climate Data Online', detail: 'Station observations, temperature, precipitation, and date-bounded climate context.', tone: 'orange' },
  { category: 'Trails & places', kind: 'terrain_record', title: 'Park trails and field access points', source: 'National Park Service APIs', detail: 'Parks, alerts, places, activities, and public trail geometries for manual area selection.', tone: 'blue' },
  { category: 'Protected areas', kind: 'protected_area_record', title: 'Protected-area boundaries', source: 'Protected Planet · WDPA', detail: 'Global protected-area polygons and designation metadata for research context.', tone: 'green' },
  { category: 'Terrain', kind: 'terrain_record', title: 'Elevation and terrain surface', source: 'USGS 3DEP', detail: 'Free lidar and DEM products for understanding slope, access, and terrain around a site.', tone: 'violet' },
]

function sourceReportSummary(text: string | undefined): string {
  if (!text) return 'No source summary is available for this record.'
  const normalized = text
    .replace(/\r/g, '')
    .replace(/\s+(?=#{1,3}\s)/g, '\n')
    .trim()
  const sections = normalized.split(/\n(?=##\s+)/)
  const preferred = sections.find((section) => /^##\s+(observation summary|forecast summary|feature summary|report summary|summary|overview)/i.test(section.trim()))
  const chosen = preferred ?? sections.find((section) => /^##\s+/i.test(section.trim()))
  const summary = (chosen ?? normalized)
    .replace(/^#{1,3}\s+[^\n]+\n?/, '')
    .replace(/\n#{1,3}\s+[^\n]+[\s\S]*$/, '')
    .replace(/\s+/g, ' ')
    .trim()
  return summary || 'No source summary is available for this record.'
}

const records = [
  { id: 'baseline-report', title: 'River Zone 3 Baseline Report', type: 'Research report', asset: 'River Zone 3', section: 'Seasonal water quality', state: 'Synced', updated: 'Aug 30, 12:00', points: 18, tone: 'violet' },
  { id: 'observation-series', title: 'Water-quality observations', type: 'Observation series', asset: 'River Zone 3', section: 'pH · turbidity · dissolved oxygen', state: 'Synced', updated: 'Aug 30, 11:42', points: 96, tone: 'teal' },
  { id: 'field-note', title: 'Field note · River Zone 3', type: 'Field note', asset: 'River Zone 3', section: 'Researcher observation', state: 'Needs review', updated: 'Ready for capture', points: 1, tone: 'orange' },
  { id: 'sampling-protocol', title: 'Freshwater Sampling Protocol', type: 'Procedure', asset: 'All sites', section: 'Calibration and duplicate samples', state: 'Synced', updated: 'Aug 28, 16:20', points: 14, tone: 'blue' },
]

const activities = [
  { time: '—', title: 'FieldNote pack ready', detail: 'River Zone 3 evidence is available on this device', icon: Database, type: 'sync' },
  { time: '—', title: 'Offline search is armed', detail: 'Ask about low oxygen, turbidity, or sampling procedure', icon: Search, type: 'search' },
  { time: '—', title: 'Shared knowledge staged', detail: 'Curated USGS/EPA-derived project pack loaded', icon: ArrowDownToLine, type: 'sync' },
  { time: '—', title: 'Connection policy active', detail: 'Local memory stays available when the network disappears', icon: Network, type: 'online' },
]

const results = [
  { score: '0.94', title: 'River Zone 3 Baseline Report', section: 'Seasonal water-quality baseline', kind: 'REPORT', text: 'The project pack records low dissolved oxygen and elevated turbidity in two post-rainfall River Zone 3 samples. Compare with an upstream reference and verify calibration before interpreting the pattern.', highlights: ['low dissolved oxygen', 'elevated turbidity', 'verify calibration'] },
  { score: '0.81', title: 'Water-quality observations', section: '14–15 Aug 2026 · post rainfall', kind: 'OBSERVATIONS', text: 'River Zone 3 recorded dissolved oxygen at 4.2 and 4.8 mg/L with turbidity at 15.0 and 18.4 NTU. These cross the project review bands and should trigger a duplicate sample.', highlights: ['4.2', '4.8', '15.0', '18.4'] },
  { score: '0.76', title: 'Freshwater Sampling Protocol', section: 'Calibration and duplicate sample', kind: 'PROCEDURE', text: 'Confirm the site code, calibration timestamp, weather, and instrument ID. If a value looks unusual, collect a duplicate and keep the finding local until it is verified.', highlights: ['calibration timestamp', 'duplicate', 'verified'] },
]

function BrandMark({ compact = false }: { compact?: boolean }) {
  return <img className={`brand-mark brand-logo ${compact ? 'compact' : ''}`} src="/quadoff-fieldnote-logo-clean.png" alt="QuadOff FieldNote" />
}

function App() {
  const [view, setView] = useState<View>('home')
  const [connection, setConnection] = useState<Connection>('online')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('Observed a post-rainfall reading at River Zone 3. Add instrument calibration, weather, and duplicate-sample details before sharing.')
  const [savedNote, setSavedNote] = useState(false)
  const [notePolicy, setNotePolicy] = useState<'needs-verification' | 'ready-to-sync'>('needs-verification')
  const [query, setQuery] = useState('Has low dissolved oxygen or high turbidity been reported near River Zone 3 before?')
  const [hasSearched, setHasSearched] = useState(true)
  const [filters, setFilters] = useState({ asset: true, site: true, document: false })
  const [syncing, setSyncing] = useState(false)
  const [booting, setBooting] = useState(true)
  const [localVectors, setLocalVectors] = useState(108)
  const [searchMatches, setSearchMatches] = useState<typeof results>(results)
  const [searchAnswer, setSearchAnswer] = useState('')
  const [searchLatency, setSearchLatency] = useState(43)
  const [searchOrigin, setSearchOrigin] = useState('Qdrant Edge')
  const [reasoningStatus, setReasoningStatus] = useState('')
  const [conflictCount, setConflictCount] = useState(1)
  const [selectedEvidence, setSelectedEvidence] = useState<any | null>(null)
  const [documentBackView, setDocumentBackView] = useState<View>('home')
  const [availableLocations, setAvailableLocations] = useState<FieldLocation[]>(manualLocations)
  const [manualLocationId, setManualLocationId] = useState(manualLocations[0].id)
  const [observationCategory, setObservationCategory] = useState('Plants & vegetation')
  const [observationNote, setObservationNote] = useState('')
  const [qualitativeEvidence, setQualitativeEvidence] = useState('')
  const [refinedObservation, setRefinedObservation] = useState<{ title: string, summary: string, engine?: string, model_status?: string, used_model?: boolean } | null>(null)
  const [refining, setRefining] = useState(false)
  const [observationImages, setObservationImages] = useState<File[]>([])
  const [savedObservation, setSavedObservation] = useState<any | null>(null)
  const [observationStatus, setObservationStatus] = useState('Draft · not saved')
  const [uploadStatus, setUploadStatus] = useState('')

  const pendingCount = savedNote ? 1 : 0

  useEffect(() => {
    const timer = window.setTimeout(() => setBooting(false), 2100)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    fetch(`${API}/api/status`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('offline')))
      .then((status) => {
        setConnection(status.connectivity === 'offline' ? 'offline' : 'online')
        setLocalVectors(status.edge_vectors ?? status.local_memory ?? 108)
        setSavedNote((status.pending_sync ?? 0) > 0)
        setConflictCount(status.open_conflicts ?? 0)
        setReasoningStatus(status.reasoning ?? '')
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    fetch('/field-locations.json')
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('location catalog unavailable')))
      .then((locations: FieldLocation[]) => {
        if (Array.isArray(locations) && locations.length >= 30) setAvailableLocations(locations)
      })
      .catch(() => undefined)
  }, [])

  function selectView(next: View) {
    setView(next)
    setMobileOpen(false)
  }

  function startObservationFromEvidence(evidence: any | null = selectedEvidence) {
    setSelectedEvidence(evidence)
    setObservationNote('')
    setQualitativeEvidence('')
    setRefinedObservation(null)
    setSavedObservation(null)
    setObservationImages([])
    setObservationStatus('Draft · not saved')
    setUploadStatus('')
    selectView('observation')
  }

  function updateObservationImages(files: FileList | null) {
    if (!files) return
    setObservationImages(Array.from(files).slice(0, 6))
  }

  async function refineObservation() {
    if (!observationNote.trim() && !qualitativeEvidence.trim()) return
    setRefining(true)
    try {
      const response = await fetch(`${API}/api/observations/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          observation: observationNote,
          evidence: qualitativeEvidence,
          query,
          source_title: selectedEvidence?.title ?? 'Selected field evidence',
          source_text: selectedEvidence?.text ?? '',
          category: observationCategory,
          location: availableLocations.find((location) => location.id === manualLocationId)?.name,
          network_allowed: connection === 'online',
        }),
      })
      if (!response.ok) throw new Error('Refinement unavailable')
      const payload = await response.json()
      setRefinedObservation({ title: payload.title, summary: payload.summary, engine: payload.engine, model_status: payload.model_status, used_model: payload.used_model })
    } catch {
      const location = availableLocations.find((item) => item.id === manualLocationId)?.name ?? 'selected area'
      setRefinedObservation({
        title: `${observationCategory} observation · ${location}`,
        summary: `${observationNote.trim()} ${qualitativeEvidence.trim()}`.trim() || 'No observation text entered yet.',
        engine: 'browser fallback',
        model_status: 'Edge service unavailable; no model ran.',
        used_model: false,
      })
    } finally {
      setRefining(false)
    }
  }

  async function saveObservation() {
    if (!observationNote.trim() && !qualitativeEvidence.trim()) return
    const location = availableLocations.find((item) => item.id === manualLocationId) ?? availableLocations[0]
    setObservationStatus('Saving a new local copy…')
    try {
      const response = await fetch(`${API}/api/observations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: refinedObservation?.title ?? `${observationCategory} observation · ${location.name}`,
          observation: observationNote,
          evidence: qualitativeEvidence,
          refined_summary: refinedObservation?.summary ?? '',
          category: observationCategory,
          site_id: location.id,
          location: { name: location.name, region: location.region, latitude: location.lat, longitude: location.lng },
          source_memory_id: selectedEvidence?.id ?? null,
          source_title: selectedEvidence?.title ?? null,
          query,
          policy: 'ready-to-sync',
        }),
      })
      if (!response.ok) throw new Error('Save failed')
      const payload = await response.json()
      setSavedObservation(payload.item)
      setObservationStatus(payload.queued ? 'Saved as a new record · ready to upload' : 'Saved as a new local record')
      if (observationImages.length) {
        for (const image of observationImages) {
          const reader = new FileReader()
          const dataUrl = await new Promise<string>((resolve, reject) => {
            reader.onload = () => resolve(String(reader.result))
            reader.onerror = reject
            reader.readAsDataURL(image)
          })
          await fetch(`${API}/api/observations/${payload.item.id}/images`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: image.name, mime_type: image.type || 'application/octet-stream', data_url: dataUrl }),
          })
        }
      }
    } catch {
      setObservationStatus('Saved in this browser draft · backend unavailable')
    }
  }

  async function uploadObservation() {
    if (!savedObservation) return
    setUploadStatus('Uploading new record to Qdrant…')
    try {
      const response = await fetch(`${API}/api/observations/${savedObservation.id}/upload`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail ?? 'Upload failed')
      setUploadStatus(payload.message ?? 'New record acknowledged by Qdrant')
      setSavedObservation(payload.item ?? savedObservation)
    } catch {
      setUploadStatus('Upload queued locally. It will be delivered when a central Qdrant connection is available.')
    }
  }

  function toggleConnectivity() {
    const next = connection === 'online' ? 'offline' : 'online'
    setConnection(next)
    fetch(`${API}/api/connectivity`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ online: next === 'online' }) })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload.detail ?? 'Connectivity update failed')
        if (next === 'online') {
          setSavedNote((payload.pending_sync ?? 0) > 0)
          if (payload.sync?.delivered > 0) {
            setUploadStatus(`Connection restored · ${payload.sync.delivered} queued record${payload.sync.delivered === 1 ? '' : 's'} uploaded to Qdrant`)
          } else if (payload.sync_error) {
            setUploadStatus('Connection restored · upload still queued until Qdrant is reachable')
          }
        }
      })
      .catch(() => {
        setConnection(connection)
        if (next === 'online') setUploadStatus('Reconnect could not be confirmed · local records remain queued')
      })
  }

  function runSync() {
    if (connection === 'offline') return
    setSyncing(true)
    fetch(`${API}/api/sync/run`, { method: 'POST' })
      .then(() => setSavedNote(false))
      .finally(() => setSyncing(false))
  }

  function createNote() {
    if (!note.trim()) return
    setSavedNote(notePolicy === 'ready-to-sync')
    setNoteOpen(false)
    setView('memory')
    fetch(`${API}/api/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: 'Field note · River Zone 3', text: note, site_id: 'river-zone-3', policy: notePolicy }) }).catch(() => undefined)
  }

  function runSearch() {
    setHasSearched(true)
    setSearchMatches([])
    setSearchAnswer('')
    fetch(`${API}/api/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, site_id: filters.site ? manualLocationId : undefined, limit: 6, source: 'edge' }) })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('search failed')))
      .then((payload) => {
        const mapped = payload.matches.map((match: { id: string, score: number, title: string, kind: string, text: string, citation: string }) => ({ id: match.id, score: match.score.toFixed(2), title: match.title, section: match.citation, kind: match.kind.replace('_', ' ').toUpperCase(), text: match.text, highlights: ['dissolved oxygen', 'turbidity', 'calibration', 'duplicate'] }))
        setSearchMatches(mapped)
        setSearchAnswer(payload.answer?.summary ?? '')
        setSearchLatency(payload.retrieval?.latency_ms ?? 43)
        setSearchOrigin(payload.retrieval?.origin ?? 'Qdrant Edge')
      })
      .catch(() => undefined)
  }

  function openEvidenceSearch() {
    selectView('evidence')
    // Prime the search page with the current region instead of showing stale
    // results from whichever place was searched previously.
    runSearch()
  }

  function runAreaSearch(area: SearchArea) {
    const areaQuery = `Environmental evidence near ${area.center.lat.toFixed(3)}, ${area.center.lng.toFixed(3)}`
    const searchSource = connection === 'online' ? 'cloud' : 'edge'
    setQuery(areaQuery)
    setView('search')
    setHasSearched(false)
    setSearchMatches([])
    setSearchAnswer('')
    fetch(`${API}/api/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: areaQuery, site_id: 'river-zone-3', limit: 6, source: searchSource, area }) })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('area search failed')))
      .then((payload) => {
        const mapped = payload.matches.map((match: { id: string, score: number, title: string, kind: string, text: string, citation: string }) => ({ id: match.id, score: match.score.toFixed(2), title: match.title, section: match.citation, kind: match.kind.replace('_', ' ').toUpperCase(), text: match.text, highlights: ['dissolved oxygen', 'turbidity', 'calibration', 'duplicate'] }))
        setSearchMatches(mapped)
        setSearchAnswer(payload.answer?.summary ?? '')
        setSearchLatency(payload.retrieval?.latency_ms ?? 43)
        setSearchOrigin(payload.retrieval?.origin ?? 'Central demo · Edge fallback')
        setHasSearched(true)
      })
      .catch(() => setHasSearched(true))
  }

  function runManualAreaSearch(area: SearchArea) {
    const areaQuery = `Environmental evidence near ${area.center.lat.toFixed(3)}, ${area.center.lng.toFixed(3)}`
    const searchSource = connection === 'online' ? 'cloud' : 'edge'
    setQuery(areaQuery)
    setView('evidence')
    setHasSearched(false)
    setSearchMatches([])
    setSearchAnswer('')
    fetch(`${API}/api/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: areaQuery, site_id: manualLocationId, limit: 8, source: searchSource, area }) })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('area search failed')))
      .then((payload) => {
        const mapped = payload.matches.map((match: { id: string, score: number, title: string, kind: string, text: string, citation: string }) => ({ id: match.id, score: match.score.toFixed(2), title: match.title, section: match.citation, kind: match.kind.replace('_', ' ').toUpperCase(), text: match.text, highlights: ['dissolved oxygen', 'turbidity', 'calibration', 'duplicate'] }))
        setSearchMatches(mapped)
        setSearchAnswer(payload.answer?.summary ?? '')
        setSearchLatency(payload.retrieval?.latency_ms ?? 43)
        setSearchOrigin(payload.retrieval?.origin ?? 'Qdrant Edge')
        setHasSearched(true)
      })
      .catch(() => setHasSearched(true))
  }

  async function openCatalogRecord(document: PlaceDocument) {
    const preview = {
      ...document,
      section: document.citation ?? `${document.source ?? 'Source dataset'} · source-linked record`,
      kind: document.kind.replace(/_/g, ' ').toUpperCase(),
    }
    setSelectedEvidence(preview)
    setDocumentBackView('home')
    setQuery(document.title)
    setView('document')
    try {
      const response = await fetch(`${API}/api/documents/${encodeURIComponent(document.id)}`)
      if (!response.ok) throw new Error('document detail unavailable')
      const detail = await response.json()
      setSelectedEvidence({
        ...detail,
        section: detail.citation ?? preview.section,
        kind: detail.kind.replace(/_/g, ' ').toUpperCase(),
      })
    } catch {
      // The preview still contains the source-linked record and remains
      // readable if the edge service is temporarily unavailable.
    }
  }

  async function openSearchResult(result: any) {
    const preview = {
      ...result,
      section: result.section ?? `${result.source ?? 'Source dataset'} · source-linked record`,
      kind: String(result.kind ?? 'FIELD RECORD').replace(/_/g, ' ').toUpperCase(),
    }
    setSelectedEvidence(preview)
    setDocumentBackView('evidence')
    setView('document')
    try {
      const response = await fetch(`${API}/api/documents/${encodeURIComponent(result.id)}`)
      if (!response.ok) throw new Error('document detail unavailable')
      const detail = await response.json()
      setSelectedEvidence({
        ...detail,
        section: detail.citation ?? preview.section,
        kind: String(detail.kind ?? preview.kind).replace(/_/g, ' ').toUpperCase(),
      })
    } catch {
      // Local observations may not have a public source snapshot. The
      // result preview still opens as a readable document.
    }
  }

  function resolveConflict(choice: 'local' | 'remote' | 'merged') {
    fetch(`${API}/api/conflicts/conflict-finding-demo-conflict/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ choice }) })
      .then((response) => { if (response.ok) setConflictCount(0) })
      .catch(() => undefined)
  }

  return (<>
    <EdgeBootScreen visible={booting} />
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'is-open' : ''}`}>
        <div className="sidebar-top">
          <div className="brand"><BrandMark /></div>
          <button className="icon-button close-mobile" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <div className="workspace-label">FIELD OPERATIONS</div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon
            return <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => item.id === 'evidence' ? openEvidenceSearch() : selectView(item.id)}><Icon size={18} strokeWidth={1.8} /><span>{item.label}</span>{item.id === 'sync' && pendingCount > 0 && <b>{pendingCount}</b>}</button>
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="edge-card">
            <div className="edge-card-header"><span className="mini-pulse" />Qdrant Edge</div>
            <p>Local device memory</p>
            <div><strong>{localVectors}</strong><span> vectors indexed</span></div>
            <div className="edge-storage"><span>Shard storage</span><strong>18.4 MB</strong></div>
            <div className="progress"><i /></div>
          </div>
          <button className="profile"><span className="avatar">AK</span><span><strong>Arjun Kumar</strong><small>Field Technician</small></span><MoreHorizontal size={18} /></button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="page-context"><button className="icon-button menu-mobile" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="brand-inline"><BrandMark /></div></div>
          <div className="top-actions">
            <div className="device-signals"><button className="icon-button" aria-label="Satellite status"><Network size={17} /></button><button className="icon-button" aria-label="Local vector store"><Database size={17} /></button><button className="icon-button" aria-label="Mesh radio"><Cloud size={17} /></button></div>
            <button className={`connection-button ${connection}`} onClick={toggleConnectivity}><span className="status-dot" />{connection === 'online' ? 'Connected' : 'Offline'}<ChevronDown size={14} /></button>
            <button className="secondary-button compact" aria-label="Calibrate device"><Settings size={16} />Calibrate</button>
            <button className="secondary-button compact new-observation" onClick={() => startObservationFromEvidence()}><Plus size={17} />New observation</button>
            <span className="node-badge">H-03</span>
          </div>
        </header>
        <div className="module-nav" aria-label="FieldNote modules">
          {nav.map((item) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => item.id === 'evidence' ? openEvidenceSearch() : selectView(item.id)}><Icon size={15} /><span>{item.label}</span>{item.id === 'sync' && (pendingCount > 0 || conflictCount > 0) && <b>{pendingCount + conflictCount}</b>}</button> })}
        </div>
        <div className="content">
          <div className="view-transition" key={view}>
            {view === 'home' && <HomePage locations={availableLocations} locationId={manualLocationId} setLocationId={setManualLocationId} onEvidenceSearch={openEvidenceSearch} onSearchArea={runManualAreaSearch} onOpenRecord={openCatalogRecord} />}
            {view === 'document' && <DocumentPage document={selectedEvidence} onBack={() => selectView(documentBackView)} onSearch={() => selectView('evidence')} onRelevant={() => startObservationFromEvidence(selectedEvidence)} />}
            {view === 'evidence' && <EvidenceSearchPage query={query} setQuery={setQuery} onSearch={runSearch} results={searchMatches} answer={searchAnswer} latency={searchLatency} origin={searchOrigin} connection={connection} regionLabel={availableLocations.find((location) => location.id === manualLocationId)?.name ?? 'Selected region'} onOpenResult={openSearchResult} />}
            {view === 'observation' && <ObservationPage connection={connection} locations={availableLocations} locationId={manualLocationId} setLocationId={setManualLocationId} category={observationCategory} setCategory={setObservationCategory} query={query} selectedEvidence={selectedEvidence} note={observationNote} setNote={setObservationNote} evidence={qualitativeEvidence} setEvidence={setQualitativeEvidence} refined={refinedObservation} refining={refining} reasoningStatus={reasoningStatus} onRefine={refineObservation} images={observationImages} onImages={updateObservationImages} onSave={saveObservation} saved={savedObservation} status={observationStatus} uploadStatus={uploadStatus} onUpload={uploadObservation} />}
          </div>
        </div>
      </main>
      {mobileOpen && <button className="backdrop" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />}
      {noteOpen && <NewNoteModal note={note} setNote={setNote} policy={notePolicy} setPolicy={setNotePolicy} onClose={() => setNoteOpen(false)} onSave={createNote} />}
    </div>
  </>)
}

function EdgeBootScreen({ visible }: { visible: boolean }) {
  return <div className={`boot-screen ${visible ? '' : 'exit'}`} aria-hidden={!visible}>
    <div className="boot-grid" />
    <div className="boot-orbit orbit-one" /><div className="boot-orbit orbit-two" /><div className="boot-orbit orbit-three" />
    <div className="boot-core"><BrandMark compact /></div>
    <div className="boot-copy"><span>QUADOFF / QDRANT EDGE</span><strong>Local intelligence<br />is coming online.</strong><div className="boot-progress"><i /></div><small>WAKING LOCAL VECTOR MEMORY</small></div>
  </div>
}

function LiveMap(props: { coordinate: GeoPoint, radiusKm: number, onCoordinateChange: (point: GeoPoint) => void }) {
  const [provider, setProvider] = useState<'google' | 'leaflet'>(GOOGLE_MAPS_API_KEY ? 'google' : 'leaflet')
  return provider === 'google'
    ? <GoogleLiveMap {...props} onFallback={() => setProvider('leaflet')} />
    : <LeafletLiveMap {...props} />
}

function GoogleLiveMap({ coordinate, radiusKm, onCoordinateChange, onFallback }: { coordinate: GeoPoint, radiusKm: number, onCoordinateChange: (point: GeoPoint) => void, onFallback: () => void }) {
  const elementRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<any>(null)
  const markerRef = useRef<any>(null)
  const circleRef = useRef<any>(null)
  const nodeRefs = useRef<any[]>([])
  const [ready, setReady] = useState(Boolean(window.google?.maps))

  useEffect(() => {
    if (window.google?.maps || !GOOGLE_MAPS_API_KEY) {
      setReady(Boolean(window.google?.maps))
      return
    }
    const existing = document.querySelector<HTMLScriptElement>('script[data-quadoff-google-maps]')
    const script = existing ?? document.createElement('script')
    if (!existing) {
      script.dataset.quadoffGoogleMaps = 'true'
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_API_KEY)}&v=weekly`
      script.async = true
      script.defer = true
      document.head.appendChild(script)
    }
    const handleLoad = () => setReady(Boolean(window.google?.maps))
    const handleError = () => onFallback()
    script.addEventListener('load', handleLoad)
    script.addEventListener('error', handleError)
    return () => {
      script.removeEventListener('load', handleLoad)
      script.removeEventListener('error', handleError)
    }
  }, [onFallback])

  useEffect(() => {
    if (!ready || !elementRef.current || mapRef.current || !window.google?.maps) return
    const googleMaps = window.google.maps
    const map = new googleMaps.Map(elementRef.current, {
      center: coordinate,
      zoom: 11,
      minZoom: 3,
      maxZoom: 19,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: false,
      zoomControl: true,
      zoomControlOptions: { position: googleMaps.ControlPosition.RIGHT_BOTTOM },
      backgroundColor: '#06132d',
      styles: [
        { elementType: 'geometry', stylers: [{ color: '#06132d' }] },
        { elementType: 'labels.text.fill', stylers: [{ color: '#aebbd4' }] },
        { elementType: 'labels.text.stroke', stylers: [{ color: '#06132d' }] },
        { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#263d70' }] },
        { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#07162f' }] },
        { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#0b2340' }] },
        { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#0b3034' }] },
        { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#142b52' }] },
        { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#203d70' }] },
        { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#273c71' }] },
        { featureType: 'transit', elementType: 'geometry', stylers: [{ color: '#102747' }] },
        { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#031b35' }] },
        { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#6291cb' }] },
      ],
    })
    const signal = { path: googleMaps.SymbolPath.CIRCLE, scale: 8, fillColor: '#ef235b', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 }
    markerRef.current = new googleMaps.Marker({ position: coordinate, map, title: 'Selected research coordinate', icon: signal })
    circleRef.current = new googleMaps.Circle({ map, center: coordinate, radius: radiusKm * 1000, strokeColor: '#ef235b', strokeOpacity: .95, strokeWeight: 2, fillColor: '#ef235b', fillOpacity: .12 })
    const nodeOffsets = [{ lat: 0.025, lng: 0.035, color: '#40d69a' }, { lat: -0.018, lng: -0.04, color: '#755cff' }, { lat: 0.045, lng: -0.015, color: '#ef235b' }]
    nodeRefs.current = nodeOffsets.map((node) => new googleMaps.Marker({ map, position: { lat: coordinate.lat + node.lat, lng: coordinate.lng + node.lng }, icon: { path: googleMaps.SymbolPath.CIRCLE, scale: 5, fillColor: node.color, fillOpacity: 1, strokeColor: '#fff', strokeWeight: 1 } }))
    map.addListener('click', (event: any) => {
      if (event.latLng) onCoordinateChange({ lat: event.latLng.lat(), lng: event.latLng.lng() })
    })
    mapRef.current = map
    let phase = 0
    const pulseTimer = window.setInterval(() => {
      phase += 1
      const selectedScale = phase % 2 === 0 ? 8 : 10
      markerRef.current?.setIcon({ ...signal, scale: selectedScale })
      nodeRefs.current.forEach((node, index) => node.setIcon({ path: googleMaps.SymbolPath.CIRCLE, scale: phase % 2 === index % 2 ? 5 : 4, fillColor: nodeOffsets[index].color, fillOpacity: 1, strokeColor: '#fff', strokeWeight: 1 }))
    }, 900)
    return () => {
      window.clearInterval(pulseTimer)
      mapRef.current = null
      markerRef.current = null
      circleRef.current = null
      nodeRefs.current = []
    }
  }, [ready, onCoordinateChange])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !markerRef.current || !circleRef.current) return
    markerRef.current.setPosition(coordinate)
    circleRef.current.setCenter(coordinate)
    circleRef.current.setRadius(radiusKm * 1000)
    const offsets = [{ lat: 0.025, lng: 0.035 }, { lat: -0.018, lng: -0.04 }, { lat: 0.045, lng: -0.015 }]
    nodeRefs.current.forEach((node, index) => node.setPosition({ lat: coordinate.lat + offsets[index].lat, lng: coordinate.lng + offsets[index].lng }))
    map.panTo(coordinate)
  }, [coordinate.lat, coordinate.lng, radiusKm])

  return <div className="live-map-shell"><div ref={elementRef} className="live-map" role="application" aria-label="Live Google map for selecting a research coordinate" />{!ready && <div className="live-map-loading"><span className="radar-dot" />LOADING GOOGLE MAPS…</div>}<div className="live-map-status"><span className="radar-dot" />LIVE GOOGLE MAP · CLICK TO MOVE COORDINATE</div><div className="live-map-coordinate">{coordinate.lat.toFixed(5)} · {coordinate.lng.toFixed(5)}<small>{radiusKm} KM RADIUS</small></div></div>
}

function LeafletLiveMap({ coordinate, radiusKm, onCoordinateChange }: { coordinate: GeoPoint, radiusKm: number, onCoordinateChange: (point: GeoPoint) => void }) {
  const elementRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markerRef = useRef<L.Marker | null>(null)
  const circleRef = useRef<L.Circle | null>(null)
  const nodeRefs = useRef<L.Marker[]>([])

  useEffect(() => {
    if (!elementRef.current || mapRef.current) return
    const map = L.map(elementRef.current, { zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 19 }).setView([coordinate.lat, coordinate.lng], 11)
    L.control.zoom({ position: 'bottomright' }).addTo(map)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd',
      maxZoom: 19,
      opacity: 0.9,
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    }).addTo(map)
    const pinIcon = L.divIcon({ className: 'live-pin-icon', html: '<span class="live-pin-core">⌖</span>', iconSize: [34, 34], iconAnchor: [17, 34] })
    markerRef.current = L.marker([coordinate.lat, coordinate.lng], { icon: pinIcon, keyboard: false }).addTo(map)
    circleRef.current = L.circle([coordinate.lat, coordinate.lng], { radius: radiusKm * 1000, color: '#ef235b', weight: 1.5, fillColor: '#ef235b', fillOpacity: 0.12, dashArray: '7 7' }).addTo(map)
    const nodeOffsets = [{ lat: 0.025, lng: 0.035, className: 'node-alpha' }, { lat: -0.018, lng: -0.04, className: 'node-beta' }, { lat: 0.045, lng: -0.015, className: 'node-coral' }]
    nodeRefs.current = nodeOffsets.map((node) => L.marker([coordinate.lat + node.lat, coordinate.lng + node.lng], { icon: L.divIcon({ className: `live-node-icon ${node.className}`, html: '<span></span>', iconSize: [14, 14], iconAnchor: [7, 7] }), interactive: false }).addTo(map))
    map.on('click', (event) => onCoordinateChange({ lat: event.latlng.lat, lng: event.latlng.lng }))
    mapRef.current = map
    window.setTimeout(() => map.invalidateSize(), 50)
    return () => {
      map.remove()
      mapRef.current = null
      markerRef.current = null
      circleRef.current = null
      nodeRefs.current = []
    }
  }, [onCoordinateChange])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !markerRef.current || !circleRef.current) return
    const latLng: L.LatLngExpression = [coordinate.lat, coordinate.lng]
    markerRef.current.setLatLng(latLng)
    circleRef.current.setLatLng(latLng).setRadius(radiusKm * 1000)
    const offsets = [{ lat: 0.025, lng: 0.035 }, { lat: -0.018, lng: -0.04 }, { lat: 0.045, lng: -0.015 }]
    nodeRefs.current.forEach((node, index) => node.setLatLng([coordinate.lat + offsets[index].lat, coordinate.lng + offsets[index].lng]))
    map.setView(latLng, map.getZoom(), { animate: true, duration: .45 })
  }, [coordinate.lat, coordinate.lng, radiusKm])

  return <div className="live-map-shell"><div ref={elementRef} className="live-map" role="application" aria-label="Live map for selecting a research coordinate" /><div className="live-map-status"><span className="radar-dot" />LIVE TILES · CLICK TO MOVE COORDINATE</div><div className="live-map-coordinate">{coordinate.lat.toFixed(5)} · {coordinate.lng.toFixed(5)}<small>{radiusKm} KM RADIUS</small></div></div>
}

function HomePage({ locations, locationId, setLocationId, onEvidenceSearch, onSearchArea, onOpenRecord }: { locations: FieldLocation[], locationId: string, setLocationId: (value: string) => void, onEvidenceSearch: () => void, onSearchArea: (area: SearchArea) => void, onOpenRecord: (record: PlaceDocument) => void }) {
  const radiusKm = 6
  const location = locations.find((item) => item.id === locationId) ?? locations[0]
  const [selectedCoordinate, setSelectedCoordinate] = useState({ lat: location.lat, lng: location.lng })
  const [placeDocuments, setPlaceDocuments] = useState<PlaceDocument[]>([])

  useEffect(() => {
    setSelectedCoordinate({ lat: location.lat, lng: location.lng })
  }, [locationId, location.lat, location.lng])

  useEffect(() => {
    setPlaceDocuments([])
    fetch(`${API}/api/documents?site_id=${encodeURIComponent(location.id)}&limit=40`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('documents unavailable')))
      .then((payload) => setPlaceDocuments(Array.isArray(payload.documents) ? payload.documents : []))
      .catch(() => setPlaceDocuments([]))
  }, [location.id])

  function searchArea() {
    const latDelta = radiusKm / 111
    const lngDelta = radiusKm / (111 * Math.cos(selectedCoordinate.lat * Math.PI / 180))
    onSearchArea({ center: selectedCoordinate, north: selectedCoordinate.lat + latDelta, south: selectedCoordinate.lat - latDelta, east: selectedCoordinate.lng + lngDelta, west: selectedCoordinate.lng - lngDelta, radiusKm })
  }

  const relevantRecords = catalogRecords.map((record) => ({ ...record, title: `${location.name} · ${record.category} evidence`, detail: `${record.detail} Relevant to the selected ${location.name} field area.` }))
  const fallbackDocuments: PlaceDocument[] = relevantRecords.map((record, index) => ({ id: `fallback-${location.id}-${record.kind}-${index}`, title: `${location.name} · ${record.category} overview`, kind: record.kind, text: `${record.detail} This document is specific to ${location.name} (${location.region}) around ${location.lat.toFixed(4)}, ${location.lng.toFixed(4)}.`, source: record.source, metadata: { category: record.category, region: location.region, latitude: location.lat, longitude: location.lng, document_index: index + 1, document_total: 40, document_heading: record.title, sections: ['Summary', 'Field relevance', 'Source and provenance'] } }))
  const documents = placeDocuments.length ? placeDocuments : fallbackDocuments
  const toneForCategory = (category: string) => category.toLowerCase().includes('water') ? 'teal' : category.toLowerCase().includes('weather') ? 'orange' : category.toLowerCase().includes('terrain') || category.toLowerCase().includes('trail') ? 'blue' : category.toLowerCase().includes('protected') ? 'green' : 'violet'

  return <section className="new-page home-page">
    <div className="new-page-intro"><div><h1>Choose where to wander.</h1></div><span className="demo-mode-pill"><span className="status-dot" />DEMO · COORDINATES SELECTED MANUALLY</span></div>
    <section className="home-map-panel">
      <div className="new-panel-heading"><div><p className="eyebrow">01 · SEARCH AREA</p><h2>Research area</h2></div><span className="map-coordinate-badge">{selectedCoordinate.lat.toFixed(3)}° N · {Math.abs(selectedCoordinate.lng).toFixed(3)}° W</span></div>
      <div className="manual-location-controls"><label>Choose a low-connectivity place<select value={locationId} onChange={(event) => setLocationId(event.target.value)}>{locations.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.region}</option>)}</select></label></div>
      <LiveMap coordinate={selectedCoordinate} radiusKm={radiusKm} onCoordinateChange={setSelectedCoordinate} />
      <div className="home-map-footer"><div><strong>{location.name}</strong><span>{location.description}</span></div><button className="primary-button" onClick={searchArea}><Search size={16} />Search this area</button></div>
    </section>
    <section className="records-section"><div className="new-panel-heading"><div><p className="eyebrow">02 · RECORDS AVAILABLE FOR THIS PLACE</p><h2>{location.name}</h2></div><button className="secondary-button" onClick={onEvidenceSearch}><Search size={15} />Open Evidence Search</button></div><div className="catalog-grid">{documents.map((document) => { const category = String(document.metadata?.category ?? document.kind.replace(/_/g, ' ')); return <button type="button" className="catalog-card" key={document.id} onClick={() => onOpenRecord(document)} aria-label={`Open ${document.title}`}><div className={`catalog-icon ${toneForCategory(category)}`}><BookOpen size={17} /></div><div><span>{category}</span><h3>{document.title}</h3><p>{searchResultSummary(document.text)}</p></div></button> })}</div></section>
  </section>
}

function renderRecordFields(body: string) {
  return <div className="document-field-list">{body.split('\n').map((line, index) => {
    const value = line.trim()
    if (!value) return null
    const separator = value.indexOf(':')
    const label = separator > 0 ? value.slice(0, separator).trim() : `Field ${index + 1}`
    const fieldValue = separator > 0 ? value.slice(separator + 1).trim() : value
    if (label.toLowerCase() === 'tags') {
      try {
        const tags = JSON.parse(fieldValue) as Record<string, unknown>
        return <div className="document-field-row" key={line}><dt>{label}</dt><dd className="document-tag-list">{Object.entries(tags).map(([tag, tagValue]) => <span key={tag}><b>{tag}</b><em>{String(tagValue)}</em></span>)}</dd></div>
      } catch {
        // Keep an unexpected source value readable instead of exposing a raw
        // object block or failing the whole document view.
      }
    }
    return <div className="document-field-row" key={line}><dt>{label}</dt><dd>{fieldValue}</dd></div>
  })}</div>
}

function documentFieldInterpretation(document: any) {
  const source = String(document.source ?? '')
  if (!/openstreetmap/i.test(source)) return ''
  const text = String(document.text ?? '')
  const name = text.match(/\nName:\s*([^\n]+)/i)?.[1]?.trim() ?? document.title
  const tagsLine = text.match(/\nTags:\s*(\{[^\n]+\})/i)?.[1]
  let tags: Record<string, unknown> = {}
  try {
    tags = tagsLine ? JSON.parse(tagsLine) as Record<string, unknown> : {}
  } catch {
    tags = {}
  }
  const featureType = String(tags.natural ?? tags.highway ?? tags.waterway ?? tags.landuse ?? tags.amenity ?? 'mapped landscape feature')
  const elevation = tags.ele ? ` It is recorded at approximately ${String(tags.ele)} metres elevation.` : ''
  const alternateName = tags['alt_name:en'] ? ` The alternate name is ${String(tags['alt_name:en'])}.` : ''
  const prominence = tags.prominence ? ` The source lists ${String(tags.prominence)} metres of prominence.` : ''
  const coordinate = text.match(/map center is ([^ ]+,\s*[^ ]+)/i)?.[1]
  const area = document.metadata?.region ?? 'the selected research area'
  return `This record identifies ${name} as a mapped ${featureType} in ${area}.${coordinate ? ` The mapped reference point is ${coordinate}.` : ''}${elevation}${prominence}${alternateName} The information is useful for planning a field visit, locating the feature on the ground, and comparing the mapped reference with current access, snow, vegetation, or surrounding terrain. Because this is a point or mapped geometry from OpenStreetMap, it should be treated as a reference rather than a current condition report. Verify the feature and its approach route in the field before recording a new observation.`
}

function cleanGeneratedLabel(value: string) {
  return value
    .replace(/\s*[·•]\s*(?:mapped feature|GBIF occurrence|hourly weather|weather day)\s*\d+\b/gi, '')
    .replace(/\s+(?:mapped feature|GBIF occurrence|hourly weather|weather day)\s+\d+\b/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

function renderDocumentText(text: string) {
  const displayText = text.replace(/^Original response:.*$/gim, 'Source link: available through the source action on this page.')
  return displayText.split(/\n\s*\n/).filter(Boolean).map((block, index) => {
    const value = block.trim()
    const lines = value.split('\n')
    const firstLine = lines[0].trim()
    if (firstLine.startsWith('# ') || firstLine.startsWith('## ')) {
      const isMainHeading = firstLine.startsWith('# ')
      const heading = cleanGeneratedLabel(firstLine.slice(isMainHeading ? 2 : 3))
      const body = lines.slice(1).join('\n').trim()
      return <div className="document-block" key={index}>{isMainHeading ? <h2>{heading}</h2> : <h3>{heading}</h3>}{body && (/^record fields$/i.test(heading) ? renderRecordFields(body) : <p>{body.split('\n').map((line, lineIndex) => <span key={lineIndex}>{line}{lineIndex < body.split('\n').length - 1 && <br />}</span>)}</p>)}</div>
    }
    if (lines.every((line) => line.trim().startsWith('- '))) return <ul key={index}>{lines.map((line) => <li key={line}>{line.trim().slice(2)}</li>)}</ul>
    return <p key={index}>{lines.map((line, lineIndex) => <span key={lineIndex}>{line}{lineIndex < lines.length - 1 && <br />}</span>)}</p>
  })
}

function DocumentPage({ document, onBack, onSearch, onRelevant }: { document: any | null, onBack: () => void, onSearch: () => void, onRelevant: () => void }) {
  if (!document) {
    return <section className="new-page document-page"><button className="secondary-button document-back" onClick={onBack}>← Back to records</button><div className="document-loading"><FileText size={28} /><h1>Opening source document…</h1><p>Reading the selected place record from the local Qdrant Edge dataset.</p></div></section>
  }
  const metadata = document.metadata ?? {}
  const sections = Array.isArray(metadata.sections) ? metadata.sections : ['Summary', 'Field relevance', 'Source and provenance']
  return <section className="new-page document-page">
    <div className="document-toolbar"><button className="secondary-button document-back" onClick={onBack}>← Back to records</button><span className="search-runtime"><span className="live-dot" />SOURCE DOCUMENT · QDRANT EDGE</span></div>
    <div className="new-page-intro"><div><p className="eyebrow">INDEXED FIELD BRIEF · {document.kind}</p><h1>{document.title}</h1></div><span className="copy-protection"><ShieldCheck size={15} />ORIGINAL RECORD LOCKED</span></div>
    <div className="document-facts"><div><span>DATASET</span><strong>{document.source ?? document.section}</strong></div><div><span>FIELD AREA</span><strong>{metadata.region ?? 'Selected research area'}</strong></div><div><span>COORDINATE</span><strong>{metadata.latitude !== undefined && metadata.longitude !== undefined ? `${Number(metadata.latitude).toFixed(4)}, ${Number(metadata.longitude).toFixed(4)}` : 'Attached to source record'}</strong></div><div><span>DOCUMENT</span><strong>{metadata.document_index && metadata.document_total ? `${metadata.document_index} of ${metadata.document_total}` : 'Source-linked'}</strong></div></div>
    <div className="document-layout"><article className="document-content"><p className="eyebrow">DOCUMENT CONTENT</p><div className="document-rich-text">{renderDocumentText(document.text || metadata.document_heading || 'Field evidence brief')}</div>{documentFieldInterpretation(document) && <div className="document-interpretation"><p className="eyebrow">FIELD INTERPRETATION</p><p>{documentFieldInterpretation(document)}</p></div>}<div className="document-outline"><p className="eyebrow">DOCUMENT SECTIONS</p><div>{sections.map((section: string) => <span key={section}>{section}</span>)}</div></div><div className="document-integrity"><ShieldCheck size={16} /><span>This source-linked record is read-only. Any observation you create will be saved as a separate copy.</span></div></article><aside className="document-actions"><div><p className="eyebrow">WHAT NEXT?</p><h2>Use this document</h2><p>Search for similar records or mark this source relevant to create a new field observation.</p></div><button className="secondary-button full" onClick={onSearch}><Search size={15} />Search related evidence</button><button className="primary-button full" onClick={onRelevant}><CheckCircle2 size={16} />Relevant · Create observation</button>{document.source_url && <a className="document-source-link" href={document.source_url} target="_blank" rel="noreferrer">Open source dataset <ArrowUpRight size={14} /></a>}</aside></div>
  </section>
}

function EvidenceSearchPage({ query, setQuery, onSearch, results: searchResults, answer, latency, origin, connection, regionLabel, onOpenResult }: { query: string, setQuery: (value: string) => void, onSearch: () => void, results: typeof results, answer: string, latency: number, origin: string, connection: Connection, regionLabel: string, onOpenResult: (value: any) => void }) {
  const terms = searchTerms(query)
  return <section className="new-page evidence-page">
    <div className="new-page-intro"><div><p className="eyebrow">EVIDENCE SEARCH · {regionLabel.toUpperCase()}</p><h1>Find the record behind the question.</h1></div><span className="search-runtime"><span className="live-dot" />{origin} · {connection === 'offline' ? 'OFFLINE SAFE' : 'CONNECTED'}</span></div>
    <section className="evidence-search-box"><Search size={20} /><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && onSearch()} aria-label="Search environmental evidence" placeholder="Type keywords: plants, animals, rivers, weather…" /><button className="primary-button" onClick={onSearch}>Search <ArrowUpRight size={15} /></button></section>
    <div className="evidence-layout"><section className="evidence-results"><div className="result-count"><span>{searchResults.length} matching documents</span><small>{latency} ms · ranked by semantic + keyword match</small></div>{searchResults.length === 0 && <div className="reader-empty"><Search size={25} /><h2>Search this region</h2><p>Enter a few keywords to find the closest source documents for {regionLabel}.</p></div>}{searchResults.map((result, index) => <button type="button" className="new-result-card" key={`${result.title}-${index}`} onClick={() => onOpenResult(result)}><div className="new-result-score">{Math.round(Number(result.score) * 100)}%</div><div><span>{result.kind} · {result.section}</span><h2>{highlight(result.title, terms)}</h2><p>{highlight(searchResultSummary(result.text), terms)}</p><small><ShieldCheck size={12} />{Math.round(Number(result.score) * 100)}% match</small></div><ChevronRight size={17} /></button>)}</section><aside className="document-reader"><div className="reader-empty"><FileText size={30} /><h2>Open a matching document</h2><p>Click any result to open its complete source text, headings, fields, and provenance. The original record stays locked while you decide whether it is relevant.</p></div></aside></div>
  </section>
}

function ObservationPage({ connection, locations, locationId, setLocationId, category, setCategory, query, selectedEvidence, note, setNote, evidence, setEvidence, refined, refining, reasoningStatus, onRefine, images, onImages, onSave, saved, status, uploadStatus, onUpload }: { connection: Connection, locations: FieldLocation[], locationId: string, setLocationId: (value: string) => void, category: string, setCategory: (value: string) => void, query: string, selectedEvidence: any | null, note: string, setNote: (value: string) => void, evidence: string, setEvidence: (value: string) => void, refined: { title: string, summary: string, engine?: string, model_status?: string, used_model?: boolean } | null, refining: boolean, reasoningStatus: string, onRefine: () => void, images: File[], onImages: (files: FileList | null) => void, onSave: () => void, saved: any | null, status: string, uploadStatus: string, onUpload: () => void }) {
  const location = locations.find((item) => item.id === locationId) ?? locations[0]
  const refinerReady = connection === 'online' && /(gemini|gemma)/i.test(reasoningStatus) && !/unavailable|not loaded|not cached|not configured/i.test(reasoningStatus)
  const refinedLabel = refined?.used_model ? 'GEMMA 4 REFINED COPY' : 'LOCAL 80–100 WORD EVIDENCE REFINEMENT'
  return (
    <section className="new-page observation-page">
      <div className="new-page-intro"><div><p className="eyebrow">OBSERVATION · NEW RECORD</p><h1>Turn evidence into a field note.</h1><p className="lede">This page creates a copy. The selected source record is never edited; your observation becomes its own new Qdrant point.</p></div><span className="copy-protection"><ShieldCheck size={15} />SOURCE RECORD LOCKED</span></div>
      <div className="observation-new-layout">
        <section className="observation-new-form">
          <div className="new-form-section"><label>Location &amp; context</label><select value={locationId} onChange={(event) => setLocationId(event.target.value)}>{locations.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.region}</option>)}</select></div>
          <div className="new-form-section"><label>Observed parameter &amp; category</label><select value={category} onChange={(event) => setCategory(event.target.value)}><option>Plants &amp; vegetation</option><option>Animals &amp; biodiversity</option><option>River &amp; water</option><option>Weather &amp; climate</option><option>Trail &amp; terrain</option><option>Other field evidence</option></select></div>
          <div className="new-form-section"><label>Words used during search</label><div className="locked-field"><Search size={15} />{query || 'No search phrase selected yet'}</div></div>
          <div className="new-form-section"><label htmlFor="new-observation">Observation</label><textarea id="new-observation" value={note} onChange={(event) => setNote(event.target.value)} rows={6} placeholder="Write what you saw, measured, or heard…" /></div>
          <div className="new-form-section"><label htmlFor="qualitative-evidence">Qualitative evidence</label><textarea id="qualitative-evidence" value={evidence} onChange={(event) => setEvidence(event.target.value)} rows={5} placeholder="Add small words or a detailed description of the surrounding evidence…" /><button className="secondary-button refine-button" onClick={onRefine} disabled={refining || (!note.trim() && !evidence.trim())}><WandSparkles size={16} />{refining ? 'Refining…' : 'Refine with Gemma 4'}</button>{refined && <div className="refined-card"><span>{refinedLabel}</span><h3>{refined.title}</h3><p>{refined.summary}</p>{refined.model_status && <small className="refined-status">{refined.model_status}</small>}</div>}</div>
          <div className="new-form-section"><label>Images · works online or offline</label><label className="upload-drop"><Upload size={18} /><span><strong>Upload field images</strong></span><input type="file" accept="image/*" multiple onChange={(event) => onImages(event.target.files)} /></label>{images.length > 0 && <div className="image-file-list">{images.map((image) => <span key={`${image.name}-${image.size}`}><FileImage size={14} />{image.name}</span>)}</div>}</div>
        </section>
        <aside className="observation-new-side">
          <div className="source-card"><div className="reader-kicker"><BookOpen size={15} />SELECTED REPORT SUMMARY</div>{selectedEvidence ? <><h2>{selectedEvidence.title}</h2><p>{sourceReportSummary(selectedEvidence.text)}</p><small>Summary taken from the original report · source remains unchanged</small></> : <><h2>No source selected</h2><p>You can still write a standalone field observation, or go back to Evidence Search and mark a record relevant.</p></>}</div>
          <div className="save-card"><div><span className="eyebrow">SAVE AS A COPY</span><h2>Commit new observation</h2><p>{status}</p></div><button className="primary-button full" onClick={onSave} disabled={(!note.trim() && !evidence.trim()) || Boolean(saved)}><CheckCircle2 size={16} />{saved ? 'Saved as new record' : 'Save new record'}</button>{saved && <><div className="saved-record"><strong>{saved.title}</strong><span>New ID · {saved.id}</span><small>Source remains immutable · image attachments retained locally</small></div><button className="qdrant-button full" onClick={onUpload}><Cloud size={16} />Upload new record to Qdrant</button>{uploadStatus && <div className="upload-status"><Cloud size={14} />{uploadStatus}</div>}</>}</div>
        </aside>
      </div>
    </section>
  )
}

function Overview({ connection, pendingCount, setView, onNewNote, onSearchArea, localVectors }: { connection: Connection, pendingCount: number, setView: (view: View) => void, onNewNote: () => void, onSearchArea: (area: SearchArea) => void, localVectors: number }) {
  const [areaSelection, setAreaSelection] = useState({ x: 31, y: 35, radiusKm: 8 })
  const [locationStatus, setLocationStatus] = useState('RZ3-ALPHA · USGS REF')

  function handleMapSelect(event: MouseEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest('button')) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = Math.min(88, Math.max(12, ((event.clientX - rect.left) / rect.width) * 100))
    const y = Math.min(82, Math.max(18, ((event.clientY - rect.top) / rect.height) * 100))
    setAreaSelection((current) => ({ ...current, x, y }))
    setLocationStatus('MAP PIN SELECTED · READY TO SEARCH')
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setLocationStatus('LOCATION UNAVAILABLE · SELECT ON MAP')
      return
    }
    setLocationStatus('LOCATING DEVICE…')
    navigator.geolocation.getCurrentPosition((position) => {
      setAreaSelection((current) => ({ ...current, x: 31, y: 35 }))
      setLocationStatus(`YOU ARE HERE · ${position.coords.latitude.toFixed(3)}, ${position.coords.longitude.toFixed(3)}`)
    }, () => setLocationStatus('LOCATION BLOCKED · SELECT ON MAP'))
  }

  function searchSelectedArea() {
    const latitude = 45.46 - (areaSelection.y / 100) * 0.28
    const longitude = -122.96 + (areaSelection.x / 100) * 0.3
    const latDelta = areaSelection.radiusKm / 111
    const lngDelta = areaSelection.radiusKm / (111 * Math.cos(latitude * Math.PI / 180))
    onSearchArea({ center: { lat: latitude, lng: longitude }, north: latitude + latDelta, south: latitude - latDelta, east: longitude + lngDelta, west: longitude - lngDelta, radiusKm: areaSelection.radiusKm })
  }

  return <section className="mission-overview">
    <div className="mission-strip">
      <div className="mission-strip-brand"><BrandMark /></div>
      <div className="mission-strip-status"><span className="status-dot" />{connection === 'online' ? 'CONNECTED' : 'OFFLINE'} <b>·</b> QDRANT EDGE ACTIVE</div>
      <div className="mission-strip-metrics"><span>SQLITE CACHE <b>94% FREE</b></span><span>NODE <b>STATION-03</b></span><span>BATTERY <b className="green-text">88%</b></span></div>
    </div>
    <div className="protocol-band"><span className="protocol-chip"><Database size={14} />EMBEDDED QDRANT ENGINE</span><p><strong>Offline protocol engaged.</strong> FieldNote keeps research evidence searchable on-device when the cloud is unavailable.</p><span className="protocol-count"><b>{pendingCount || 0}</b> Pending sync</span><span className="protocol-time">LAST SYNC · 14 AUG 2026<br />06:30 UTC</span></div>
    <section className="stat-grid mission-stats">
      <Stat icon={Database} iconClass="violet" label="Local knowledge pack" value={String(localVectors)} suffix="records" detail="12 reports · 96 observations" />
      <Stat icon={Network} iconClass="violet" label="Edge vector index" value="4ms" suffix="latency" detail="384-dim HNSW · local shard" />
      <Stat icon={Gauge} iconClass="orange" label="Storage health" value="412" suffix="MB / 8GB" detail="NVMe local partition intact" />
      <Stat icon={ArrowUpRight} iconClass="orange" label="Sync state" value={pendingCount ? String(pendingCount) : '0'} suffix="queue items" detail={pendingCount ? 'Waiting for gateway link' : 'Queue is clear'} />
    </section>
    <div className="overview-evidence-grid">
      <section className="panel telemetry-card"><div className="panel-heading"><div><p className="eyebrow">TOPOGRAPHIC VECTOR RETICLE</p><h2>River Zone 3 · live transect</h2></div><span className="green-outline"><span className="radar-dot" />LIVE RADAR</span></div><div className="telemetry-map map-selector" onClick={handleMapSelect} role="application" aria-label="Select a search area on the River Zone 3 map"><img className="telemetry-image" src="/topographic-vector-map.png" alt="Topographic map of River Zone 3" /><div className="map-scanline" /><div className="selected-area" style={{ left: `${areaSelection.x}%`, top: `${areaSelection.y}%`, width: `${areaSelection.radiusKm}%`, height: `${areaSelection.radiusKm}%` }}><span /><span /><span /><span /></div><span className="current-location-marker" style={{ left: '31%', top: '35%' }}><MapPin size={13} /></span><span className="vector-dot map-dot-alpha" /><span className="vector-dot map-dot-beta" /><span className="vector-dot map-dot-cluster" /><span className="map-label label-alpha">RZ3-ALPHA <small>USGS REF</small><b>Sim Vector Score&nbsp;&nbsp;1.000</b></span><span className="map-label label-beta">RZ3-BETA <small>RUNOFF · COSINE 0.942</small><b>Nearest Cluster&nbsp;&nbsp;Effluent-2024</b></span><span className="map-cross cross-one" /><span className="map-cross cross-two" /><div className="map-readout">DIM: 384 · DISTANCE: COSINE · HNSW ef=128</div><button className="map-location-button" onClick={useCurrentLocation}><LocateFixed size={14} />Use my location</button></div><div className="map-selection-bar"><div><span className="selection-kicker"><Crosshair size={13} />SEARCH AREA</span><strong>{locationStatus}</strong><small>Click the map to move the area · {areaSelection.radiusKm} km radius</small></div><div className="selection-actions"><button className="secondary-button compact" onClick={() => setAreaSelection((current) => ({ ...current, radiusKm: Math.max(4, current.radiusKm - 2) }))}>−</button><button className="secondary-button compact" onClick={() => setAreaSelection((current) => ({ ...current, radiusKm: Math.min(16, current.radiusKm + 2) }))}>+ radius</button><button className="qdrant-button compact" onClick={searchSelectedArea}><Cloud size={15} />Search Qdrant Cloud</button></div></div><div className="telemetry-metrics"><span><small>ELEVATION</small><b>342 m</b></span><span><small>DISCHARGE FLOW</small><b className="violet-text">6.8 m³/s</b></span><span><small>WATER TEMP</small><b>14.1°C</b></span><span><small>PH</small><b className="amber-text">7.42 · NOM</b></span></div></section>
      <section className="panel research-pack"><div className="panel-heading"><div><p className="eyebrow">VERIFIED RESEARCH PACK</p><h2>Reference evidence</h2></div><span className="green-outline"><ShieldCheck size={13} />88 RECORDS</span></div><p className="pack-note">Read-only baseline indexed on this device for low-latency field decisions.</p>{records.slice(0, 3).map((record, index) => <article className="pack-row" key={record.id}><div className={`pack-icon ${index === 0 ? 'green' : index === 1 ? 'violet' : 'coral'}`}><FileText size={17} /></div><div><div className="pack-row-top"><span>{index === 0 ? 'REGULATORY STANDARD' : index === 1 ? 'HISTORIC TRANSECT' : 'SOP RUNBOOK'}</span><b>{index === 0 ? 'PEER-REVIEWED' : index === 1 ? 'ARCHIVE LOCKED' : 'METHOD 1664-B'}</b></div><h3>{record.title}</h3><p>{record.section}. Vector dimension: 384 · citation retained.</p></div></article>)}</section>
    </div>
    <div className="overview-lower-grid">
      <section className="panel mission-log"><div className="panel-heading"><div><p className="eyebrow">DEVICE MISSION LOG</p><h2>What happened today</h2></div><span className="eyebrow">AUDIT TRAIL // UTC</span></div><div className="mission-timeline">{activities.map(({ title, detail, icon: Icon, type }, index) => <div className="mission-event" key={title}><span className={`event-node ${type}`}><Icon size={13} /></span><div><b>{['14:22 UTC', '11:05 UTC', '06:30 UTC', '06:15 UTC'][index]}</b><h3>{title}</h3><p>{detail}</p></div><span className="event-tag">{index === 0 ? 'QUEUE PENDING' : index === 1 ? 'HARDWARE' : index === 2 ? 'CONFIRMED' : 'CALIBRATION'}</span></div>)}</div></section>
      <section className="panel local-memory-card"><div className="panel-heading"><div><p className="eyebrow">LOCAL FIELD MEMORY</p><h2>Capture stays local.</h2></div><span className="coral-outline"><Database size={13} />WRITE-READ</span></div><p>New observations are indexed immediately, then governed by your sharing policy.</p><div className="local-memory-note"><span className="state-pill pending">NEEDS VERIFICATION</span><h3>East Bank odour &amp; silt drift observation</h3><small>Pending local check · vectorized locally · ready to search</small></div><div className="local-memory-actions"><button className="qdrant-button" onClick={onNewNote}><Plus size={16} />Compose observation</button><button className="secondary-button" onClick={() => setView('search')}><Search size={16} />Query local index</button></div></section>
    </div>
    <div className="direct-actions"><span><strong>DIRECT RESEARCHER ACTIONS</strong><small>Switch modules or trigger immediate local vector retrieval</small></span><button onClick={() => setView('search')}><Search size={15} />Query local index</button><button onClick={onNewNote}><Plus size={15} />Compose field observation</button><button onClick={() => setView('sync')}><RefreshCw size={15} />Open sync center</button></div>
    <div className="overview-foot"><span>DEVICE ID: RUGGED-TOUGHBOOK-WZ03</span><span>QDRANT EDGE · EMBEDDED C-API</span><span className="green-text">LOCAL DATASTORE INTEGRITY OK</span></div>
  </section>
}

function Stat({ icon: Icon, iconClass, label, value, suffix, detail, status }: { icon: typeof Database, iconClass: string, label: string, value: string, suffix?: string, detail: string, status?: Connection }) {
  return <div className="stat-card"><div className={`stat-icon ${iconClass}`}><Icon size={19} /></div><p>{label}</p><div className="stat-value">{value}{suffix && <span>{suffix}</span>}</div><small className={status ? `connection-detail ${status}` : ''}>{status && <i />}{detail}</small></div>
}

function KnowledgeSearch({ query, setQuery, hasSearched, onSearch, filters, setFilters, connection, results: searchResults, answer, latency, origin }: { query: string, setQuery: (value: string) => void, hasSearched: boolean, onSearch: () => void, filters: { asset: boolean, site: boolean, document: boolean }, setFilters: (value: { asset: boolean, site: boolean, document: boolean }) => void, connection: Connection, results: typeof results, answer: string, latency: number, origin: string }) {
  const toggle = (key: keyof typeof filters) => setFilters({ ...filters, [key]: !filters[key] })
  const localBrief = answer || 'Low dissolved oxygen and elevated turbidity were reported in River Zone 3 after rainfall. Compare the upstream reference, verify calibration, and keep new observations local until confirmed.'
  return <>
    <section className="search-head"><div><p className="eyebrow">QDRANT EDGE · EVIDENCE SEARCH</p><h1>Search local evidence</h1><p className="lede">Ask the device. Get cited matches from the local vector index, even when the network is gone.</p></div><span className="search-runtime"><span className="live-dot" />LOCAL INFERENCE · {connection === 'online' ? 'CONNECTED' : 'OFFLINE'}</span></section>
    <section className="search-workspace"><div className="query-box"><Search size={21} /><input aria-label="Search field knowledge" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && onSearch()} /><kbd><Command size={12} />K</kbd><button className="primary-button" onClick={onSearch}>Search <ArrowUpRight size={15} /></button></div><div className="filter-row"><span><Filter size={15} />Narrow results</span><button className={`filter-chip ${filters.site ? 'active' : ''}`} onClick={() => toggle('site')}>River Zone 3 <ChevronDown size={14} /></button><button className={`filter-chip ${filters.document ? 'active' : ''}`} onClick={() => toggle('document')}>All evidence <ChevronDown size={14} /></button><button className="clear-filters" onClick={() => setFilters({ asset: false, site: false, document: false })}>Clear</button></div></section>
    {hasSearched && <section className="search-results"><div className="result-meta"><span><strong>{searchResults.length} MATCHES FOUND</strong> · sorted by cosine distance</span><span className="origin-badge"><span className="mini-pulse" />{origin} · {latency} ms · 0 network requests</span></div><div className="result-list">{searchResults.map((result, index) => <article className="result-card" key={`${result.title}-${index}`}><div className="result-score"><strong>{Math.round(Number(result.score) * 100)}%</strong><span>{result.score} cosine</span></div><div className="result-body"><div className="result-topline"><span>{result.kind}</span><i />{result.section}</div><h2>{result.title}</h2><p>{highlight(result.text, result.highlights)}</p><div className="result-citation"><span><ShieldCheck size={13} />VERIFIED LOCAL RECORD</span><small>Storage: SQLite / Qdrant Edge shard</small></div><div className="result-actions"><button>Inspect vectors <ArrowUpRight size={15} /></button><button><Copy size={14} />Pin citation</button></div></div><div className="rank">0{index + 1}</div></article>)}</div><aside className="synthesis-panel"><div className="panel-heading"><div><p className="eyebrow">SYNTHESIS &amp; EVIDENCE CHAIN</p><h2>Local inference</h2></div><span className="green-outline">CITED</span></div><div className="reasoning-graph"><p className="graph-label">REASONING GRAPH ARCHITECTURE</p><div className="graph-step"><b>1</b><span>User question</span></div><i /><div className="graph-step active"><b>2</b><span>{searchResults.length} retrieved records · cosine &gt; 0.75</span></div><i /><div className="graph-step warn"><b>3</b><span>1 local field observation · unverified</span></div><i /><div className="graph-step final"><b>4</b><span>Synthesized cited field hypothesis</span></div></div><div className="cited-brief"><div className="answer-label"><Zap size={15} />CITED DETERMINISTIC SYNTHESIS <span>Temp: 0.0 · Local model</span></div><p>{localBrief}</p><div className="brief-note"><strong>NOTE</strong> · New local observations remain quarantined until a duplicate sample or reviewer confirms them.</div></div><button className="qdrant-button full"><ArrowUpRight size={16} />Export evidence dossier</button><div className="synthesis-actions"><button className="secondary-button">Add to mission log</button><button className="secondary-button">Pin citations</button></div><div className="vector-footprint"><div><span>EMBEDDING VRAM FOOTPRINT</span><b>142 MB / 4096 MB</b></div><div className="footprint-bar"><i /></div><small>Cosine precision: FP16 · SIMD Neon: enabled</small></div></aside></section>}
  </>
}

function searchTerms(query: string) {
  const ignored = new Set(['about', 'again', 'been', 'from', 'near', 'that', 'this', 'what', 'with', 'which', 'where'])
  return Array.from(new Set(query.toLowerCase().split(/[^a-z0-9]+/).filter((term) => term.length > 2 && !ignored.has(term))))
}

function searchResultSummary(text: string) {
  const summary = sourceReportSummary(text)
  const compact = summary
    .replace(/\s+/g, ' ')
    .replace(/\b(?:Source|Original response|Dataset provenance)\s*:\s*https?:\/\/\S+/gi, '')
    .trim()
  return compact.length > 300 ? `${compact.slice(0, 300).trimEnd()}…` : compact
}

function highlight(text: string, terms: string[]) {
  if (!text || terms.length === 0) return text
  const expression = new RegExp(`(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  return text.split(expression).map((part, index) => terms.some((term) => term.toLowerCase() === part.toLowerCase()) ? <mark key={index}>{part}</mark> : part)
}

function ObservationComposer({ note, setNote, policy, setPolicy, onSave, localVectors }: { note: string, setNote: (value: string) => void, policy: 'needs-verification' | 'ready-to-sync', setPolicy: (value: 'needs-verification' | 'ready-to-sync') => void, onSave: () => void, localVectors: number }) {
  return <><section className="split-head composer-head"><div><p className="eyebrow">LOCAL FIELD CAPTURE</p><h1>Observation composer</h1><p className="lede">Record what happened at River Zone 3. FieldNote indexes it locally first, then lets you decide what the team can receive.</p></div><span className="composer-ref">OBS · RZ3 · {new Date().toISOString().slice(0, 10)}</span></section><div className="composer-banner"><span className="status-dot offline" /><div><strong>Recording on this device</strong><span>Qdrant Edge will make this observation searchable immediately. No cloud request is required.</span></div><span className="banner-tag">LOCAL FIRST</span></div><div className="composer-layout"><section className="panel observation-form"><div className="panel-heading"><div><p className="eyebrow">01 · FIELD OBSERVATION</p><h2>What did you find?</h2></div><span className="form-state">DRAFT</span></div><label>Location & context</label><div className="field-value"><CircleDot size={16} /><span>River Zone 3 · Clearwater 2026</span><ChevronDown size={15} /></div><label>Observed parameter category</label><div className="field-value"><span className="category-dot" />Turbidity & dissolved oxygen <ChevronDown size={15} /></div><label htmlFor="composer-note">Observation note & qualitative evidence</label><textarea id="composer-note" value={note} onChange={(event) => setNote(event.target.value)} rows={8} placeholder="Describe the reading, conditions, instrument, and what should be verified..." /><div className="field-hint"><span>Preserve the original measurement and context.</span><span>{note.length} characters</span></div><div className="artifact-card"><div className="artifact-icon"><FileText size={19} /></div><div><strong>Source context attached</strong><span>River Zone 3 baseline pack · calibration protocol</span></div><span className="verified-tag">PACKED</span></div></section><section className="panel policy-panel"><div className="panel-heading"><div><p className="eyebrow">02 · DATA GOVERNANCE</p><h2>Choose a sharing policy</h2></div><span className="form-state">REQUIRED</span></div><button className={`policy-option ${policy === 'needs-verification' ? 'selected' : ''}`} onClick={() => setPolicy('needs-verification')}><span className="policy-check">{policy === 'needs-verification' ? <Check size={14} /> : null}</span><span><strong>Needs verification</strong><small>Visible locally, not shared</small><em>Keep the note in the Edge shard until a duplicate sample or reviewer confirms it.</em></span><b>QUARANTINE</b></button><button className={`policy-option ${policy === 'ready-to-sync' ? 'selected ready' : ''}`} onClick={() => setPolicy('ready-to-sync')}><span className="policy-check">{policy === 'ready-to-sync' ? <Check size={14} /> : null}</span><span><strong>Ready to sync</strong><small>Approve for team knowledge</small><em>Queue this finding for central Qdrant when connectivity returns.</em></span><b>OUTBOX</b></button><div className="commit-card"><div><p className="eyebrow">03 · INDEX & COMMIT</p><h3>Qdrant Edge action</h3><p>One click creates the vector point and preserves this policy in SQLite.</p></div><button className="qdrant-button full" onClick={onSave}><Zap size={17} />Save & index locally <ArrowUpRight size={16} /></button><div className="commit-status"><Check size={15} /><span>Ready to index · {localVectors} vectors currently on device</span></div></div></section></div><section className="composer-footer"><span>WATER TEMP <strong>14.1°C</strong></span><span>TURBIDITY <strong className="accent-amber">24.2 NTU</strong></span><span>DO SATURATION <strong className="accent-green">92.4%</strong></span><span>PRIVACY <strong>DEVICE FIRST</strong></span></section></>
}

function MemoryInspector({ localVectors, note, setNote, policy, setPolicy, onSave }: { localVectors: number, note: string, setNote: (value: string) => void, policy: 'needs-verification' | 'ready-to-sync', setPolicy: (value: 'needs-verification' | 'ready-to-sync') => void, onSave: () => void }) {
  return <ObservationComposer note={note} setNote={setNote} policy={policy} setPolicy={setPolicy} onSave={onSave} localVectors={localVectors} />
}

function SyncCenter({ connection, pendingCount, syncing, onSync, conflictCount, onResolveConflict }: { connection: Connection, pendingCount: number, syncing: boolean, onSync: () => void, conflictCount: number, onResolveConflict: (choice: 'local' | 'remote' | 'merged') => void }) {
  const synced = pendingCount === 0
  return <>
    <section className="split-head sync-head"><div><p className="eyebrow">DEVICE ↔ CENTRAL QDRANT</p><h1>Sync &amp; conflict center</h1><p className="lede">Reconnect deliberately. Review every difference before it reaches shared knowledge.</p></div><button className="primary-button" disabled={connection === 'offline' || syncing || synced} onClick={onSync}>{syncing ? <RefreshCw className="spin" size={17} /> : <RefreshCw size={17} />}{syncing ? 'Syncing…' : synced ? 'Queue clear' : 'Reconnect & sync'}</button></section>
    <div className={`sync-banner ${connection}`}><div className="sync-banner-icon"><Cloud size={20} /></div><div><strong>{connection === 'online' ? 'Connection restored — central Qdrant reachable' : 'Offline mission assurance — device is isolated'}</strong><span>{connection === 'online' ? 'Approved findings can now be delivered through the secure delta handshake.' : 'Cloud traffic is blocked. Local evidence remains searchable and every change is queued.'}</span></div><span className={`status-label ${connection}`}>{connection === 'online' ? 'ONLINE' : 'OFFLINE'}</span></div>
    <div className="sync-center-layout"><aside className="sync-sidebar-stack"><section className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">OFFLINE SYNC QUEUE</p><h2>{pendingCount ? '1 staged update' : 'Queue is clear'}</h2></div><span className={`queue-count ${pendingCount ? '' : 'done'}`}>{pendingCount || <Check size={15} />}</span></div><div className="queue-event"><div className={`queue-icon ${pendingCount ? 'waiting' : 'complete'}`}>{pendingCount ? <ArrowUpRight size={18} /> : <Check size={18} />}</div><div><div className="queue-title"><strong>Field note · River Zone 3</strong><span className={`state-pill ${pendingCount ? 'pending' : 'synced'}`}>{pendingCount ? 'READY TO SYNC' : 'SYNCED'}</span></div><p>{pendingCount ? 'Created locally · policy-controlled delivery' : 'Central acknowledgement is current'}</p><small>{pendingCount ? 'UPSERT · 1 VECTOR POINT' : 'SQLITE OUTBOX · 0 ITEMS'}</small></div></div><div className="queue-note"><ShieldCheck size={17} /><span>Auto-push is engaged when a secure connection is available.</span></div><button className="secondary-button full" disabled={connection === 'offline' || !pendingCount} onClick={onSync}><RefreshCw size={15} />Flush queue now</button></section><section className="panel spatial-context"><div className="panel-heading"><div><p className="eyebrow">SPATIAL DEPLOYMENT CONTEXT</p><h2>River Zone 3</h2></div><span className="violet-text">RZ3 MONITOR</span></div><div className="context-grid"><span><small>MONITORING ZONE</small><b>East Bank Transect 3</b></span><span><small>FIELD SENSOR NODE</small><b>RZ3-ALPHA · Station A</b></span><span><small>WATER TEMPERATURE</small><b className="green-text">14.1°C · Nominal</b></span><span><small>RIVER VELOCITY</small><b className="coral-text">1.8 m/s · Downstream</b></span></div></section></aside><section className={`panel conflict-panel conflict-center ${conflictCount ? 'has-conflict' : 'resolved'}`}><div className="conflict-title"><div><p className="eyebrow">CONFLICT DETECTED · RECORD #RZ3-EVD-104</p><h2>{conflictCount ? 'Sampling site east bank needs reconciliation' : 'All evidence reconciled'}</h2><p>{conflictCount ? 'Central Lab and this field terminal recorded different evidence for the same observation.' : 'No unresolved local-versus-shared evidence remains on this device.'}</p></div><span className="coral-outline">{conflictCount ? 'RECONCILIATION REQUIRED' : 'CLEAR'}</span></div>{conflictCount ? <><div className="conflict-compare"><article className="evidence-side cloud-side"><div className="evidence-side-head"><span>CLOUD EVIDENCE · REMOTE MASTER</span><b>VERIFIED LAB ASSAY</b></div><h3>Central Hydro-Lab Analytics</h3><small>Modified 14 Aug · 13:45 UTC by Dr. S. Chen</small><p>“High turbidity verified after laboratory review. Suspended organic sediment confirmed; no toxic synthetic hydrocarbons identified.”</p><div className="evidence-facts"><span>SEDIMENT TYPE <b>Organic clay silt</b></span><span>HYDROCARBON INDEX <b>&lt; 0.02 ppm</b></span></div><footer>Analytical confidence <strong className="green-text">99.1%</strong></footer></article><article className="evidence-side local-side"><div className="evidence-side-head"><span>LOCAL EVIDENCE · THIS DEVICE</span><b>AMBER · PENDING LAB CONFIRMATION</b></div><h3>Field Terminal · Unit 03</h3><small>Recorded 14 Aug · 14:22 UTC by researcher on site</small><p>“Chemical odour observed near east bank with surface sheen. Requires laboratory verification for volatile organics.”</p><div className="evidence-facts"><span>SENSOR PROFILE <b>Petroleum / sulfide odour</b></span><span>VISUAL SURFACE FILM <b>Iridescent micro-sheen</b></span></div><footer>Sensor confidence <strong className="amber-text">88.7% local</strong></footer></article></div><div className="reconcile-actions"><span>Select reconciliation protocol</span><button className="secondary-button" onClick={() => onResolveConflict('local')}>Keep local evidence</button><button className="secondary-button" onClick={() => onResolveConflict('remote')}>Keep cloud evidence</button><button className="primary-button" onClick={() => onResolveConflict('merged')}>Merge evidence · recommended</button></div><div className="recommendation"><ShieldCheck size={15} />Recommended: retain the lab assay as the primary finding and attach the on-site odour as a local supplementary observation.</div></> : <div className="resolved-message"><Check size={23} /><p>Conflict decision recorded. The merged evidence is now ready for the next sync handshake.</p></div>}</section></div>
    <section className="panel timeline-panel"><div className="panel-heading"><div><p className="eyebrow">SYNC EVENT HISTORY TIMELINE</p><h2>Session activity</h2></div><span className="eyebrow">SESSION · #SYNC-2026-RZ3-08</span></div><div className="sync-timeline"><div><i className="green-dot" /><b>15:02:11 UTC</b><span>Handshake with Central Cloud successful</span><em>UPLINK OK</em></div><div><i className="coral-dot" /><b>15:02:18 UTC</b><span>Conflict identified in Record #RZ3-EVD-104</span><em>DELTA DETECTED</em></div><div><i className="violet-dot" /><b>15:03:00 UTC</b><span>Merge simulated: Ready to commit</span><em>DRY RUN PASSED</em></div><div><i className="green-dot" /><b>15:03:45 UTC</b><span>Synced to team knowledge</span><em>COMMITTED</em></div></div></section>
    <section className="sync-flow"><div><span>01</span><strong>Index locally</strong><small>Qdrant Edge</small></div><ChevronRight size={19} /><div><span>02</span><strong>Choose policy</strong><small>SQLite outbox</small></div><ChevronRight size={19} /><div><span>03</span><strong>Deliver on signal</strong><small>Central Qdrant</small></div><ChevronRight size={19} /><div><span>04</span><strong>Acknowledge</strong><small>Mark as synced</small></div></section>
  </>
}

function NewNoteModal({ note, setNote, policy, setPolicy, onClose, onSave }: { note: string, setNote: (value: string) => void, policy: 'needs-verification' | 'ready-to-sync', setPolicy: (value: 'needs-verification' | 'ready-to-sync') => void, onClose: () => void, onSave: () => void }) {
  return <div className="modal-layer" role="dialog" aria-modal="true" aria-labelledby="new-note-title"><div className="modal"><div className="modal-head"><div><p className="eyebrow">LOCAL FIELD CAPTURE</p><h2 id="new-note-title">Add field observation</h2></div><button className="icon-button" onClick={onClose}><X size={19} /></button></div><div className="note-context"><span><CircleDot size={16} />River Zone 3</span><span>Clearwater 2026</span><span>Saved to this device first</span></div><label htmlFor="note-content">What did you find?</label><textarea id="note-content" value={note} onChange={(event) => setNote(event.target.value)} rows={5} /><label htmlFor="note-policy">Sharing policy</label><select id="note-policy" className="note-policy" value={policy} onChange={(event) => setPolicy(event.target.value as 'needs-verification' | 'ready-to-sync')}><option value="needs-verification">Needs verification · keep local</option><option value="ready-to-sync">Ready to sync · approve for team</option></select><div className="modal-foot"><p><Database size={16} />Indexed in Qdrant Edge immediately. You choose what leaves this device.</p><div><button className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" onClick={onSave}>Save locally <ArrowUpRight size={16} /></button></div></div></div></div>
}

export default App
