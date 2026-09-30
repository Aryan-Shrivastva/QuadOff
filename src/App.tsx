import { useEffect, useState, type MouseEvent } from 'react'
import {
  ArrowDownToLine,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Cloud,
  Command,
  Copy,
  Crosshair,
  Database,
  FileText,
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
  X,
  Zap,
} from 'lucide-react'

type View = 'overview' | 'search' | 'memory' | 'sync'
type Connection = 'online' | 'offline'
type GeoPoint = { lat: number, lng: number }
type SearchArea = { center: GeoPoint, north: number, south: number, east: number, west: number, radiusKm: number }
const API = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

const nav = [
  { id: 'overview' as View, label: 'Device overview', icon: LayoutDashboard },
  { id: 'search' as View, label: 'Evidence search', icon: Search },
  { id: 'memory' as View, label: 'Observation composer', icon: FileText },
  { id: 'sync' as View, label: 'Sync & conflict center', icon: RefreshCw },
]

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
  const [view, setView] = useState<View>('overview')
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
  const [conflictCount, setConflictCount] = useState(1)

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
      })
      .catch(() => undefined)
  }, [])

  function selectView(next: View) {
    setView(next)
    setMobileOpen(false)
  }

  function toggleConnectivity() {
    const next = connection === 'online' ? 'offline' : 'online'
    setConnection(next)
    fetch(`${API}/api/connectivity`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ online: next === 'online' }) }).catch(() => undefined)
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
    fetch(`${API}/api/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, site_id: filters.site ? 'river-zone-3' : undefined, limit: 6 }) })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('search failed')))
      .then((payload) => {
        const mapped = payload.matches.map((match: { score: number, title: string, kind: string, text: string, citation: string }) => ({ score: match.score.toFixed(2), title: match.title, section: match.citation, kind: match.kind.replace('_', ' ').toUpperCase(), text: match.text, highlights: ['dissolved oxygen', 'turbidity', 'calibration', 'duplicate'] }))
        setSearchMatches(mapped)
        setSearchAnswer(payload.answer?.summary ?? '')
        setSearchLatency(payload.retrieval?.latency_ms ?? 43)
        setSearchOrigin(payload.retrieval?.origin ?? 'Qdrant Edge')
      })
      .catch(() => undefined)
  }

  function runAreaSearch(area: SearchArea) {
    const areaQuery = `Environmental evidence near ${area.center.lat.toFixed(3)}, ${area.center.lng.toFixed(3)}`
    setQuery(areaQuery)
    setView('search')
    setHasSearched(false)
    fetch(`${API}/api/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: areaQuery, site_id: 'river-zone-3', limit: 6, source: 'cloud', area }) })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('area search failed')))
      .then((payload) => {
        const mapped = payload.matches.map((match: { score: number, title: string, kind: string, text: string, citation: string }) => ({ score: match.score.toFixed(2), title: match.title, section: match.citation, kind: match.kind.replace('_', ' ').toUpperCase(), text: match.text, highlights: ['dissolved oxygen', 'turbidity', 'calibration', 'duplicate'] }))
        setSearchMatches(mapped)
        setSearchAnswer(payload.answer?.summary ?? '')
        setSearchLatency(payload.retrieval?.latency_ms ?? 43)
        setSearchOrigin(payload.retrieval?.origin ?? 'Central demo · Edge fallback')
        setHasSearched(true)
      })
      .catch(() => setHasSearched(true))
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
            return <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => selectView(item.id)}><Icon size={18} strokeWidth={1.8} /><span>{item.label}</span>{item.id === 'sync' && pendingCount > 0 && <b>{pendingCount}</b>}</button>
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
          <div className="page-context"><button className="icon-button menu-mobile" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="brand-inline"><BrandMark /><small>RIVER ZONE 3 FIELD MISSION</small></div></div>
          <div className="top-actions">
            <div className="device-signals"><button className="icon-button" aria-label="Satellite status"><Network size={17} /></button><button className="icon-button" aria-label="Local vector store"><Database size={17} /></button><button className="icon-button" aria-label="Mesh radio"><Cloud size={17} /></button></div>
            <button className={`connection-button ${connection}`} onClick={toggleConnectivity}><span className="status-dot" />{connection === 'online' ? 'Connected' : 'Offline'}<ChevronDown size={14} /></button>
            <button className="secondary-button compact" aria-label="Calibrate device"><Settings size={16} />Calibrate</button>
            <button className="qdrant-button compact sync-lock" onClick={() => selectView('sync')}><ShieldCheck size={16} />Sync lock</button>
            <button className="secondary-button compact new-observation" onClick={() => selectView('memory')}><Plus size={17} />New observation</button>
            <span className="node-badge">H-03</span>
          </div>
        </header>
        <div className="module-nav" aria-label="FieldNote modules">
          {nav.map((item) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => selectView(item.id)}><Icon size={15} /><span>{item.label}</span>{item.id === 'sync' && (pendingCount > 0 || conflictCount > 0) && <b>{pendingCount + conflictCount}</b>}</button> })}
        </div>
        <div className="content">
          <div className="view-transition" key={view}>
          {view === 'overview' && <Overview connection={connection} pendingCount={pendingCount} setView={setView} onNewNote={() => selectView('memory')} onSearchArea={runAreaSearch} localVectors={localVectors} />}
            {view === 'search' && <KnowledgeSearch query={query} setQuery={setQuery} hasSearched={hasSearched} onSearch={runSearch} filters={filters} setFilters={setFilters} connection={connection} results={searchMatches} answer={searchAnswer} latency={searchLatency} origin={searchOrigin} />}
            {view === 'memory' && <MemoryInspector localVectors={localVectors} note={note} setNote={setNote} policy={notePolicy} setPolicy={setNotePolicy} onSave={createNote} />}
            {view === 'sync' && <SyncCenter connection={connection} pendingCount={pendingCount} syncing={syncing} onSync={runSync} conflictCount={conflictCount} onResolveConflict={resolveConflict} />}
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
      <div className="mission-strip-brand"><BrandMark /><div><span>RIVER ZONE 3 FIELD MISSION</span></div></div>
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

function highlight(text: string, terms: string[]) {
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
