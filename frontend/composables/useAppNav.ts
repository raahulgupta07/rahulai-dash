// Shared app-navigation model.
//
// Single source of truth for the grouped nav (Agent Studios / Workspace / Build /
// Manage / Settings). Consumed by BOTH the top bar (TopNav) and the contextual
// left rail (AppRail) so they never drift. The top bar shows the GROUPS; clicking
// a group routes to that group's first page, and AppRail then shows that group's
// items as a left rail (one group at a time — no dropdowns).
import LibraryIcon from '~/components/icons/LibraryIcon.vue'
import ActivityIcon from '~/components/icons/ActivityIcon.vue'
import McpIcon from '~/components/icons/McpIcon.vue'
import { useCan } from '~/composables/usePermissions'

export interface NavItem {
  key: string
  label: string
  href?: string
  activePath?: string
  icon?: string
  component?: any
  adminOnly?: boolean
  permission?: string
  action?: () => void
  children?: NavItem[]
  // Optional sub-section eyebrow label shown in the rail above this item when
  // the section changes (e.g. WORKSPACE / OUTPUTS / AUTOMATE). When a group has
  // no sections the rail renders the group title once (legacy behavior).
  section?: string
}
export interface NavGroup {
  title: string
  items: NavItem[]
  // When set, the group header is a direct route link (no rail) — used for
  // standalone top-level tabs like Agent Studios.
  direct?: string
  // When set (alongside sectioned items), the rail renders a studio-style
  // header card (icon + title + badge + subtitle) on a rounded #FBFAF6 panel.
  railHeader?: { subtitle?: string; badge?: string; icon?: string }
}

// ---- Module-level shared state (singletons across all consumers) ----
// MCP modal lives in TopNav's template; AppRail/TopNav both flip this ref.
const showMcpModal = ref(false)
// Per-item rail count badges, keyed by NavItem.key. A page (e.g. Workspace
// Overview) populates this after fetching; the rail reads it fail-soft (missing
// key = no badge). Module-level so it survives across the page/rail boundary.
const railCounts = ref<Record<string, number>>({})
// "Pack Analytics" settings tab visibility — fetched once, fail-soft.
const domainPacksEnabled = ref(false)
let domainPacksLoaded = false

export function useAppNav() {
  const route = useRoute()
  const { isMcpEnabled } = useOrgSettings()
  const isAdmin = computed<boolean>(() => useCan('full_admin_access'))

  const loadDomainPacksFlag = async () => {
    if (domainPacksLoaded) return
    domainPacksLoaded = true
    try {
      const { data } = await useMyFetch<any[]>('/api/organization/hybrid-flags')
      const rows = (data.value as any[]) || []
      const row = rows.find(r => r?.env_name === 'HYBRID_DOMAIN_PACKS')
      domainPacksEnabled.value = !!row?.effective
    } catch {
      domainPacksEnabled.value = false
    }
  }

  // Settings sub-tabs (mirror of layouts/settings.vue), each gated by a permission.
  const settingsTabs: { name: string; label: string; permission: string; icon: string }[] = [
    { name: 'members', label: 'settings.membersTab', permission: 'view_members', icon: 'heroicons-users' },
    { name: 'models', label: 'settings.llm', permission: 'manage_llm', icon: 'heroicons-cpu-chip' },
    { name: 'ai_settings', label: 'settings.aiSettings', permission: 'manage_settings', icon: 'heroicons-sparkles' },
    { name: 'general', label: 'settings.general', permission: 'manage_settings', icon: 'heroicons-cog-6-tooth' },
    { name: 'integrations', label: 'settings.integrations.title', permission: 'manage_settings', icon: 'heroicons-squares-2x2' },
    { name: 'folder-sync', label: 'Folder Sync', permission: 'manage_settings', icon: 'heroicons-folder-arrow-down' },
    { name: 'smtp', label: 'settings.smtpTab', permission: 'manage_settings', icon: 'heroicons-envelope' },
    { name: 'audit', label: 'settings.auditLogs', permission: 'view_audit_logs', icon: 'heroicons-clipboard-document-list' },
    { name: 'identity-provider', label: 'settings.identityProviderTab', permission: 'manage_identity_providers', icon: 'heroicons-finger-print' },
    { name: 'features', label: 'Feature Flags', permission: 'manage_settings', icon: 'heroicons-flag' },
  ]

  // Section eyebrow per settings tab → groups the rail like Workspace.
  const settingsSection: Record<string, string> = {
    members: 'PEOPLE',
    models: 'WORKSPACE', ai_settings: 'WORKSPACE', general: 'WORKSPACE',
    integrations: 'INTEGRATIONS', 'folder-sync': 'INTEGRATIONS', smtp: 'INTEGRATIONS',
    audit: 'SECURITY', 'identity-provider': 'SECURITY',
    features: 'ADVANCED', 'pack-analytics': 'ADVANCED',
  }

  const settingsChildren = computed<NavItem[]>(() => {
    const tabs = settingsTabs.filter(tab => useCan(tab.permission))
    const children = tabs.map(tab => ({ key: `settings-${tab.name}`, label: tab.label, href: `/settings/${tab.name}`, activePath: `/settings/${tab.name}`, icon: tab.icon, section: settingsSection[tab.name] || 'WORKSPACE' }))
    if (domainPacksEnabled.value && useCan('manage_settings')) {
      children.push({ key: 'settings-pack-analytics', label: 'Pack Analytics', href: '/settings/pack-analytics', activePath: '/settings/pack-analytics', icon: 'heroicons-chart-bar-square', section: 'ADVANCED' })
    }
    return children
  })

  // Full group model.
  const allGroups = computed<NavGroup[]>(() => [
    {
      title: 'nav.studios',
      direct: '/studios',
      items: [
        { key: 'studios', href: '/studios', activePath: '/studios', icon: 'heroicons-film', label: 'nav.studios' },
      ],
    },
    {
      title: 'nav.dataAgents',
      direct: '/agents',
      items: [
        { key: 'data-agents', href: '/agents', activePath: '/agents', icon: 'heroicons-circle-stack', label: 'nav.dataAgents' },
      ],
    },
    {
      title: 'nav.workspace',
      railHeader: { subtitle: 'Everything your agents produce', badge: 'ORG', icon: 'heroicons-squares-2x2' },
      items: [
        { key: 'overview', href: '/workspace', activePath: '/workspace', icon: 'heroicons-squares-2x2', label: 'Overview', section: 'WORKSPACE' },
        { key: 'templates', href: '/templates', activePath: '/templates', icon: 'heroicons-square-3-stack-3d', label: 'Agent Templates', section: 'WORKSPACE' },
        { key: 'reports', href: '/reports', activePath: '/reports', icon: 'heroicons-chat-bubble-left-right', label: 'nav.reports', section: 'OUTPUTS' },
        { key: 'dashboards', href: '/dashboards', activePath: '/dashboards', icon: 'heroicons-chart-bar-square', label: 'nav.dashboards', section: 'OUTPUTS' },
        { key: 'presentations', href: '/presentations', activePath: '/presentations', icon: 'heroicons-presentation-chart-line', label: 'nav.presentations', section: 'OUTPUTS' },
        { key: 'spreadsheets', href: '/spreadsheets', activePath: '/spreadsheets', icon: 'heroicons-table-cells', label: 'nav.spreadsheets', section: 'OUTPUTS' },
        { key: 'scheduled', href: '/scheduled-tasks', activePath: '/scheduled-tasks', icon: 'heroicons-clock', label: 'nav.scheduled', section: 'AUTOMATE' },
      ],
    },
    {
      title: 'nav.build',
      railHeader: { subtitle: 'Teach your agents what they know', badge: 'ORG', icon: 'heroicons-cube' },
      items: [
        { key: 'knowledge', href: '/knowledge', activePath: '/knowledge', icon: 'heroicons-academic-cap', label: 'nav.knowledge', section: 'CONTEXT' },
        { key: 'instructions', href: '/instructions', activePath: '/instructions', icon: 'heroicons-cube', label: 'nav.instructions', section: 'CONTEXT' },
        { key: 'queries', href: '/queries', activePath: '/queries', component: LibraryIcon, label: 'nav.queries', section: 'CONTEXT' },
        // 'Skills' (global /skills = HYBRID_SKILLS sandbox-exec) removed from nav —
        // known-unstable (livelocks the agent loop). Use studio Domain Packs instead.
        { key: 'memory', href: '/memory', activePath: '/memory', icon: 'heroicons-cpu-chip', label: 'Memory', section: 'CAPABILITIES' },
        { key: 'my-groups', href: '/settings/my-groups', activePath: '/settings/my-groups', icon: 'heroicons-user-group', label: 'My Groups', section: 'ACCESS' },
      ],
    },
    {
      title: 'nav.manage',
      railHeader: { subtitle: 'Connect, observe, and automate', badge: 'ORG', icon: 'heroicons-adjustments-horizontal' },
      items: [
        // Open to ALL org members: each user sees connectors they created + shared
        // to them + org-wide, and can self-serve build/edit their own (per-user
        // connector visibility). Create-shared/org stays gated inside the page.
        { key: 'connectors', href: '/connectors', activePath: '/connectors', icon: 'heroicons-circle-stack', label: 'Connectors', section: 'DATA' },
        // Self-serve: any member connects an admin-published connector with their
        // own account → private, per-user data source.
        { key: 'available-connectors', href: '/connectors/available', activePath: '/connectors/available', icon: 'heroicons-user-plus', label: 'nav.availableConnectors', section: 'DATA' },
        { key: 'monitoring', href: '/monitoring', activePath: '/monitoring', component: ActivityIcon, label: 'nav.monitoring', adminOnly: true, section: 'OBSERVE' },
        { key: 'evals', href: '/evals', activePath: '/evals', icon: 'heroicons-check-circle', label: 'nav.evals', permission: 'manage_evals', section: 'OBSERVE' },
        { key: 'workflows', href: '/workflows', activePath: '/workflows', icon: 'heroicons-arrow-path', label: 'Workflows', permission: 'manage_settings', section: 'AUTOMATE' },
        {
          key: 'mcp',
          label: 'nav.mcpServer',
          component: McpIcon,
          permission: 'manage_settings',
          section: 'AUTOMATE',
          action: () => { if (isMcpEnabled.value) showMcpModal.value = true },
        },
      ],
    },
    {
      title: 'nav.settings',
      railHeader: { subtitle: 'Workspace configuration', badge: 'ADMIN', icon: 'heroicons-cog-6-tooth' },
      items: settingsChildren.value,
    },
  ])

  const itemVisible = (item: NavItem) => {
    if (item.key === 'mcp' && !isMcpEnabled.value) return false
    if (item.children && item.children.length === 0) return false
    if (item.permission && !useCan(item.permission)) return false
    if (item.adminOnly && !isAdmin.value) return false
    return true
  }

  const visibleGroups = computed<NavGroup[]>(() =>
    allGroups.value
      .map(g => ({ title: g.title, direct: g.direct, railHeader: g.railHeader, items: g.items.filter(itemVisible) }))
      .filter(g => g.items.length > 0)
  )

  const isRouteActive = (path: string) => {
    if (path === '/') return route.path === '/'
    return route.path === path || route.path.startsWith(path + '/')
  }

  const isGroupActive = (group: NavGroup) =>
    group.items.some(it =>
      (it.href && isRouteActive(it.activePath || it.href)) ||
      (it.children?.some(c => c.href && isRouteActive(c.href)) ?? false)
    )

  // First navigable href in a group (where a group click should land).
  const firstHref = (group: NavGroup): string | null => {
    const it = group.items.find(i => !!i.href)
    return it?.href || group.direct || null
  }

  // The non-direct group matching the current route → drives the contextual rail.
  const activeGroup = computed<NavGroup | null>(() =>
    visibleGroups.value.find(g => !g.direct && isGroupActive(g)) || null
  )

  return {
    visibleGroups,
    activeGroup,
    isRouteActive,
    isGroupActive,
    firstHref,
    itemVisible,
    showMcpModal,
    railCounts,
    loadDomainPacksFlag,
  }
}
