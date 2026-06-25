<template>
    <NuxtLayout name="default">
        <!-- Canonical Build/Manage page shell: centered, cream, no left rail.
             Each /settings/* tab is its own standalone page (nav lives in the
             top-bar "Settings ▾" dropdown). Title + subtitle come from the
             active tab so every page reads like Monitoring/Queries/etc. -->
        <div class="flex justify-center px-4 md:px-6 text-sm bg-[#FBFAF6] min-h-full">
            <div class="w-full max-w-7xl py-2 text-[#1f2328]">
                <!-- Page heading (per-tab) -->
                <div class="mb-6 pt-2">
                    <h1
                        class="text-2xl font-semibold text-[#1f2328] tracking-tight"
                        style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
                    >{{ currentTab ? $t(currentTab.label) : $t('settings.title') }}</h1>
                    <p v-if="currentTab?.description" class="mt-2 text-[#6b6b6b] leading-relaxed max-w-2xl">
                        {{ currentTab.description }}
                    </p>
                </div>

                <!-- Page content -->
                <div class="bg-white border border-[#E7E5DD] rounded-2xl p-6 md:p-8">
                    <slot />
                </div>
            </div>
        </div>
    </NuxtLayout>
</template>

<script setup lang="ts">
const route = useRoute()

// All available tabs with their required permissions + one-line descriptions.
const allTabs = [
    { name: 'members', label: 'settings.membersTab', requiredPermission: "view_members", description: 'Manage members, roles, and groups.' },
    { name: 'models', label: 'settings.llm', requiredPermission: "manage_llm", description: 'Configure language-model providers and API keys.' },
    { name: 'ai_settings', label: 'settings.aiSettings', requiredPermission: "manage_settings", description: 'Tune agent behaviour and AI defaults.' },
    { name: 'general', label: 'settings.general', requiredPermission: "manage_settings", description: 'Workspace name, branding, and general preferences.' },
    { name: "integrations", label: "settings.integrations.title", requiredPermission: "manage_settings", description: 'Connect external channels and integrations.' },
    { name: 'folder-sync', label: 'Folder Sync', requiredPermission: "manage_settings", description: 'Auto-ingest a local folder into an agent via the desktop sync app — like Claude Code.' },
    { name: 'audit', label: 'settings.auditLogs', requiredPermission: "view_audit_logs", description: 'Review activity and security events across the workspace.' },
    { name: 'identity-provider', label: 'settings.identityProviderTab', requiredPermission: "manage_identity_providers", description: 'Configure SSO, SCIM provisioning, and LDAP.' },
    { name: 'smtp', label: 'settings.smtpTab', requiredPermission: "manage_settings", description: 'Configure outbound email delivery.' },
    { name: 'features', label: 'Feature Flags', requiredPermission: "manage_settings", description: 'Toggle hybrid feature flags and experimental capabilities.' },
    { name: 'pack-analytics', label: 'Pack Analytics', requiredPermission: "manage_settings", description: 'Org-wide observability for Domain Packs (Skills) — binding, fires, and win-rate.' },
]

// The tab whose route is active (drives the page title + subtitle).
const currentTab = computed(() =>
    allTabs.find(tab => route.path === `/settings/${tab.name}`) || null
)
</script>
