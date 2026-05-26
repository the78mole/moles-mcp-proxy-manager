<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

type SourceType = 'PYPI' | 'GITHUB' | 'LOCAL' | 'OPENAPI'

type Server = {
  id: number
  name: string
  source_type: SourceType
  package_name?: string
  executable_name?: string
  git_url?: string
  local_path?: string
  backend_url?: string
  target_port: number
  status: string
  env_vars: Record<string, string>
}

const servers = ref<Server[]>([])
const loadingById = reactive<Record<number, boolean>>({})
const form = reactive({
  name: '',
  source_type: 'PYPI' as SourceType,
  package_name: '',
  executable_name: '',
  git_url: '',
  local_path: '',
  backend_url: '',
  target_port: 9000,
})

const requiresExecutable = computed(() => ['GITHUB', 'LOCAL'].includes(form.source_type))

async function fetchServers() {
  const response = await fetch('/api/v1/servers')
  servers.value = await response.json()
}

async function addServer() {
  const payload: Record<string, unknown> = {
    ...form,
    env_vars: {},
  }
  if (form.source_type !== 'PYPI') delete payload.package_name
  if (!requiresExecutable.value) delete payload.executable_name
  if (form.source_type !== 'GITHUB') delete payload.git_url
  if (form.source_type !== 'LOCAL') delete payload.local_path
  if (form.source_type !== 'OPENAPI') delete payload.backend_url

  await fetch('/api/v1/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
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

onMounted(fetchServers)
</script>

<template>
  <main class="mx-auto max-w-6xl p-6">
    <h1 class="mb-6 text-3xl font-bold">moles-mcp-proxy-manager</h1>

    <section class="mb-8 rounded border border-slate-700 p-4">
      <h2 class="mb-4 text-xl font-semibold">Add Server</h2>
      <div class="grid gap-3 md:grid-cols-2">
        <input v-model="form.name" class="rounded bg-slate-900 p-2" placeholder="Name" />
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
        <input v-model.number="form.target_port" type="number" class="rounded bg-slate-900 p-2" placeholder="Target Port" />
      </div>
      <button class="mt-4 rounded bg-blue-600 px-4 py-2" @click="addServer">Save</button>
    </section>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="server in servers" :key="server.id" class="rounded border border-slate-700 p-4">
        <header class="mb-3 flex items-center justify-between">
          <h3 class="font-semibold">{{ server.name }}</h3>
          <span class="rounded bg-slate-800 px-2 py-1 text-xs">{{ server.source_type }}</span>
        </header>
        <p class="text-sm">Port: {{ server.target_port }}</p>
        <p class="mb-3 text-sm">Status: {{ server.status }}</p>
        <div class="flex gap-2">
          <button class="rounded bg-emerald-600 px-3 py-1 text-sm" @click="callAction(server.id, server.status === 'running' ? 'stop' : 'start')">
            {{ server.status === 'running' ? 'Stop' : 'Start' }}
          </button>
          <button class="rounded bg-amber-500 px-3 py-1 text-sm" :disabled="loadingById[server.id]" @click="callAction(server.id, 'update')">
            <span v-if="loadingById[server.id]">Updating...</span>
            <span v-else>Update</span>
          </button>
          <button class="rounded bg-slate-600 px-3 py-1 text-sm" @click="window.open(`/api/v1/servers/${server.id}/logs`, '_blank')">Logs</button>
        </div>
      </article>
    </section>
  </main>
</template>
