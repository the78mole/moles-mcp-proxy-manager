<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

type SourceType = 'PYPI' | 'GITHUB' | 'LOCAL' | 'OPENAPI' | 'NPM'

type Server = {
  id: number
  name: string
  slug: string
  source_type: SourceType
  package_name?: string
  executable_name?: string
  git_url?: string
  local_path?: string
  backend_url?: string
  status: string
  internal_port?: number
  env_vars: Record<string, string>
  args: string[]
}

const servers = ref<Server[]>([])
const loadingById = reactive<Record<number, boolean>>({})
const copyFeedback = reactive<Record<number, boolean>>({})

// ── Backend-Status ────────────────────────────────────────────────────────────
const backendOnline = ref<boolean | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

async function checkBackend() {
  try {
    const res = await fetch('/api/v1/servers', { signal: AbortSignal.timeout(3000) })
    if (res.ok) {
      servers.value = await res.json()
      backendOnline.value = true
      return
    }
  } catch { /* intentional */ }
  backendOnline.value = false
}

// ── Server-Katalog ───────────────────────────────────────────────────────────
type CatalogEntry = {
  id: string
  name: string
  description: string
  source_type: SourceType
  package_name?: string
  executable_name?: string
  git_url?: string
  default_settings: { envs: Record<string, string>; args: string[] }
}

const CATALOG: CatalogEntry[] = [
  {
    id: 'bookstack',
    name: 'BookStack',
    description: 'MCP server for the BookStack documentation platform',
    source_type: 'NPM',
    package_name: 'bookstack-mcp',
    default_settings: { envs: { BOOKSTACK_BASE_URL: '', BOOKSTACK_TOKEN_ID: '', BOOKSTACK_TOKEN_SECRET: '' }, args: [] },
  },
  {
    id: 'time',
    name: 'Time',
    description: 'Current time and timezone conversion',
    source_type: 'PYPI',
    package_name: 'mcp-server-time',
    default_settings: { envs: {}, args: ['--local-timezone', 'Europe/Berlin'] },
  },
  {
    id: 'fetch',
    name: 'Fetch',
    description: 'Web content fetching and HTML-to-Markdown conversion',
    source_type: 'PYPI',
    package_name: 'mcp-server-fetch',
    default_settings: { envs: {}, args: [] },
  },
  {
    id: 'filesystem',
    name: 'Filesystem',
    description: 'File system read/write/list operations',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-filesystem',
    default_settings: { envs: {}, args: ['/tmp'] },
  },
  {
    id: 'github',
    name: 'GitHub',
    description: 'Repositories, issues, PRs and code search',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-github',
    default_settings: { envs: { GITHUB_PERSONAL_ACCESS_TOKEN: '' }, args: [] },
  },
  {
    id: 'gitlab',
    name: 'GitLab',
    description: 'GitLab projects, issues and merge requests',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-gitlab',
    default_settings: { envs: { GITLAB_PERSONAL_ACCESS_TOKEN: '', GITLAB_API_URL: 'https://gitlab.com' }, args: [] },
  },
  {
    id: 'brave-search',
    name: 'Brave Search',
    description: 'Web and local search via the Brave Search API',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-brave-search',
    default_settings: { envs: { BRAVE_API_KEY: '' }, args: [] },
  },
  {
    id: 'postgres',
    name: 'PostgreSQL',
    description: 'Read-only access to a PostgreSQL database',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-postgres',
    default_settings: { envs: {}, args: ['postgresql://localhost/mydb'] },
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Channels, messages and workspace management',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-slack',
    default_settings: { envs: { SLACK_BOT_TOKEN: '', SLACK_TEAM_ID: '' }, args: [] },
  },
  {
    id: 'memory',
    name: 'Memory',
    description: 'Knowledge-graph-based persistent memory store',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-memory',
    default_settings: { envs: {}, args: [] },
  },
  {
    id: 'sequential-thinking',
    name: 'Sequential Thinking',
    description: 'Dynamic problem-solving via sequential thoughts',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-sequential-thinking',
    default_settings: { envs: {}, args: [] },
  },
  {
    id: 'puppeteer',
    name: 'Puppeteer',
    description: 'Browser automation and web scraping',
    source_type: 'NPM',
    package_name: '@modelcontextprotocol/server-puppeteer',
    default_settings: { envs: {}, args: [] },
  },
]

const catalogOpen = ref(false)
const catalogFilter = ref('')

const filteredCatalog = computed(() => {
  const q = catalogFilter.value.trim().toLowerCase()
  if (!q) return CATALOG
  return CATALOG.filter(e =>
    e.name.toLowerCase().includes(q) ||
    e.description.toLowerCase().includes(q) ||
    (e.package_name ?? '').toLowerCase().includes(q),
  )
})

const SOURCE_TYPE_BADGE: Record<SourceType, string> = {
  PYPI:    'bg-blue-800 text-blue-200',
  NPM:     'bg-orange-800 text-orange-200',
  GITHUB:  'bg-purple-800 text-purple-200',
  LOCAL:   'bg-slate-600 text-slate-200',
  OPENAPI: 'bg-teal-800 text-teal-200',
}

function applyTemplate(entry: CatalogEntry) {
  form.name = entry.name
  form.slug = nameToSlug(entry.name)
  form.source_type = entry.source_type
  form.package_name = entry.package_name ?? ''
  form.executable_name = entry.executable_name ?? ''
  form.git_url = entry.git_url ?? ''
  form.local_path = ''
  form.backend_url = ''
  form.settings = JSON.stringify(entry.default_settings, null, 2)
  settingsError.value = ''
  catalogOpen.value = false
  catalogFilter.value = ''
  addServerOpen.value = true
}

// ── Add-Server-Modal ─────────────────────────────────────────────────────────
const addServerOpen = ref(false)

function openAddServer() {
  form.name = ''
  form.slug = ''
  form.source_type = 'PYPI'
  form.package_name = ''
  form.executable_name = ''
  form.git_url = ''
  form.local_path = ''
  form.backend_url = ''
  form.settings = DEFAULT_SETTINGS
  settingsError.value = ''
  catalogOpen.value = false
  catalogFilter.value = ''
  addServerOpen.value = true
}

// ── Add-Form ──────────────────────────────────────────────────────────────────
const DEFAULT_SETTINGS = JSON.stringify({ envs: {}, args: [] }, null, 2)

const form = reactive({
  name: '',
  slug: '',
  source_type: 'PYPI' as SourceType,
  package_name: '',
  executable_name: '',
  git_url: '',
  local_path: '',
  backend_url: '',
  settings: DEFAULT_SETTINGS,
})

const settingsError = ref('')

function nameToSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function onNameInput() {
  if (!form.slug || form.slug === nameToSlug(form.name.slice(0, -1))) {
    form.slug = nameToSlug(form.name)
  }
}

const requiresExecutable = computed(() => ['GITHUB', 'LOCAL'].includes(form.source_type))
const requiresPackageName = computed(() => ['PYPI', 'NPM'].includes(form.source_type))

const MANAGER_ORIGIN = globalThis.window?.location?.origin ?? 'http://localhost:8000'

function connectionUrl(server: Server): string {
  return `${MANAGER_ORIGIN}/v1/mcp/${server.slug}/openapi.json`
}

async function copyUrl(server: Server) {
  await globalThis.navigator.clipboard.writeText(connectionUrl(server))
  copyFeedback[server.id] = true
  setTimeout(() => { copyFeedback[server.id] = false }, 1500)
}

async function fetchServers() {
  const response = await fetch('/api/v1/servers')
  servers.value = await response.json()
}

async function addServer() {
  settingsError.value = ''
  let parsedSettings: { envs?: Record<string, string>; args?: string[] } = {}
  try {
    parsedSettings = JSON.parse(form.settings)
  } catch {
    settingsError.value = 'Settings: ungültiges JSON'
    return
  }

  const payload: Record<string, unknown> = {
    name: form.name,
    slug: form.slug || nameToSlug(form.name),
    source_type: form.source_type,
    env_vars: parsedSettings.envs ?? {},
    args: parsedSettings.args ?? [],
  }
  if (requiresPackageName.value) payload.package_name = form.package_name
  if (requiresExecutable.value) payload.executable_name = form.executable_name
  if (form.source_type === 'GITHUB') payload.git_url = form.git_url
  if (form.source_type === 'LOCAL') payload.local_path = form.local_path
  if (form.source_type === 'OPENAPI') payload.backend_url = form.backend_url

  await fetch('/api/v1/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  form.name = ''
  form.slug = ''
  form.package_name = ''
  form.executable_name = ''
  form.git_url = ''
  form.local_path = ''
  form.backend_url = ''
  form.settings = DEFAULT_SETTINGS
  await fetchServers()
  addServerOpen.value = false
}

async function callAction(id: number, action: 'start' | 'stop' | 'update') {
  loadingById[id] = true
  try {
    await fetch(`/api/v1/servers/${id}/${action}`, { method: 'POST' })
    await fetchServers()
  } finally {
    loadingById[id] = false
  }
}

function openLogs(id: number) {
  globalThis.window.open(`/api/v1/servers/${id}/logs`, '_blank')
}

// ── Edit-Modal ────────────────────────────────────────────────────────────────
const editModal = reactive({
  open: false,
  serverId: null as number | null,
  sourceType: 'PYPI' as SourceType,
  name: '',
  slug: '',
  package_name: '',
  executable_name: '',
  git_url: '',
  local_path: '',
  backend_url: '',
  settings: DEFAULT_SETTINGS,
  settingsError: '',
  saving: false,
})

const editRequiresExecutable = computed(() => ['GITHUB', 'LOCAL'].includes(editModal.sourceType))
const editRequiresPackageName = computed(() => ['PYPI', 'NPM'].includes(editModal.sourceType))

function openEdit(server: Server) {
  editModal.open = true
  editModal.serverId = server.id
  editModal.sourceType = server.source_type
  editModal.name = server.name
  editModal.slug = server.slug
  editModal.package_name = server.package_name ?? ''
  editModal.executable_name = server.executable_name ?? ''
  editModal.git_url = server.git_url ?? ''
  editModal.local_path = server.local_path ?? ''
  editModal.backend_url = server.backend_url ?? ''
  editModal.settings = JSON.stringify({ envs: server.env_vars, args: server.args }, null, 2)
  editModal.settingsError = ''
}

function closeEdit() {
  editModal.open = false
}

async function saveEdit() {
  editModal.settingsError = ''
  let parsedSettings: { envs?: Record<string, string>; args?: string[] } = {}
  try {
    parsedSettings = JSON.parse(editModal.settings)
  } catch {
    editModal.settingsError = 'Settings: ungültiges JSON'
    return
  }

  const payload: Record<string, unknown> = {
    name: editModal.name,
    slug: editModal.slug,
    env_vars: parsedSettings.envs ?? {},
    args: parsedSettings.args ?? [],
  }
  if (editModal.package_name) payload.package_name = editModal.package_name
  if (editModal.executable_name) payload.executable_name = editModal.executable_name
  if (editModal.git_url) payload.git_url = editModal.git_url
  if (editModal.local_path) payload.local_path = editModal.local_path
  if (editModal.backend_url) payload.backend_url = editModal.backend_url

  editModal.saving = true
  try {
    await fetch(`/api/v1/servers/${editModal.serverId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    closeEdit()
    await fetchServers()
  } finally {
    editModal.saving = false
  }
}

onMounted(() => {
  checkBackend()
  pollTimer = setInterval(checkBackend, 10000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  stopLogs()
})

// ── Log-Panel ─────────────────────────────────────────────────────────────────
const logsOpen = ref(false)
const logsAutoScroll = ref(true)
const logsRunning = ref(false)
const logsFlat = ref<string[]>([])
const logContainer = ref<HTMLElement | null>(null)
let logsWs: WebSocket | null = null

function startLogs() {
  if (logsWs) return
  logsFlat.value = []
  const proto = globalThis.location?.protocol === 'https:' ? 'wss' : 'ws'
  const host = globalThis.location?.host ?? 'localhost:8001'
  logsWs = new WebSocket(`${proto}://${host}/api/v1/ws/logs`)
  logsRunning.value = true
  logsWs.onmessage = (evt) => {
    const msg = JSON.parse(evt.data as string) as { ping?: boolean; slug?: string; line?: string }
    if (msg.ping) return
    logsFlat.value.push(`[${msg.slug}] ${msg.line}`)
  }
  logsWs.onclose = () => { logsWs = null; logsRunning.value = false }
  logsWs.onerror = () => { logsWs?.close() }
}

function stopLogs() {
  logsWs?.close()
}

// ── MCP-Config-Modal ─────────────────────────────────────────────────────────
const mcpModal = reactive({
  open: false,
  server: null as Server | null,
  activeTab: 'vscode' as 'vscode' | 'claude',
})
const mcpCopyFeedback = reactive<Record<string, boolean>>({})

function mcpUrl(server: Server): string {
  return `${MANAGER_ORIGIN}/v1/mcp/${server.slug}`
}

function mcpJsonSnippet(server: Server, format: 'vscode' | 'claude'): string {
  const url = mcpUrl(server)
  if (format === 'vscode') {
    return JSON.stringify({ servers: { [server.slug]: { type: 'http', url } } }, null, 2)
  }
  return JSON.stringify({ mcpServers: { [server.slug]: { type: 'http', url } } }, null, 2)
}

function openMcpModal(server: Server) {
  mcpModal.server = server
  mcpModal.activeTab = 'vscode'
  mcpModal.open = true
}

function closeMcpModal() {
  mcpModal.open = false
}

async function copyMcpJson(format: 'vscode' | 'claude') {
  if (!mcpModal.server) return
  await globalThis.navigator.clipboard.writeText(mcpJsonSnippet(mcpModal.server, format))
  mcpCopyFeedback[format] = true
  setTimeout(() => { mcpCopyFeedback[format] = false }, 1500)
}

watch(logsOpen, (open) => { if (!open) stopLogs() })

watch(logsFlat, async () => {
  if (!logsAutoScroll.value) return
  await nextTick()
  if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
})
</script>

<template>
  <main class="mx-auto max-w-6xl p-6">
    <!-- Title + Backend-Status-Badge -->
    <div class="mb-6 flex items-center gap-3">
      <h1 class="text-3xl font-bold">moles-mcp-proxy-manager</h1>
      <span
        class="rounded-full px-2.5 py-0.5 text-xs font-medium"
        :class="backendOnline === null
          ? 'bg-slate-700 text-slate-400'
          : backendOnline
            ? 'bg-emerald-900 text-emerald-300'
            : 'bg-red-900 text-red-300'"
      >
        {{ backendOnline === null ? 'connecting…' : backendOnline ? 'backend online' : 'backend offline' }}
      </span>
      <div class="ml-auto flex gap-2">
        <button
          class="flex items-center gap-1.5 rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium hover:bg-emerald-600"
          @click="openAddServer"
        >
          + Add Server
        </button>
        <button
          class="flex items-center gap-1.5 rounded bg-slate-700 px-3 py-1.5 text-sm font-medium hover:bg-slate-600"
          @click="catalogOpen = true"
        >
          Catalog
        </button>
      </div>
    </div>

    <!-- Server Dashboard -->
    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="server in servers" :key="server.id" class="rounded border border-slate-700 p-4">
        <header class="mb-3 flex items-center justify-between">
          <h3 class="font-semibold">{{ server.name }}</h3>
          <span class="rounded bg-slate-800 px-2 py-1 text-xs">{{ server.source_type }}</span>
        </header>

        <!-- Connection URL for Open WebUI -->
        <div class="mb-3 flex items-center gap-2 overflow-hidden rounded bg-slate-900 px-2 py-1">
          <span class="flex-1 truncate font-mono text-xs text-slate-300">{{ connectionUrl(server) }}</span>
          <button
            class="shrink-0 rounded bg-slate-700 px-2 py-0.5 text-xs hover:bg-slate-600"
            :class="{ 'bg-emerald-700': copyFeedback[server.id] }"
            @click="copyUrl(server)"
          >{{ copyFeedback[server.id] ? 'Copied!' : 'Copy' }}</button>
        </div>

        <p class="mb-3 text-sm">
          Status:
          <span :class="server.status === 'running' ? 'text-emerald-400' : 'text-slate-400'">
            {{ server.status }}
          </span>
          <span v-if="server.internal_port" class="ml-1 text-xs text-slate-500">(internal :{{ server.internal_port }})</span>
        </p>

        <!-- Settings summary -->
        <div v-if="Object.keys(server.env_vars).length || server.args.length" class="mb-3 rounded bg-slate-900 px-2 py-1 text-xs text-slate-400">
          <span v-if="Object.keys(server.env_vars).length" class="mr-2">envs: {{ Object.keys(server.env_vars).join(', ') }}</span>
          <span v-if="server.args.length">args: {{ server.args.join(' ') }}</span>
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            class="rounded px-3 py-1 text-sm"
            :class="server.status === 'running' ? 'bg-red-700 hover:bg-red-600' : 'bg-emerald-600 hover:bg-emerald-500'"
            @click="callAction(server.id, server.status === 'running' ? 'stop' : 'start')"
          >
            {{ server.status === 'running' ? 'Stop' : 'Start' }}
          </button>
          <button
            class="rounded bg-amber-500 px-3 py-1 text-sm hover:bg-amber-400 disabled:opacity-50"
            :disabled="loadingById[server.id]"
            @click="callAction(server.id, 'update')"
          >
            <span v-if="loadingById[server.id]">Updating…</span>
            <span v-else>Update</span>
          </button>
          <button class="rounded bg-slate-600 px-3 py-1 text-sm hover:bg-slate-500" @click="openLogs(server.id)">Logs</button>
          <button class="rounded bg-blue-700 px-3 py-1 text-sm hover:bg-blue-600" @click="openEdit(server)">Edit</button>
          <button class="rounded bg-violet-700 px-3 py-1 text-sm hover:bg-violet-600" @click="openMcpModal(server)">MCP Config</button>
        </div>
      </article>
    </section>

    <!-- Log Panel -->
    <section class="mt-8">
      <div
        class="flex w-full cursor-pointer select-none items-center rounded px-4 py-2.5 text-sm font-medium"
        :class="logsOpen ? 'rounded-b-none border border-slate-600 bg-slate-700' : 'border border-slate-700 bg-slate-800 hover:bg-slate-700'"
        role="button"
        @click="logsOpen = !logsOpen"
      >
        <span class="flex-1 text-left">Logs</span>
        <!-- Controls (only when open) -->
        <span v-if="logsOpen" class="mr-4 flex items-center gap-3 text-xs" @click.stop>
          <button
            class="rounded px-2.5 py-0.5 font-medium"
            :class="logsRunning ? 'bg-red-700 hover:bg-red-600' : 'bg-emerald-700 hover:bg-emerald-600'"
            @click="logsRunning ? stopLogs() : startLogs()"
          >{{ logsRunning ? '■ Stop' : '▶ Start' }}</button>
          <button
            class="rounded bg-slate-600 px-2.5 py-0.5 font-medium hover:bg-slate-500"
            @click="logsFlat = []"
          >✕ Clear</button>
          <span class="flex items-center gap-1.5">
            <span class="text-slate-400">Auto-scroll</span>
            <span
              class="relative inline-flex h-4 w-7 cursor-pointer rounded-full transition-colors duration-200"
              :class="logsAutoScroll ? 'bg-blue-600' : 'bg-slate-600'"
              @click="logsAutoScroll = !logsAutoScroll"
            >
              <span
                class="absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform duration-200"
                :class="logsAutoScroll ? 'translate-x-3.5' : 'translate-x-0.5'"
              />
            </span>
          </span>
        </span>
        <span class="text-slate-400 text-xs">{{ logsOpen ? '▲ zuklappen' : '▼ ausklappen' }}</span>
      </div>
      <div
        v-if="logsOpen"
        ref="logContainer"
        class="overflow-y-auto rounded-b border border-t-0 border-slate-600 bg-slate-950"
        style="height: 50vh"
      >
        <div
          v-for="(line, i) in logsFlat"
          :key="i"
          class="border-b border-slate-900 px-3 py-0.5 font-mono text-xs text-slate-300"
        >{{ line }}</div>
        <div v-if="logsFlat.length === 0" class="flex h-full items-center justify-center text-sm text-slate-500">
          Keine Logs vorhanden — starte einen Server um Output zu sehen.
        </div>
      </div>
    </section>

    <!-- Edit Modal -->
    <Teleport to="body">
      <!-- Catalog Modal -->
      <div
        v-if="catalogOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
        @click.self="catalogOpen = false"
      >
        <div class="flex w-full max-w-xl flex-col rounded-lg border border-slate-600 bg-slate-800 p-6 shadow-xl" style="max-height: 80vh">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-lg font-semibold">MCP Server Catalog</h2>
            <button class="text-slate-400 hover:text-white" @click="catalogOpen = false">&#10005;</button>
          </div>
          <!-- Filter -->
          <input
            v-model="catalogFilter"
            class="mb-4 rounded bg-slate-900 p-2 text-sm"
            placeholder="Filter by name, description or package…"
            autofocus
          />
          <!-- List -->
          <ul class="overflow-y-auto" role="list">
            <!-- Empty Template always at top -->
            <li class="mb-1 flex items-center gap-3 rounded border-b border-slate-700/60 px-2 py-2.5 hover:bg-slate-700">
              <div class="min-w-0 flex-1">
                <p class="font-medium">Empty Template</p>
                <p class="text-xs text-slate-400">Leeres Formular — alles manuell konfigurieren</p>
              </div>
              <button
                class="shrink-0 rounded bg-emerald-700 px-3 py-1 text-sm hover:bg-emerald-600"
                @click="openAddServer"
              >Use</button>
            </li>
            <li
              v-for="entry in filteredCatalog"
              :key="entry.id"
              class="flex items-center gap-3 rounded px-2 py-2.5 hover:bg-slate-700"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ entry.name }}</p>
                <p class="truncate text-xs text-slate-400">{{ entry.description }}</p>
                <p v-if="entry.package_name" class="truncate font-mono text-xs text-slate-500">{{ entry.package_name }}</p>
              </div>
              <span
                class="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium"
                :class="SOURCE_TYPE_BADGE[entry.source_type]"
              >{{ entry.source_type.toLowerCase() }}</span>
              <button
                class="shrink-0 rounded bg-blue-600 px-3 py-1 text-sm hover:bg-blue-500"
                @click="applyTemplate(entry)"
              >Use</button>
            </li>
            <li v-if="filteredCatalog.length === 0" class="py-6 text-center text-sm text-slate-500">
              No entries match „{{ catalogFilter }}“
            </li>
          </ul>
        </div>
      </div>

      <!-- Add Server Modal -->
      <div
        v-if="addServerOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
        @click.self="addServerOpen = false"
      >
        <div
          class="flex w-full max-w-lg flex-col rounded-lg border border-slate-600 bg-slate-800 p-6 shadow-xl"
          style="max-height: 90vh; overflow-y: auto"
        >
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Add Server</h2>
            <button class="text-slate-400 hover:text-white" @click="addServerOpen = false">&#10005;</button>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <div>
              <label class="mb-1 block text-xs text-slate-400">Name</label>
              <input v-model="form.name" class="w-full rounded bg-slate-900 p-2 text-sm" placeholder="My MCP Server" @input="onNameInput" />
            </div>
            <div>
              <label class="mb-1 block text-xs text-slate-400">Slug</label>
              <input v-model="form.slug" class="w-full rounded bg-slate-900 p-2 font-mono text-sm" placeholder="my-mcp-server" />
            </div>
            <div class="md:col-span-2">
              <label class="mb-1 block text-xs text-slate-400">Source Type</label>
              <select v-model="form.source_type" class="w-full rounded bg-slate-900 p-2 text-sm">
                <option value="PYPI">PyPI</option>
                <option value="NPM">npm</option>
                <option value="GITHUB">GitHub</option>
                <option value="LOCAL">Local Path</option>
                <option value="OPENAPI">Native OpenAPI</option>
              </select>
            </div>
            <div v-if="requiresPackageName" class="md:col-span-2">
              <label class="mb-1 block text-xs text-slate-400">Package Name</label>
              <input v-model="form.package_name" class="w-full rounded bg-slate-900 p-2 text-sm" placeholder="e.g. mcp-server-fetch" />
            </div>
            <div v-if="requiresExecutable" class="md:col-span-2">
              <label class="mb-1 block text-xs text-slate-400">Executable Name</label>
              <input v-model="form.executable_name" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div v-if="form.source_type === 'GITHUB'" class="md:col-span-2">
              <label class="mb-1 block text-xs text-slate-400">GitHub URL</label>
              <input v-model="form.git_url" class="w-full rounded bg-slate-900 p-2 text-sm" placeholder="https://github.com/…" />
            </div>
            <div v-if="form.source_type === 'LOCAL'" class="md:col-span-2">
              <label class="mb-1 block text-xs text-slate-400">Local Path</label>
              <input v-model="form.local_path" class="w-full rounded bg-slate-900 p-2 text-sm" placeholder="/absolute/path/to/server" />
            </div>
            <div v-if="form.source_type === 'OPENAPI'" class="md:col-span-2">
              <label class="mb-1 block text-xs text-slate-400">Backend URL</label>
              <input v-model="form.backend_url" class="w-full rounded bg-slate-900 p-2 text-sm" placeholder="http://…" />
            </div>
          </div>

          <div class="mt-3">
            <label class="mb-1 block text-xs text-slate-400">Settings (JSON)</label>
            <textarea
              v-model="form.settings"
              class="w-full rounded bg-slate-900 p-2 font-mono text-sm"
              rows="7"
              spellcheck="false"
            />
            <p v-if="settingsError" class="mt-1 text-xs text-red-400">{{ settingsError }}</p>
            <p class="mt-1 text-xs text-slate-500">Verwende <code>envs</code> für Umgebungsvariablen und <code>args</code> für zusätzliche CLI-Argumente.</p>
          </div>

          <div class="mt-5 flex justify-end gap-3">
            <button class="rounded bg-slate-600 px-4 py-2 text-sm hover:bg-slate-500" @click="addServerOpen = false">Cancel</button>
            <button class="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500" @click="addServer">Save</button>
          </div>
        </div>
      </div>

      <!-- Edit Modal -->
      <div
        v-if="editModal.open"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
        @click.self="closeEdit"
      >
        <div class="w-full max-w-lg rounded-lg border border-slate-600 bg-slate-800 p-6 shadow-xl">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Edit Server</h2>
            <button class="text-slate-400 hover:text-white" @click="closeEdit">✕</button>
          </div>

          <div class="grid gap-3">
            <div>
              <label class="mb-1 block text-xs text-slate-400">Name</label>
              <input v-model="editModal.name" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div>
              <label class="mb-1 block text-xs text-slate-400">Slug</label>
              <input v-model="editModal.slug" class="w-full rounded bg-slate-900 p-2 font-mono text-sm" />
            </div>
            <div v-if="editRequiresPackageName">
              <label class="mb-1 block text-xs text-slate-400">Package Name</label>
              <input v-model="editModal.package_name" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div v-if="editRequiresExecutable">
              <label class="mb-1 block text-xs text-slate-400">Executable Name</label>
              <input v-model="editModal.executable_name" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div v-if="editModal.sourceType === 'GITHUB'">
              <label class="mb-1 block text-xs text-slate-400">GitHub URL</label>
              <input v-model="editModal.git_url" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div v-if="editModal.sourceType === 'LOCAL'">
              <label class="mb-1 block text-xs text-slate-400">Local Path</label>
              <input v-model="editModal.local_path" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div v-if="editModal.sourceType === 'OPENAPI'">
              <label class="mb-1 block text-xs text-slate-400">Backend URL</label>
              <input v-model="editModal.backend_url" class="w-full rounded bg-slate-900 p-2 text-sm" />
            </div>
            <div>
              <label class="mb-1 block text-xs text-slate-400">Settings (JSON)</label>
              <textarea
                v-model="editModal.settings"
                class="w-full rounded bg-slate-900 p-2 font-mono text-sm"
                rows="8"
                spellcheck="false"
              />
              <p v-if="editModal.settingsError" class="mt-1 text-xs text-red-400">{{ editModal.settingsError }}</p>
            </div>
          </div>

          <div class="mt-5 flex justify-end gap-3">
            <button class="rounded bg-slate-600 px-4 py-2 text-sm hover:bg-slate-500" @click="closeEdit">Cancel</button>
            <button
              class="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500 disabled:opacity-50"
              :disabled="editModal.saving"
              @click="saveEdit"
            >
              {{ editModal.saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>
      </div>

      <!-- MCP Config Modal -->
      <div
        v-if="mcpModal.open"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
        @click.self="closeMcpModal"
      >
        <div class="w-full max-w-xl rounded-lg border border-slate-600 bg-slate-800 p-6 shadow-xl">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-lg font-semibold">MCP Config — {{ mcpModal.server?.name }}</h2>
            <button class="text-slate-400 hover:text-white" @click="closeMcpModal">✕</button>
          </div>

          <!-- Format-Tabs -->
          <div class="mb-3 flex gap-0 border-b border-slate-700">
            <button
              class="px-4 py-1.5 text-sm"
              :class="mcpModal.activeTab === 'vscode' ? 'border-b-2 border-blue-400 text-blue-400' : 'text-slate-400 hover:text-white'"
              @click="mcpModal.activeTab = 'vscode'"
            >VS Code</button>
            <button
              class="px-4 py-1.5 text-sm"
              :class="mcpModal.activeTab === 'claude' ? 'border-b-2 border-blue-400 text-blue-400' : 'text-slate-400 hover:text-white'"
              @click="mcpModal.activeTab = 'claude'"
            >Claude Desktop</button>
          </div>

          <p class="mb-2 text-xs text-slate-400">
            <span v-if="mcpModal.activeTab === 'vscode'">In <code class="rounded bg-slate-900 px-1">.vscode/mcp.json</code> eintragen:</span>
            <span v-else>In <code class="rounded bg-slate-900 px-1">claude_desktop_config.json</code> unter <code class="rounded bg-slate-900 px-1">mcpServers</code> eintragen:</span>
          </p>

          <pre class="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-200">{{ mcpModal.server ? mcpJsonSnippet(mcpModal.server, mcpModal.activeTab) : '' }}</pre>

          <div class="mt-4 flex justify-end gap-3">
            <button
              class="rounded px-4 py-2 text-sm"
              :class="mcpCopyFeedback[mcpModal.activeTab] ? 'bg-emerald-700' : 'bg-slate-600 hover:bg-slate-500'"
              @click="copyMcpJson(mcpModal.activeTab)"
            >{{ mcpCopyFeedback[mcpModal.activeTab] ? 'Copied!' : 'Copy' }}</button>
            <button class="rounded bg-slate-600 px-4 py-2 text-sm hover:bg-slate-500" @click="closeMcpModal">Close</button>
          </div>
        </div>
      </div>
    </Teleport>
  </main>
</template>
