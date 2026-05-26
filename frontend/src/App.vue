<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

type SourceType = 'PYPI' | 'GITHUB' | 'LOCAL' | 'OPENAPI'

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
}

const servers = ref<Server[]>([])
const loadingById = reactive<Record<number, boolean>>({})
const copyFeedback = reactive<Record<number, boolean>>({})

const form = reactive({
  name: '',
  slug: '',
  source_type: 'PYPI' as SourceType,
  package_name: '',
  executable_name: '',
  git_url: '',
  local_path: '',
  backend_url: '',
})

// Auto-generate slug from name: lowercase, replace non-alphanumeric with hyphens
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
  const payload: Record<string, unknown> = {
    name: form.name,
    slug: form.slug || nameToSlug(form.name),
    source_type: form.source_type,
    env_vars: {},
  }
  if (form.source_type === 'PYPI') payload.package_name = form.package_name
  if (requiresExecutable.value) payload.executable_name = form.executable_name
  if (form.source_type === 'GITHUB') payload.git_url = form.git_url
  if (form.source_type === 'LOCAL') payload.local_path = form.local_path
  if (form.source_type === 'OPENAPI') payload.backend_url = form.backend_url

  await fetch('/api/v1/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  // Reset form
  form.name = ''
  form.slug = ''
  form.package_name = ''
  form.executable_name = ''
  form.git_url = ''
  form.local_path = ''
  form.backend_url = ''
  await fetchServers()
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

onMounted(fetchServers)
</script>

<template>
  <main class="mx-auto max-w-6xl p-6">
    <h1 class="mb-6 text-3xl font-bold">moles-mcp-proxy-manager</h1>

    <!-- Add Server Form -->
    <section class="mb-8 rounded border border-slate-700 p-4">
      <h2 class="mb-4 text-xl font-semibold">Add Server</h2>
      <div class="grid gap-3 md:grid-cols-2">
        <input
          v-model="form.name"
          class="rounded bg-slate-900 p-2"
          placeholder="Name"
          @input="onNameInput"
        />
        <input
          v-model="form.slug"
          class="rounded bg-slate-900 p-2 font-mono"
          placeholder="URL Slug (e.g. my-tool)"
        />
        <select v-model="form.source_type" class="rounded bg-slate-900 p-2">
          <option value="PYPI">PyPI</option>
          <option value="GITHUB">GitHub</option>
          <option value="LOCAL">Local Path</option>
          <option value="OPENAPI">Native OpenAPI</option>
        </select>
        <input v-if="form.source_type === 'PYPI'" v-model="form.package_name" class="rounded bg-slate-900 p-2" placeholder="Package Name" />
        <input v-if="requiresExecutable" v-model="form.executable_name" class="rounded bg-slate-900 p-2" placeholder="Executable Name" />
        <input v-if="form.source_type === 'GITHUB'" v-model="form.git_url" class="rounded bg-slate-900 p-2" placeholder="GitHub URL" />
        <input v-if="form.source_type === 'LOCAL'" v-model="form.local_path" class="rounded bg-slate-900 p-2" placeholder="Absolute Local Path" />
        <input v-if="form.source_type === 'OPENAPI'" v-model="form.backend_url" class="rounded bg-slate-900 p-2" placeholder="Backend URL" />
      </div>
      <button class="mt-4 rounded bg-blue-600 px-4 py-2 hover:bg-blue-500" @click="addServer">Save</button>
    </section>

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

        <div class="flex gap-2">
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
        </div>
      </article>
    </section>
  </main>
</template>
