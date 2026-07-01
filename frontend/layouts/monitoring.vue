<template>
    <NuxtLayout name="default">
        <div class="bg-[#F1ECE3] h-full overflow-hidden flex flex-col">
            <div class="my-2 me-2 px-6 md:px-8 py-6 text-sm bg-[#FBFAF6] border border-[#E9E0D3] rounded-2xl flex-1 overflow-y-auto text-[#1f2328]">
                <h1
                    class="text-2xl font-semibold text-[#1f2328] tracking-tight"
                    style="font-family: 'Spectral', ui-serif, Georgia, serif"
                >
                    {{ $t('monitoring.title') }}
                </h1>
                <p class="mt-1 text-[#6b6b6b] leading-relaxed max-w-2xl">{{ $t('monitoring.overview.subtitle') }}</p>

                <!-- Tabs navigation -->
                <div class="border-b border-[#E9E0D3] mt-5">
                    <nav class="-mb-px flex space-x-6">
                        <NuxtLink
                            v-for="tab in visibleTabs"
                            :key="tab.name"
                            :to="`/monitoring/${tab.name}`"
                            :class="[
                                isTabActive(tab.name)
                                    ? 'border-[#C2541E] text-[#1f2328]'
                                    : 'border-transparent text-[#6b6b6b] hover:border-[#E9E0D3] hover:text-[#1f2328]',
                                'whitespace-nowrap border-b-2 py-2 px-1 text-sm font-medium flex items-center space-x-2'
                            ]"
                        >
                            <Icon :name="tab.icon" class="w-4 me-1" />
                            <span>{{ $t(tab.label) }}</span>
                        </NuxtLink>
                    </nav>
                </div>

                <!-- Page content -->
                <slot />
            </div>
        </div>
    </NuxtLayout>
</template>

<script setup lang="ts">
const route = useRoute()

// Make route path reactive
const currentPath = computed(() => route.path)

// All available tabs. Visibility mirrors the page-level gate: anyone with
// `manage` on at least one data source can see the monitoring tabs.
const allTabs = [
    { name: '', label: 'monitoring.tabExplore', icon: 'i-heroicons-chart-bar' },
    { name: 'diagnosis', label: 'monitoring.tabDiagnosis', icon: 'i-heroicons-wrench' },
    { name: 'cost', label: 'monitoring.tabCost', icon: 'i-heroicons-banknotes' },
]

const visibleTabs = computed(() => {
    if (!useCanAny('manage', 'data_source')) return []
    return allTabs
})

// Helper function to check if tab is active
const isTabActive = (tabName: string) => {
    const path = currentPath.value
    if (tabName === '') {
        // For the first tab (Explore), it's active when on /monitoring or /monitoring/
        return path === '/monitoring' || path === '/monitoring/'
    }
    return path === `/monitoring/${tabName}`
}
</script>
