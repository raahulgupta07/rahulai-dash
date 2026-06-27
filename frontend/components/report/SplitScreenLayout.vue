<template>

    <!-- dashboardFirst (URL ?focus=dashboard): visually move the dashboard panel to
         the main/left side and dock the chat narrow on the right via flex-row-reverse.
         No DOM reorder — the existing chat/panel slots are only resized + flipped. -->
    <div class="flex h-screen overflow-y-hidden bg-[#FAF8F3]"
         :class="dashboardFirst ? 'flex-row-reverse' : 'flex-row'">
        <!-- Left (Chat) — z-20 so popovers can overlap the right panel.
             In dashboardFirst mode this is the narrow right-hand chat dock
             (dockWidth px); collapses to a thin rail when dockCollapsed. -->
        <div class="relative z-20" :style="{
                width: !isSplitScreen
                    ? '100%'
                    : dashboardFirst
                        ? `${dockWidth}px`
                        : `${leftPanelWidth}px`,
                willChange: 'width',
                transition: (isResizing || dockResizing) ? 'none' : 'width 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
             }">
            <slot name="left" />
            <!-- Dashboard-first dock resizer: handle on the dock's INNER edge
                 (the edge facing the dashboard). The dock is the left slot but
                 sits visually on the right under flex-row-reverse, so its inner
                 edge is the visual LEFT edge (logical `start`). Drag computes a
                 new dock width from the pointer and emits it up. Hidden when the
                 dock is collapsed to the thin rail. -->
            <div v-if="dashboardFirst && !isDockCollapsed"
                 class="absolute start-0 top-0 bottom-0 w-[8px] cursor-col-resize z-40 group"
                 @mousedown="startDockResize">
                <div class="absolute inset-y-0 start-[2px] w-[3px] rounded-full opacity-0 group-hover:opacity-100 bg-[#C2541E] transition-opacity"></div>
            </div>
        </div>

        <!-- Right Panel -->
        <div v-if="isSplitScreen"
             :style="{
                 transition: isResizing ? 'none' : 'width 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
             }"
             class="flex-1 min-w-0 relative z-10 bg-[#FAF8F3] flex flex-col">
            <!-- Right header (tabs). Hidden in dashboardFirst mode — the board's
                 own toolbar (selector/Share/fullscreen) + the chat dock header are
                 enough; the Outputs/Dashboard/Agents/Slides/Excel tab strip is noise
                 when the view is locked to the dashboard. -->
            <div v-if="!dashboardFirst" class="flex-shrink-0 flex items-center justify-between px-3 pt-1.5">
                <slot name="right-header" />
            </div>
            <!-- Right content (rounded panel) -->
            <div class="flex-1 min-h-0 p-2 pt-1.5 relative">
                <div class="h-full w-full bg-[#FAF8F3] rounded-xl border border-[#E9E0D3] overflow-hidden">
                    <slot name="right" />
                </div>
                <!-- Resizer overlaid on rounded panel's start edge (between
                     chat pane and dashboard). Use logical `start-*` so it
                     flips to the correct visual side under RTL. -->
                <div v-if="!dashboardFirst" class="absolute start-[5px] top-0 bottom-0 w-[8px] cursor-col-resize z-30 group"
                     @mousedown="$emit('startResize', $event)">
                    <div class="absolute inset-y-0 start-[3px] w-[3px] rounded-full opacity-0 group-hover:opacity-100 bg-[#C2541E] transition-opacity"></div>
                </div>
            </div>
            <!-- Overlay to prevent iframe from capturing mouse events during resize -->
            <div v-if="isResizing" class="absolute inset-0 z-50" />
        </div>
    </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
    isSplitScreen: boolean,
    leftPanelWidth: number,
    isResizing: boolean,
    // Dashboard-first layout: flip panes (dashboard main/left, chat dock right).
    dashboardFirst?: boolean,
    // Width of the chat dock in dashboardFirst mode (px). ~360 normal, ~46 collapsed.
    dockWidth?: number,
}>(), {
    dashboardFirst: false,
    dockWidth: 360,
})

const emit = defineEmits(['startResize', 'update:dockWidth'])

// Dock collapsed = the thin rail width (~46px); hide the resizer then.
const isDockCollapsed = computed(() => (props.dockWidth ?? 360) <= 60)

// Drag-resize the chat dock (dashboard-first only). Dock width is derived from
// the pointer: window.innerWidth - clientX (dock sits flush on the right edge),
// clamped 300..560, emitted up for the parent to persist.
const DOCK_MIN = 300
const DOCK_MAX = 560
const dockResizing = ref(false)
function onDockMove(e: MouseEvent) {
    if (!dockResizing.value) return
    const w = Math.min(DOCK_MAX, Math.max(DOCK_MIN, window.innerWidth - e.clientX))
    emit('update:dockWidth', w)
}
function onDockUp() {
    dockResizing.value = false
    window.removeEventListener('mousemove', onDockMove)
    window.removeEventListener('mouseup', onDockUp)
    document.body.style.userSelect = ''
}
function startDockResize(e: MouseEvent) {
    e.preventDefault()
    dockResizing.value = true
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onDockMove)
    window.addEventListener('mouseup', onDockUp)
}
</script>

<style scoped>
.bg-dots {
    background-image: radial-gradient(circle, rgba(0, 0, 0, 0.15) 1px, #fff 1px);
    background-size: 20px 20px;
}
</style>


