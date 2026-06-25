<template>
    <div class="flex h-full text-sm w-full">
            <!-- Loading -->
            <div v-if="loading" class="flex flex-col items-center justify-center py-20 w-full">
                <Spinner class="h-4 w-4 text-gray-400" />
                <p class="text-sm text-gray-500 mt-2">{{ $t('common.loading') }}</p>
            </div>

            <!-- Not found / no access -->
            <div v-else-if="notFound" class="flex flex-col items-center justify-center py-20 text-center w-full">
                <UIcon name="i-heroicons-film" class="w-10 h-10 text-gray-300 mb-3" />
                <h3 class="text-sm font-medium text-gray-700">{{ $t('studio.notFound') }}</h3>
                <p class="mt-1 text-xs text-gray-500 max-w-md">{{ $t('studio.notFoundHint') }}</p>
                <UButton color="gray" variant="outline" size="xs" class="mt-4" @click="router.push('/studios')">
                    {{ $t('studio.backToStudios') }}
                </UButton>
            </div>

            <template v-else-if="studio">
                <!-- LEFT RAIL: studio header + grouped nav (anchored, neutral selection) -->
                <aside class="w-60 shrink-0 bg-[#FBFAF6] border-e border-[#E7E5DD] flex flex-col overflow-y-auto h-full">
                    <!-- studio header -->
                    <div class="px-3 pt-3 pb-2 border-b border-[#E7E5DD]">
                        <button class="text-[11px] text-[#9a958c] hover:text-[#6b6b6b] mb-1.5 inline-flex items-center gap-1" @click="router.push('/studios')">
                            <UIcon name="i-heroicons-arrow-left" class="w-3 h-3" /> {{ $t('studio.backToStudios') }}
                        </button>
                        <button
                            type="button"
                            class="flex items-center gap-2 w-full text-left rounded-xl -mx-1 px-1.5 py-1.5 transition-colors"
                            :class="activeTab === 'chat' ? 'bg-[#ECEAE1]' : 'hover:bg-[#faf8f3]'"
                            @click="activeTab = 'chat'"
                        >
                            <div class="shrink-0 flex items-center justify-center w-7 h-7 rounded-lg bg-[#F4F1EA] border border-[#E7E5DD] text-base text-[#C2683F] overflow-hidden">
                                <img v-if="isImageAvatar" :src="studio.avatar || ''" alt="" class="w-full h-full object-cover" />
                                <span v-else-if="studio.avatar">{{ studio.avatar }}</span>
                                <UIcon v-else name="i-heroicons-film" class="w-4 h-4 text-[#C2683F]" />
                            </div>
                            <div class="min-w-0">
                                <div class="flex items-center gap-1.5">
                                    <span class="text-sm font-semibold text-[#1f2328] truncate" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ studio.name }}</span>
                                    <span :class="scopeBadgeClass" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0">{{ scopeLabel }}</span>
                                </div>
                                <p v-if="studio.description" class="text-[11px] text-[#9a958c] truncate">{{ studio.description }}</p>
                            </div>
                        </button>
                    </div>

                    <!-- grouped nav -->
                    <nav class="px-2 py-2 flex flex-col gap-px">
                        <template v-for="g in navGroups" :key="g.key">
                            <div v-if="g.label && g.items.length" class="px-3 pt-2 pb-0.5 text-[9px] font-semibold uppercase tracking-wider text-[#9a958c]">{{ g.label }}</div>
                            <button
                                v-for="tab in g.items"
                                :key="tab.value"
                                type="button"
                                class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] text-left transition-colors"
                                :class="activeTab === tab.value
                                    ? 'bg-[#ECEAE1] text-[#1f2328] font-medium'
                                    : 'text-[#6b6b6b] hover:text-[#1f2328] hover:bg-[#faf8f3]'"
                                @click="activeTab = tab.value"
                            >
                                <UIcon :name="tab.icon" class="w-3.5 h-3.5 shrink-0" />
                                <span class="flex-1 truncate">{{ tab.label }}</span>
                                <span v-if="tab.value === 'instructions' && reviewQueueCount" class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">{{ reviewQueueCount }}</span>
                                <span v-else-if="tabCounts[tab.value]" class="text-[11px] text-[#9a958c]">{{ tabCounts[tab.value] }}</span>
                            </button>
                        </template>
                    </nav>
                </aside>

                <!-- MAIN CONTENT -->
                <main class="flex-1 min-w-0 overflow-y-auto px-8 py-6 h-full bg-[#FBFAF6]">
                    <!-- Read-only banner -->
                    <div v-if="role === 'viewer'" class="mb-4 flex items-center gap-2 text-[11px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded-lg px-3 py-1.5">
                        <UIcon name="i-heroicons-eye" class="w-3.5 h-3.5" />
                        {{ $t('studio.readOnly') }}
                    </div>

                    <div class="min-w-0">
                        <!-- CHAT -->
                        <section v-if="activeTab === 'chat'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.chatTitle') }}</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('studio.chatHint') }}</p>
                                </div>
                                <div class="flex items-center gap-2 shrink-0">
                                    <button v-if="canEdit" type="button" :disabled="improving" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors disabled:opacity-50" @click="improveNow">
                                        <Spinner v-if="improving" class="h-3.5 w-3.5" />
                                        <UIcon v-else name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F]" />
                                        {{ $t('studio.improveNow') }}
                                    </button>
                                    <button type="button" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors" @click="showShare = true">
                                        <UIcon name="i-heroicons-share" class="w-3.5 h-3.5 text-[#9a958c]" />
                                        {{ $t('studio.tabMembers') }}
                                    </button>
                                    <UTooltip :text="sources.length === 0 ? $t('studio.needSourcesForChat') : $t('studio.newChat')">
                                        <button
                                            type="button"
                                            :disabled="sources.length === 0 || creatingChat"
                                            class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-1.5 transition-colors disabled:opacity-50 disabled:hover:bg-[#C2683F]"
                                            @click="startChat"
                                        >
                                            <Spinner v-if="creatingChat" class="h-3.5 w-3.5 text-white" />
                                            <UIcon v-else name="i-heroicons-plus" class="w-3.5 h-3.5" />
                                            {{ $t('studio.newChat') }}
                                        </button>
                                    </UTooltip>
                                </div>
                            </div>

                            <!-- GROUNDED ON chip strip: per-source pill w/ status + table count + unpin -->
                            <div class="mb-5 flex flex-wrap items-center gap-2">
                                <span class="text-[10px] font-semibold uppercase tracking-wider text-[#9a958c] mr-1">{{ $t('studio.groundedOn') || 'Grounded on' }}</span>
                                <div
                                    v-for="s in sources"
                                    :key="s.id"
                                    class="group flex items-center gap-2 pl-2 pr-1.5 py-1.5 rounded-full border border-[#E7E5DD] bg-[#F4F1EA] hover:border-[#dcd9cf]"
                                >
                                    <DataSourceIcon v-if="s.type" class="h-3.5 shrink-0" :type="s.type" />
                                    <UIcon v-else name="i-heroicons-circle-stack" class="w-3.5 h-3.5 shrink-0 text-[#9a958c]" />
                                    <span class="text-xs text-[#1f2328]">{{ s.name || s.agent_id }}</span>
                                    <span class="w-1.5 h-1.5 rounded-full bg-[#3f9e6a] shrink-0" :title="$t('common.connected') || 'connected'"></span>
                                    <button
                                        v-if="canEdit"
                                        class="w-4 h-4 rounded-full text-[#9a958c] hover:text-[#6b6b6b] hover:bg-[#E7E5DD] flex items-center justify-center opacity-0 group-hover:opacity-100"
                                        :title="$t('studio.unpin')"
                                        @click="unpinSource(s.agent_id)"
                                    >
                                        <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
                                    </button>
                                </div>
                                <button
                                    v-if="canEdit"
                                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-dashed border-[#E7E5DD] text-xs text-[#6b6b6b] hover:border-[#dcd9cf] hover:text-[#1f2328]"
                                    @click="openAddSource"
                                >
                                    <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5" /> Add source
                                </button>
                            </div>

                            <div v-if="loadingChats" class="flex items-center justify-center py-10 text-[#9a958c]">
                                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                            </div>
                            <div v-else-if="chats.length === 0" class="py-12 text-center border border-dashed border-[#E7E5DD] rounded-2xl">
                                <div class="w-12 h-12 rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] flex items-center justify-center text-[#C2683F] mx-auto mb-3">
                                    <UIcon name="i-heroicons-chat-bubble-left-right" class="w-6 h-6" />
                                </div>
                                <h3 class="text-base font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.noChats') }}</h3>

                                <!-- Suggested questions: clickable chips that seed a new grounded chat -->
                                <div v-if="suggestedQuestions.length" class="mt-4 max-w-xl mx-auto">
                                    <p class="text-[11px] font-medium text-[#9a958c] uppercase tracking-wider mb-2">{{ $t('studio.suggestedQuestions') }}</p>
                                    <div class="flex flex-wrap justify-center gap-2">
                                        <button
                                            v-for="(q, i) in suggestedQuestions"
                                            :key="i"
                                            type="button"
                                            class="inline-flex items-center gap-2 text-xs text-[#1f2328] bg-white border border-[#E7E5DD] rounded-full px-3.5 py-2 hover:border-[#dcd9cf] hover:bg-[#faf8f3] transition-colors disabled:opacity-50"
                                            :disabled="sources.length === 0 || creatingChat"
                                            @click="startChat(q)"
                                        >
                                            <span class="w-1.5 h-1.5 rounded-full bg-[#C2683F] shrink-0"></span>
                                            <span class="truncate max-w-[18rem]">{{ q }}</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <ul v-else class="divide-y divide-[#E7E5DD] border border-[#E7E5DD] rounded-2xl overflow-hidden bg-white">
                                <li
                                    v-for="c in chats"
                                    :key="c.id"
                                    class="flex items-center justify-between px-3 py-2.5 bg-white hover:bg-[#faf8f3] cursor-pointer"
                                    @click="openChat(c.id)"
                                >
                                    <div class="flex items-center gap-2 min-w-0">
                                        <UIcon name="i-heroicons-chat-bubble-left-right" class="w-4 h-4 text-[#9a958c] shrink-0" />
                                        <span class="text-xs text-[#1f2328] truncate">{{ c.title || 'untitled report' }}</span>
                                    </div>
                                    <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-3.5 h-3.5 text-[#9a958c] shrink-0" />
                                </li>
                            </ul>
                        </section>

                        <!-- AI AUTO-PILOT (studio home) -->
                        <section v-else-if="activeTab === 'autopilot'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">AI Auto-pilot</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">One button trains the whole agent — columns, knowledge, joins, artifacts &amp; insights. No manual steps.</p>
                                </div>
                                <div v-if="canEdit" class="flex items-center gap-2">
                                    <div class="inline-flex items-center rounded-lg overflow-hidden border border-[#E7E5DD]">
                                        <button type="button" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white hover:bg-[#faf8f3] px-3 py-2 transition-colors" @click="openAddSource">
                                            <UIcon name="i-heroicons-link" class="w-3.5 h-3.5" /> Pin existing
                                        </button>
                                        <button type="button" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white hover:bg-[#faf8f3] px-3 py-2 border-s border-[#E7E5DD] transition-colors" @click="openUploadSource">
                                            <UIcon name="i-heroicons-arrow-up-tray" class="w-3.5 h-3.5" /> Upload file
                                        </button>
                                    </div>
                                    <button type="button" :disabled="trainingAll || !sources.length" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-2 transition-colors disabled:opacity-50" @click="runFullTrain">
                                        <Spinner v-if="trainingAll" class="h-3.5 w-3.5 text-white" />
                                        <UIcon v-else name="i-heroicons-bolt" class="w-3.5 h-3.5" />
                                        {{ trainingAll ? 'Training…' : 'Auto-train everything' }}
                                    </button>
                                </div>
                            </div>

                            <div v-if="!sources.length" class="py-10 text-center border border-dashed border-[#E7E5DD] rounded-2xl">
                                <UIcon name="i-heroicons-sparkles" class="w-7 h-7 mx-auto text-[#9a958c] mb-1.5" />
                                <p class="text-xs text-[#6b6b6b]">Pin a source under <button class="text-[#C2683F] font-medium" @click="activeTab='sources'">Sources &amp; Data</button> to begin.</p>
                            </div>

                            <template v-else>
                                <!-- READINESS HERO -->
                                <div class="flex items-center gap-4 rounded-2xl border border-[#E8C9B5] bg-gradient-to-br from-[#FBF6F2] to-white p-4 mb-4">
                                    <div class="relative w-[84px] h-[84px] shrink-0">
                                        <svg width="84" height="84" style="transform:rotate(-90deg)">
                                            <circle cx="42" cy="42" r="36" stroke="#F0E2D7" stroke-width="9" fill="none" />
                                            <circle cx="42" cy="42" r="36" stroke="#C2683F" stroke-width="9" fill="none" stroke-linecap="round" stroke-dasharray="226" :stroke-dashoffset="readinessOffset" style="transition:stroke-dashoffset .5s" />
                                        </svg>
                                        <div class="absolute inset-0 flex flex-col items-center justify-center">
                                            <span class="text-xl font-semibold" style="font-family: ui-serif, Georgia, serif">{{ readiness.score }}</span>
                                            <span class="text-[9px] uppercase tracking-wide text-[#9a958c]">ready</span>
                                        </div>
                                    </div>
                                    <div class="flex-1 min-w-0">
                                        <h3 class="text-sm font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, serif">{{ readiness.score >= 70 ? 'Agent is grounded & answering' : 'Agent needs training' }}</h3>
                                        <p class="text-[11px] text-[#9a958c] mt-0.5">AI keeps it current — re-runs profiling, joins, artifacts &amp; insights on every train.</p>
                                        <div class="flex flex-wrap gap-1.5 mt-2">
                                            <span v-for="(c, i) in readiness.checks" :key="i" class="text-[11px] inline-flex items-center gap-1 px-2 py-0.5 rounded-full border" :class="c.done ? 'border-[#cde6d8] bg-[#E7F2EC] text-[#2f7a52]' : 'border-[#E8C9B5] bg-[#FBF6F2] text-[#A8542F]'">
                                                {{ c.done ? '✓' : '○' }} {{ c.label }}<template v-if="!c.done && c.hint"> · {{ c.hint }}</template>
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <!-- STAT GRID -->
                                <div class="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-4">
                                    <div class="rounded-xl border border-[#E7E5DD] bg-white px-3 py-2.5"><div class="text-lg font-bold" style="font-family: ui-serif, Georgia, serif">{{ profiledCols }}</div><div class="text-[10px] uppercase tracking-wide text-[#9a958c]">Columns trained</div></div>
                                    <div class="rounded-xl border border-[#E7E5DD] bg-white px-3 py-2.5"><div class="text-lg font-bold" style="font-family: ui-serif, Georgia, serif">{{ docs.length }}</div><div class="text-[10px] uppercase tracking-wide text-[#9a958c]">Knowledge docs</div></div>
                                    <div class="rounded-xl border border-[#E7E5DD] bg-white px-3 py-2.5"><div class="text-lg font-bold" style="font-family: ui-serif, Georgia, serif">{{ activeInstr }}·{{ activeExamples }}</div><div class="text-[10px] uppercase tracking-wide text-[#9a958c]">Instr · Examples</div></div>
                                    <div class="rounded-xl border border-[#E7E5DD] bg-white px-3 py-2.5"><div class="text-lg font-bold" style="font-family: ui-serif, Georgia, serif">{{ studioArtifactCount }}</div><div class="text-[10px] uppercase tracking-wide text-[#9a958c]">Artifacts</div></div>
                                </div>

                                <!-- CONNECTED SOURCES COCKPIT -->
                                <div class="flex items-center justify-between mb-2">
                                    <h3 class="text-sm font-semibold text-[#1f2328] flex items-center gap-1.5" style="font-family: ui-serif, Georgia, serif"><UIcon name="i-heroicons-signal" class="w-4 h-4 text-[#C2683F]" /> Connected data</h3>
                                    <button type="button" class="text-[11px] text-[#C2683F] hover:text-[#A8542F] font-medium" @click="activeTab='sources'">Manage →</button>
                                </div>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 mb-4">
                                    <div v-for="s in sources" :key="s.id" class="rounded-xl border border-[#E7E5DD] bg-white p-3 flex items-center gap-3">
                                        <span class="w-8 h-8 rounded-lg bg-[#FBF6F2] text-[#C2683F] flex items-center justify-center shrink-0">
                                            <DataSourceIcon v-if="s.type" class="h-4" :type="s.type" />
                                            <UIcon v-else name="i-heroicons-circle-stack" class="w-4 h-4" />
                                        </span>
                                        <div class="min-w-0 flex-1">
                                            <div class="flex items-center gap-1.5">
                                                <span class="w-1.5 h-1.5 rounded-full" :class="intelFor(s.agent_id).tables.length ? 'bg-[#3f9e6a]' : 'bg-[#d8b48f]'"></span>
                                                <span class="text-[13px] font-semibold text-[#1f2328] truncate">{{ s.name || s.agent_id }}</span>
                                            </div>
                                            <div class="text-[11px] text-[#9a958c] mt-0.5">
                                                {{ s.type || 'data agent' }} ·
                                                <template v-if="intelFor(s.agent_id).tables.length">{{ intelFor(s.agent_id).tables.length }} table{{ intelFor(s.agent_id).tables.length === 1 ? '' : 's' }} · {{ intelFor(s.agent_id).tables.reduce((a,t)=>a+(t.columns?.length||0),0) }} cols · <span class="text-[#3f9e6a] font-medium">trained</span></template>
                                                <template v-else><span class="text-[#A8542F] font-medium">not trained</span> — run Auto-train</template>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- CAPABILITY MAP -->
                                <h3 class="text-sm font-semibold text-[#1f2328] mb-2 flex items-center gap-1.5" style="font-family: ui-serif, Georgia, serif"><UIcon name="i-heroicons-squares-2x2" class="w-4 h-4 text-[#C2683F]" /> What the AI handles</h3>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 mb-4">
                                    <div v-for="cap in capabilities" :key="cap.key" class="rounded-xl border border-[#E7E5DD] bg-white p-3" :class="cap.go ? 'cursor-pointer hover:border-[#E8C9B5]' : ''" @click="cap.go && (activeTab = cap.go)">
                                        <div class="flex items-center gap-2 mb-1">
                                            <span class="w-7 h-7 rounded-lg bg-[#FBF6F2] text-[#C2683F] flex items-center justify-center shrink-0"><UIcon :name="cap.icon" class="w-4 h-4" /></span>
                                            <span class="text-[13px] font-semibold text-[#1f2328]">{{ cap.title }}</span>
                                            <span class="ms-auto text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full" :class="cap.tag === 'auto' ? 'bg-[#E7F2EC] text-[#2f7a52]' : cap.tag === 'off' ? 'bg-[#F3F0E9] text-[#9a958c]' : 'bg-[#EEF1F4] text-[#475569]'">{{ cap.tag === 'auto' ? 'Auto' : cap.tag === 'off' ? 'Not needed' : 'Manual' }}</span>
                                        </div>
                                        <p class="text-[11.5px] text-[#6b6b6b]">{{ cap.desc }}</p>
                                        <p class="text-[11px] text-[#9a958c] mt-1.5">{{ cap.meta }}</p>
                                    </div>
                                </div>

                                <!-- AI SUGGESTIONS -->
                                <div v-if="aiSuggestions.length" class="rounded-2xl border border-dashed border-[#E8C9B5] bg-[#FBF6F2] p-4">
                                    <h3 class="text-[13px] font-semibold text-[#1f2328] mb-1 flex items-center gap-1.5" style="font-family: ui-serif, Georgia, serif"><UIcon name="i-heroicons-sparkles" class="w-4 h-4 text-[#C2683F]" /> AI suggestions</h3>
                                    <div v-for="(sg, i) in aiSuggestions" :key="i" class="flex items-start gap-2.5 py-2 border-b border-[#F4E5DA] last:border-0">
                                        <span class="text-[#C2683F] mt-0.5">✦</span>
                                        <span class="flex-1 text-[12px] text-[#1f2328]">{{ sg.text }}</span>
                                        <button v-if="canEdit" type="button" class="text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-white border border-[#E8C9B5] text-[#C2683F] hover:bg-[#F6EFEA] shrink-0" @click="doSuggestion(sg.fn)">{{ sg.action }}</button>
                                    </div>
                                </div>
                            </template>
                        </section>

                        <!-- SOURCES -->
                        <section v-else-if="activeTab === 'sources'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Sources &amp; Knowledge</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">Each data agent plus the docs that ground it. Add definitions per source, or org-wide below.</p>
                                </div>
                                <div v-if="canEdit" class="inline-flex items-center rounded-lg overflow-hidden border border-[#C2683F]">
                                    <button type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] px-3.5 py-1.5 transition-colors" @click="openAddSource">
                                        <UIcon name="i-heroicons-link" class="w-3.5 h-3.5" />
                                        Pin existing
                                    </button>
                                    <button type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] px-3.5 py-1.5 border-s border-[#A8542F] transition-colors" @click="openUploadSource">
                                        <UIcon name="i-heroicons-arrow-up-tray" class="w-3.5 h-3.5" />
                                        Upload file
                                    </button>
                                </div>
                            </div>

                            <!-- PRE-TRAIN HERO (Column Intelligence) -->
                            <div v-if="canEdit && sources.length" class="rounded-2xl border border-[#E8C9B5] bg-gradient-to-br from-[#FBF3EC] to-white p-4 mb-4">
                                <div class="flex items-center gap-3 flex-wrap">
                                    <div class="shrink-0 w-11 h-11 rounded-xl bg-[#C2683F] text-white flex items-center justify-center">
                                        <UIcon name="i-heroicons-cpu-chip" class="w-6 h-6" />
                                    </div>
                                    <div class="flex-1 min-w-[200px]">
                                        <h3 class="text-sm font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Auto-train this studio</h3>
                                        <p class="text-[11px] text-[#9a958c] mt-0.5">Profiles every column, learns real values, extracts docs, mines joins &amp; regenerates insights — all applied live. No approve step.</p>
                                    </div>
                                    <button type="button" :disabled="pretraining" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-2 transition-colors disabled:opacity-50" @click="runStudioPretrain">
                                        <Spinner v-if="pretraining" class="h-3.5 w-3.5 text-white" />
                                        <UIcon v-else name="i-heroicons-bolt" class="w-3.5 h-3.5" />
                                        {{ pretraining ? 'Training…' : 'Auto-train now' }}
                                    </button>
                                </div>
                                <div v-if="pretrainResult" class="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                                    <span class="px-2 py-0.5 rounded-full bg-white border border-[#E7E5DD] text-[#6b6b6b]">{{ Number(pretrainResult.row_count || 0).toLocaleString() }} rows</span>
                                    <span class="px-2 py-0.5 rounded-full bg-white border border-[#E7E5DD] text-[#6b6b6b]">{{ pretrainResult.columns_written }} columns</span>
                                    <span v-if="pretrainResult.knowledge" class="px-2 py-0.5 rounded-full bg-green-100 text-green-700">{{ pretrainResult.knowledge }} knowledge</span>
                                    <span class="text-[#9a958c]">across {{ pretrainResult.sources }} source{{ pretrainResult.sources === 1 ? '' : 's' }}</span>
                                </div>
                            </div>

                            <!-- empty: no sources pinned at all -->
                            <div v-if="sources.length === 0" class="py-10 text-center border border-dashed border-[#E7E5DD] rounded-2xl">
                                <UIcon name="i-heroicons-circle-stack" class="w-7 h-7 mx-auto text-[#9a958c] mb-1.5" />
                                <p class="text-xs text-[#6b6b6b]">{{ $t('studio.noSources') }}</p>
                            </div>

                            <!-- knowledge flag off -->
                            <div v-if="docsDisabled" class="mb-4 flex items-center gap-2 text-[11px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded-lg px-3 py-2">
                                <UIcon name="i-heroicons-information-circle" class="w-3.5 h-3.5 text-[#9a958c]" />
                                Enable Knowledge Docs in Settings → Feature Flags to add definitions.
                            </div>

                            <!-- PER-SOURCE CARDS: a data agent + the docs that ground it -->
                            <div v-if="sources.length" class="space-y-3">
                                <div v-for="s in sources" :key="s.id" class="rounded-2xl border border-[#E7E5DD] bg-white overflow-hidden">
                                    <div class="flex items-center justify-between gap-2 px-4 py-3 border-b border-[#F0EEE6]">
                                        <div class="flex items-center gap-2 min-w-0">
                                            <DataSourceIcon v-if="s.type" class="h-4 shrink-0" :type="s.type" />
                                            <UIcon v-else name="i-heroicons-circle-stack" class="w-4 h-4 shrink-0 text-[#C2683F]" />
                                            <span class="text-sm font-medium text-[#1f2328] truncate">{{ s.name || s.agent_id }}</span>
                                            <span v-if="docsForSource(s.agent_id).length" class="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[#F4F1EA] text-[#6b6b6b]">{{ docsForSource(s.agent_id).length }} doc{{ docsForSource(s.agent_id).length === 1 ? '' : 's' }}</span>
                                        </div>
                                        <UButton v-if="canEdit" color="gray" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="unpinSource(s.agent_id)">{{ $t('studio.unpin') }}</UButton>
                                    </div>

                                    <!-- in-card tabs: Tables · Knowledge · Insights · Connection -->
                                    <div class="flex items-center gap-1 px-3 pt-2 border-b border-[#F0EEE6]">
                                        <button v-for="ctb in cardTabDefs" :key="ctb.k" type="button"
                                            class="text-[12px] px-3 py-1.5 border-b-2 transition-colors flex items-center gap-1.5"
                                            :class="cardTabOf(s.agent_id) === ctb.k ? 'border-[#C2683F] text-[#1f2328] font-semibold' : 'border-transparent text-[#6b6b6b] hover:text-[#1f2328]'"
                                            @click="setCardTab(s.agent_id, ctb.k)">
                                            {{ ctb.label }}
                                            <span v-if="ctb.k === 'tables' && intelFor(s.agent_id).tables.length" class="text-[10px] font-semibold bg-[#F4E5DA] text-[#A8542F] rounded-full px-1.5">{{ intelFor(s.agent_id).tables.length }}</span>
                                            <span v-else-if="ctb.k === 'knowledge' && docsForSource(s.agent_id).length" class="text-[10px] font-semibold bg-[#F4E5DA] text-[#A8542F] rounded-full px-1.5">{{ docsForSource(s.agent_id).length }}</span>
                                            <span v-else-if="ctb.k === 'insights' && insightsFor(s.agent_id).length" class="text-[10px] font-semibold bg-[#F4E5DA] text-[#A8542F] rounded-full px-1.5">{{ insightsFor(s.agent_id).length }}</span>
                                        </button>
                                    </div>

                                    <!-- TABLES pane -->
                                    <div v-show="cardTabOf(s.agent_id) === 'tables'" class="px-4 py-3">
                                        <div v-if="intelFor(s.agent_id).loading" class="flex items-center gap-2 text-[11px] text-[#9a958c] py-4"><Spinner class="h-3.5 w-3.5" /> Loading schema…</div>
                                        <div v-else-if="intelFor(s.agent_id).disabled" class="text-[11px] text-[#9a958c] py-3">Enable Column Intelligence in Settings → Feature Flags to profile tables.</div>
                                        <div v-else-if="!intelFor(s.agent_id).tables.length" class="text-[11px] text-[#9a958c] py-3">No tables yet — run Auto-train to profile this source.</div>
                                        <div v-for="tb in intelFor(s.agent_id).tables" :key="tb.table_id" class="mb-4 last:mb-0">
                                            <div class="text-[12px] font-semibold text-[#1f2328] flex items-center gap-1.5 mb-1.5">
                                                <UIcon name="i-heroicons-table-cells" class="w-3.5 h-3.5 text-[#C2683F]" />
                                                {{ tb.table_name }}
                                                <span class="font-normal text-[11px] text-[#9a958c]">· {{ tb.columns.length }} cols</span>
                                            </div>
                                            <div class="overflow-x-auto rounded-lg border border-[#F0EEE6]">
                                                <table class="w-full text-[12px]">
                                                    <thead>
                                                        <tr class="text-[10px] uppercase tracking-wide text-[#9a958c] bg-[#FBFAF6]">
                                                            <th class="text-left font-semibold px-2.5 py-1.5">Column</th>
                                                            <th class="text-left font-semibold px-2.5 py-1.5">Role</th>
                                                            <th class="text-left font-semibold px-2.5 py-1.5">Distinct</th>
                                                            <th class="text-left font-semibold px-2.5 py-1.5">Sample values</th>
                                                            <th class="text-right font-semibold px-2.5 py-1.5">Null</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        <tr v-for="c in tb.columns" :key="c.name" class="border-t border-[#F0EEE6] align-top">
                                                            <td class="px-2.5 py-1.5">
                                                                <span class="font-medium text-[#1f2328] inline-flex items-center gap-1.5">
                                                                    <span v-if="c.description" class="w-1.5 h-1.5 rounded-full bg-[#3f9e6a]" :title="c.description"></span>
                                                                    {{ c.name }}
                                                                </span>
                                                            </td>
                                                            <td class="px-2.5 py-1.5"><span v-if="c.role" :class="roleClass(c.role)" class="text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded">{{ c.role }}</span></td>
                                                            <td class="px-2.5 py-1.5 text-[#6b6b6b] tabular-nums">{{ c.distinct ?? '—' }}</td>
                                                            <td class="px-2.5 py-1.5 text-[#6b6b6b]">
                                                                <span v-if="c.values && c.values.length">{{ c.values.slice(0,4).join(' · ') }}<span v-if="c.values.length > 4" class="text-[#9a958c]"> +{{ c.values.length - 4 }}</span></span>
                                                                <span v-else-if="c.min != null || c.max != null">{{ c.min }} … {{ c.max }}</span>
                                                                <span v-else class="text-[#c5c0b6]">—</span>
                                                            </td>
                                                            <td class="px-2.5 py-1.5 text-right tabular-nums" :class="nullClass(c.null_pct)">{{ fmtNull(c.null_pct) }}<span v-if="(c.null_pct||0) >= 50"> ⚠</span></td>
                                                        </tr>
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                        <p class="text-[11px] text-[#9a958c] mt-2 flex items-center gap-1.5"><UIcon name="i-heroicons-information-circle" class="w-3.5 h-3.5" /> Roles, values &amp; nulls auto-detected on train. Green dot = described by a doc.</p>
                                    </div>

                                    <!-- KNOWLEDGE pane -->
                                    <div v-show="cardTabOf(s.agent_id) === 'knowledge'" class="px-4 py-3">
                                        <div class="flex items-center justify-end gap-1 mb-2" v-if="canEdit">
                                            <button type="button" class="inline-flex items-center gap-1 text-[11px] font-medium text-[#C2683F] hover:text-[#A8542F] rounded-md px-2 py-1 hover:bg-[#F6EFEA] transition-colors" @click="openAddKnowledge(s.agent_id)">
                                                <UIcon name="i-heroicons-plus" class="w-3 h-3" /> Add
                                            </button>
                                            <button type="button" class="inline-flex items-center gap-1 text-[11px] font-medium text-[#6b6b6b] hover:text-[#1f2328] rounded-md px-2 py-1 hover:bg-[#faf8f3] transition-colors" @click="openAutoConfigure(s.agent_id)">
                                                <UIcon name="i-heroicons-arrow-up-tray" class="w-3 h-3" /> From doc
                                            </button>
                                        </div>
                                        <div v-if="addTarget === String(s.agent_id)" class="rounded-xl border border-[#E8C9B5] bg-[#FBF6F2] p-3 mb-2 space-y-2">
                                            <UInput v-model="newDoc.title" size="sm" placeholder="Title — e.g. Brand definitions" />
                                            <UTextarea v-model="newDoc.body" :rows="3" size="sm" placeholder="Paste the definition or note…" />
                                            <div class="flex items-center justify-end gap-2">
                                                <UButton color="gray" variant="ghost" size="2xs" @click="closeAddKnowledge">Cancel</UButton>
                                                <UButton color="orange" size="2xs" :loading="savingDoc" :disabled="!newDoc.title.trim() || !newDoc.body.trim()" @click="createDoc">Add</UButton>
                                            </div>
                                        </div>
                                        <ul v-if="docsForSource(s.agent_id).length" class="space-y-1.5">
                                            <li v-for="d in docsForSource(s.agent_id)" :key="d.id" class="flex items-start justify-between gap-3 rounded-lg border border-[#F0EEE6] bg-[#FBFAF6] px-3 py-2">
                                                <div class="min-w-0 flex-1">
                                                    <div class="flex items-center gap-2">
                                                        <span :class="docStatusBadgeClass(d.status)" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded">{{ d.status === 'approved' ? $t('studio.statusActive') : $t('studio.statusPending') }}</span>
                                                        <span class="text-xs font-medium text-[#1f2328] truncate">{{ d.title }}</span>
                                                    </div>
                                                    <p class="text-[11px] text-[#9a958c] mt-0.5">{{ d.source || 'paste' }}<template v-if="d.chunks"> · {{ d.chunks }} chunks</template></p>
                                                </div>
                                                <div v-if="canEdit && d.status !== 'approved'" class="flex items-center gap-1 shrink-0">
                                                    <UButton color="green" variant="soft" size="2xs" icon="i-heroicons-check" @click="approveDoc(d)">{{ $t('studio.approve') }}</UButton>
                                                    <UButton v-if="!docRejectHidden" color="red" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="rejectDoc(d)">{{ $t('studio.reject') }}</UButton>
                                                </div>
                                            </li>
                                        </ul>
                                        <p v-else-if="addTarget !== String(s.agent_id)" class="text-[11px] text-[#9a958c]">No knowledge yet — add a definition or upload a doc to ground this agent.</p>
                                    </div>

                                    <!-- INSIGHTS pane -->
                                    <div v-show="cardTabOf(s.agent_id) === 'insights'" class="px-4 py-3">
                                        <ul v-if="insightsFor(s.agent_id).length" class="space-y-0.5">
                                            <li v-for="(ins, i) in insightsFor(s.agent_id)" :key="i" class="flex items-start gap-2 text-[12px] py-1.5 border-b border-[#F0EEE6] last:border-0">
                                                <span class="text-[#C2683F] shrink-0">✦</span><span class="text-[#1f2328]">{{ ins }}</span>
                                            </li>
                                        </ul>
                                        <p v-else class="text-[11px] text-[#9a958c] py-3">No insights yet — run Auto-train to profile this source.</p>
                                        <p v-if="insightsFor(s.agent_id).length" class="text-[11px] text-[#9a958c] mt-2 flex items-center gap-1.5"><UIcon name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F]" /> Auto-derived from the column profile. Refreshed each train.</p>
                                    </div>

                                    <!-- CONNECTION pane -->
                                    <div v-show="cardTabOf(s.agent_id) === 'connection'" class="px-4 py-3">
                                        <table class="w-full text-[12px]">
                                            <tbody>
                                                <tr><td class="py-1.5 text-[#9a958c] w-32">Type</td><td class="py-1.5 text-[#1f2328]">{{ s.type || 'data agent' }}</td></tr>
                                                <tr><td class="py-1.5 text-[#9a958c]">Status</td><td class="py-1.5 text-[#1f2328]"><span class="inline-block w-1.5 h-1.5 rounded-full bg-[#3f9e6a] me-1.5"></span>connected</td></tr>
                                                <tr><td class="py-1.5 text-[#9a958c]">Tables</td><td class="py-1.5 text-[#1f2328]">{{ intelFor(s.agent_id).tables.length }} active</td></tr>
                                                <tr><td class="py-1.5 text-[#9a958c]">Agent id</td><td class="py-1.5 text-[#6b6b6b] font-mono text-[11px]">{{ s.agent_id }}</td></tr>
                                            </tbody>
                                        </table>
                                        <div class="mt-3 flex gap-2" v-if="canEdit">
                                            <button type="button" class="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3]" @click="refreshSchema(s.agent_id)">
                                                <UIcon name="i-heroicons-arrow-path" class="w-3.5 h-3.5" /> Refresh schema
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- ORG-WIDE KNOWLEDGE (not tied to one agent) -->
                            <div v-if="sources.length" class="rounded-2xl border border-dashed border-[#E7E5DD] bg-[#FBFAF6] mt-3 px-4 py-3">
                                <div class="flex items-center justify-between mb-2">
                                    <div class="flex items-center gap-2">
                                        <UIcon name="i-heroicons-globe-alt" class="w-4 h-4 text-[#9a958c]" />
                                        <span class="text-sm font-medium text-[#1f2328]">Org-wide knowledge</span>
                                        <span v-if="orgDocs.length" class="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[#F4F1EA] text-[#6b6b6b]">{{ orgDocs.length }}</span>
                                    </div>
                                    <button v-if="canEdit" type="button" class="inline-flex items-center gap-1 text-[11px] font-medium text-[#C2683F] hover:text-[#A8542F] rounded-md px-2 py-1 hover:bg-[#F6EFEA] transition-colors" @click="openAddKnowledge(null)">
                                        <UIcon name="i-heroicons-plus" class="w-3 h-3" /> Add
                                    </button>
                                </div>
                                <p class="text-[11px] text-[#9a958c] mb-2">Glossaries &amp; policies shared across every agent in this org.</p>

                                <div v-if="addTarget === '__org__'" class="rounded-xl border border-[#E8C9B5] bg-[#FBF6F2] p-3 mb-2 space-y-2">
                                    <UInput v-model="newDoc.title" size="sm" placeholder="Title — e.g. Revenue definition" />
                                    <UTextarea v-model="newDoc.body" :rows="3" size="sm" placeholder="Paste the definition or note…" />
                                    <div class="flex items-center justify-end gap-2">
                                        <UButton color="gray" variant="ghost" size="2xs" @click="closeAddKnowledge">Cancel</UButton>
                                        <UButton color="orange" size="2xs" :loading="savingDoc" :disabled="!newDoc.title.trim() || !newDoc.body.trim()" @click="createDoc">Add</UButton>
                                    </div>
                                </div>

                                <ul v-if="orgDocs.length" class="space-y-1.5">
                                    <li v-for="d in orgDocs" :key="d.id" class="flex items-start justify-between gap-3 rounded-lg border border-[#F0EEE6] bg-white px-3 py-2">
                                        <div class="min-w-0 flex-1">
                                            <div class="flex items-center gap-2">
                                                <span :class="docStatusBadgeClass(d.status)" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded">{{ d.status === 'approved' ? $t('studio.statusActive') : $t('studio.statusPending') }}</span>
                                                <span class="text-xs font-medium text-[#1f2328] truncate">{{ d.title }}</span>
                                            </div>
                                            <p class="text-[11px] text-[#9a958c] mt-0.5">{{ d.source || 'paste' }}<template v-if="d.chunks"> · {{ d.chunks }} chunks</template></p>
                                        </div>
                                        <div v-if="canEdit && d.status !== 'approved'" class="flex items-center gap-1 shrink-0">
                                            <UButton color="green" variant="soft" size="2xs" icon="i-heroicons-check" @click="approveDoc(d)">{{ $t('studio.approve') }}</UButton>
                                            <UButton v-if="!docRejectHidden" color="red" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="rejectDoc(d)">{{ $t('studio.reject') }}</UButton>
                                        </div>
                                    </li>
                                </ul>
                            </div>

                            <!-- FEDERATION — auto-mined cross-source joins -->
                            <div v-if="sources.length" class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mt-3">
                                <div class="flex items-center justify-between gap-2 mb-1">
                                    <div class="flex items-center gap-1.5">
                                        <UIcon name="i-heroicons-arrows-right-left" class="w-4 h-4 text-[#C2683F]" />
                                        <h3 class="text-sm font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Federation</h3>
                                        <span class="text-[11px] text-[#9a958c]">· query across sources</span>
                                    </div>
                                    <button v-if="canEdit && !joinsDisabled" type="button" :disabled="miningJoins" class="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] disabled:opacity-50" @click="mineJoins">
                                        <Spinner v-if="miningJoins" class="h-3.5 w-3.5" /><UIcon v-else name="i-heroicons-magnifying-glass" class="w-3.5 h-3.5" /> Mine joins
                                    </button>
                                </div>
                                <p class="text-[11px] text-[#9a958c] mb-2.5">Joins auto-mined from proven SQL (% = confidence · ×N = times seen). High-confidence joins auto-enable on Auto-train; enable the rest yourself.</p>
                                <div v-if="joinsDisabled" class="text-[11px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded-lg px-3 py-2 flex items-center gap-2">
                                    <UIcon name="i-heroicons-information-circle" class="w-3.5 h-3.5 text-[#9a958c]" /> Enable Join Graph in Settings → Feature Flags.
                                </div>
                                <div v-else-if="!joinEdges.length" class="text-[11px] text-[#9a958c] py-2">No joins yet — run answers across sources, then Mine joins.</div>
                                <div v-else class="space-y-1.5">
                                    <div v-for="e in joinEdges" :key="e.id" class="flex items-center gap-2 text-[12px] rounded-lg border border-[#F0EEE6] bg-[#FBFAF6] px-3 py-2">
                                        <code class="text-[11px] bg-white border border-[#F0EEE6] rounded px-1.5 py-0.5">{{ e.left_table }}.{{ e.left_col }}</code>
                                        <span class="text-[#9a958c]">⋈</span>
                                        <code class="text-[11px] bg-white border border-[#F0EEE6] rounded px-1.5 py-0.5">{{ e.right_table }}.{{ e.right_col }}</code>
                                        <span class="ms-auto text-[11px] text-[#9a958c] tabular-nums">{{ Math.round((e.confidence||0)*100) }}% · {{ e.join_count }}×</span>
                                        <span v-if="e.status === 'approved'" class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700">live</span>
                                        <button v-else-if="canEdit" type="button" class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#F4F1EA] border border-[#E7E5DD] text-[#6b6b6b] hover:bg-[#F6EFEA]" @click="approveJoin(e)">enable</button>
                                    </div>
                                </div>
                            </div>

                            <!-- STUDIO INSIGHTS — auto-derived across sources -->
                            <div v-if="sources.length && studioInsights.length" class="rounded-2xl border border-dashed border-[#E7E5DD] bg-[#FBFAF6] p-4 mt-3">
                                <div class="flex items-center gap-1.5 mb-1">
                                    <UIcon name="i-heroicons-sparkles" class="w-4 h-4 text-[#C2683F]" />
                                    <h3 class="text-sm font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Studio insights</h3>
                                    <span class="text-[11px] text-[#9a958c]">· auto-generated</span>
                                </div>
                                <ul class="space-y-0.5">
                                    <li v-for="(ins, i) in studioInsights" :key="i" class="flex items-start gap-2 text-[12px] py-1.5 border-b border-[#F0EEE6] last:border-0">
                                        <span class="text-[#C2683F] shrink-0">✦</span><span class="text-[#1f2328]">{{ ins }}</span>
                                    </li>
                                </ul>
                            </div>

                            <!-- AUTO-CONFIGURE FROM DOCUMENT (Feature 1) — one shared block, mapped via the card "From doc" button -->
                            <div v-if="canEdit && sources.length" id="studio-autoconfigure" class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mt-3">
                                <div class="flex items-start justify-between gap-3 mb-3">
                                    <div>
                                        <div class="flex items-center gap-1.5">
                                            <UIcon name="i-heroicons-sparkles" class="w-4 h-4 text-[#C2683F]" />
                                            <h3 class="text-sm font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Auto-configure from document</h3>
                                        </div>
                                        <p class="text-[11px] text-[#9a958c] mt-0.5">Upload .xlsx / .pptx — we extract column descriptions, instructions &amp; examples, then you review before applying.</p>
                                    </div>
                                </div>

                                <!-- disabled hint -->
                                <div v-if="acDisabled" class="mb-3 flex items-center gap-2 text-[11px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded-lg px-3 py-2">
                                    <UIcon name="i-heroicons-information-circle" class="w-3.5 h-3.5 text-[#9a958c]" />
                                    Auto-configure is disabled. Enable it in Settings → Feature Flags.
                                </div>

                                <template v-else>
                                    <!-- dropzone / file input -->
                                    <input ref="acFileInput" type="file" accept=".xlsx,.pptx" multiple class="hidden" @change="onAcFileInput" />
                                    <div
                                        @dragover.prevent="acDragging = true"
                                        @dragenter.prevent="acDragging = true"
                                        @dragleave.prevent="acDragging = false"
                                        @drop.prevent="onAcDrop"
                                        @click="$refs.acFileInput.click()"
                                        :class="[
                                            'cursor-pointer rounded-xl border-2 border-dashed transition-all',
                                            acDragging ? 'border-[#C2683F] bg-[#F6EFEA]' : 'border-[#E8C9B5] hover:border-[#C2683F] hover:bg-[#F6EFEA]'
                                        ]"
                                    >
                                        <div class="flex flex-col items-center justify-center py-6 px-4 text-center">
                                            <UIcon name="i-heroicons-cloud-arrow-up" :class="['w-8 h-8', acDragging ? 'text-[#C2683F]' : 'text-[#A8542F]']" />
                                            <span class="mt-2 text-xs font-medium text-[#C2683F]">{{ acDragging ? 'Drop files here' : 'Click or drag .xlsx / .pptx files' }}</span>
                                            <span class="mt-0.5 text-[11px] text-[#9a958c]">Multiple files supported</span>
                                        </div>
                                    </div>

                                    <!-- selected files -->
                                    <ul v-if="acFiles.length" class="mt-3 space-y-1.5">
                                        <li v-for="(f, i) in acFiles" :key="i" class="flex items-center justify-between gap-3 rounded-lg border border-[#E7E5DD] bg-[#F4F1EA] px-2.5 py-1.5">
                                            <div class="flex items-center gap-2 min-w-0">
                                                <span class="inline-flex items-center justify-center w-6 h-6 rounded bg-white border border-[#E7E5DD] shrink-0">
                                                    <Spinner v-if="f.uploading" class="w-3 h-3 text-[#C2683F]" />
                                                    <UIcon v-else-if="f.error" name="i-heroicons-x-circle" class="w-3.5 h-3.5 text-red-500" />
                                                    <UIcon v-else-if="f.fileId" name="i-heroicons-document-check" class="w-3.5 h-3.5 text-[#3f9e6a]" />
                                                    <UIcon v-else name="i-heroicons-document" class="w-3.5 h-3.5 text-[#9a958c]" />
                                                </span>
                                                <span class="text-xs text-[#1f2328] truncate">{{ f.name }}</span>
                                                <span v-if="f.error" class="text-[10px] text-red-600">{{ f.error }}</span>
                                            </div>
                                            <button class="text-[#9a958c] hover:text-[#6b6b6b] shrink-0" @click.stop="removeAcFile(i)">
                                                <UIcon name="i-heroicons-x-mark" class="w-3.5 h-3.5" />
                                            </button>
                                        </li>
                                    </ul>

                                    <!-- mapped source (set by the card "From doc" button) + analyze -->
                                    <div class="mt-3 flex items-center justify-between gap-2">
                                        <div class="flex items-center gap-1.5 text-[11px] text-[#6b6b6b] min-w-0">
                                            <span class="text-[#9a958c]">Mapping to</span>
                                            <span class="inline-flex items-center gap-1 font-medium text-[#1f2328] px-2 py-0.5 rounded-full bg-[#F4F1EA] border border-[#E7E5DD] truncate">
                                                <UIcon name="i-heroicons-circle-stack" class="w-3 h-3 text-[#C2683F]" />
                                                {{ (sources.find(s => String(s.agent_id) === String(acSourceId))?.name) || acSourceId || '—' }}
                                            </span>
                                        </div>
                                        <UButton
                                            color="orange"
                                            size="sm"
                                            :loading="acAnalyzing"
                                            :disabled="!acReady"
                                            @click="acAnalyze"
                                        >
                                            Analyze
                                        </UButton>
                                    </div>
                                    <p v-if="acSourceOptions.length === 0" class="mt-1.5 text-[11px] text-[#9a958c]">Pin a data source first to map columns.</p>
                                    <p v-if="acError" class="mt-2 flex items-start gap-1.5 text-xs text-red-600">
                                        <UIcon name="i-heroicons-exclamation-circle" class="w-4 h-4 shrink-0 mt-px" />
                                        <span>{{ acError }}</span>
                                    </p>

                                    <!-- REVIEW panel -->
                                    <div v-if="acProposal" class="mt-4 border-t border-[#E7E5DD] pt-4 space-y-4">
                                        <!-- matched column descriptions -->
                                        <div v-if="acColumns.length">
                                            <p class="text-[11px] font-semibold uppercase tracking-wider text-[#9a958c] mb-2">Column descriptions ({{ acColumnsChecked }} of {{ acColumns.length }})</p>
                                            <ul class="space-y-1.5">
                                                <li v-for="(c, i) in acColumns" :key="'c'+i" class="flex items-start gap-2 rounded-lg border border-[#E7E5DD] bg-white p-2">
                                                    <UCheckbox v-model="c.include" :disabled="!c.matched" class="mt-0.5" />
                                                    <div class="min-w-0 flex-1">
                                                        <div class="flex items-center gap-1.5 flex-wrap">
                                                            <span class="text-xs font-medium text-[#1f2328]">{{ c.column }}</span>
                                                            <template v-if="c.matched">
                                                                <UIcon name="i-heroicons-arrow-right" class="w-3 h-3 text-[#9a958c]" />
                                                                <span class="text-xs text-[#6b6b6b]">{{ c.matched_column }}</span>
                                                                <span class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-green-100 text-green-700">{{ c.match_kind }}</span>
                                                            </template>
                                                            <span v-else class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">no match</span>
                                                        </div>
                                                        <p class="text-[11px] text-[#9a958c] mt-0.5">{{ c.description }}</p>
                                                    </div>
                                                </li>
                                            </ul>
                                        </div>

                                        <!-- unmatched columns hint -->
                                        <div v-if="acUnmatched.length" class="text-[11px] text-[#9a958c]">
                                            Unmatched columns (skipped): {{ acUnmatched.join(', ') }}
                                        </div>

                                        <!-- proposed instructions (incl compliance) -->
                                        <div v-if="acInstructions.length">
                                            <p class="text-[11px] font-semibold uppercase tracking-wider text-[#9a958c] mb-2">Instructions ({{ acInstructionsChecked }} of {{ acInstructions.length }})</p>
                                            <ul class="space-y-1.5">
                                                <li v-for="(ins, i) in acInstructions" :key="'i'+i" class="flex items-start gap-2 rounded-lg border border-[#E7E5DD] bg-white p-2">
                                                    <UCheckbox v-model="ins.include" class="mt-0.5" />
                                                    <div class="min-w-0 flex-1">
                                                        <span v-if="ins.compliance" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-[#F4E5DA] text-[#A8542F] me-1">compliance</span>
                                                        <span class="text-xs text-[#1f2328] whitespace-pre-wrap">{{ ins.content }}</span>
                                                    </div>
                                                </li>
                                            </ul>
                                        </div>

                                        <!-- proposed examples -->
                                        <div v-if="acExamples.length">
                                            <p class="text-[11px] font-semibold uppercase tracking-wider text-[#9a958c] mb-2">Examples ({{ acExamplesChecked }} of {{ acExamples.length }})</p>
                                            <ul class="space-y-1.5">
                                                <li v-for="(ex, i) in acExamples" :key="'e'+i" class="flex items-start gap-2 rounded-lg border border-[#E7E5DD] bg-white p-2">
                                                    <UCheckbox v-model="ex.include" class="mt-0.5" />
                                                    <div class="min-w-0 flex-1">
                                                        <p class="text-xs font-medium text-[#1f2328]">{{ ex.question }}</p>
                                                        <p v-if="ex.answer" class="text-[11px] text-[#6b6b6b] mt-0.5 whitespace-pre-wrap">{{ ex.answer }}</p>
                                                        <pre v-if="ex.sql" class="text-[10px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded px-2 py-1 mt-1 overflow-x-auto whitespace-pre-wrap">{{ ex.sql }}</pre>
                                                    </div>
                                                </li>
                                            </ul>
                                        </div>

                                        <div class="flex items-center justify-end gap-2 pt-1">
                                            <UButton color="gray" variant="outline" size="sm" :disabled="acApplying" @click="acReset">Discard</UButton>
                                            <UButton color="orange" size="sm" :loading="acApplying" @click="acApply">Approve &amp; apply</UButton>
                                        </div>
                                    </div>
                                </template>
                            </div>

                            <!-- doc loading hint (docs render per-source above) -->
                            <div v-if="loadingDocs && sources.length" class="flex items-center justify-center py-4 text-[#9a958c]">
                                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                            </div>
                        </section>

                        <!-- INSTRUCTIONS -->
                        <section v-else-if="activeTab === 'instructions'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.instructionsTitle') }}</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('studio.instructionsHint') }}</p>
                                </div>
                                <div v-if="canEdit" class="flex items-center gap-2">
                                    <button type="button" :disabled="regenInstr" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors disabled:opacity-50" @click="regenerateInstructions">
                                        <Spinner v-if="regenInstr" class="h-3.5 w-3.5" />
                                        <UIcon v-else name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F]" />
                                        {{ $t('studio.regenerate') }}
                                    </button>
                                    <button type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-1.5 transition-colors" @click="openAddInstruction">
                                        <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5" />
                                        {{ $t('studio.addInstruction') }}
                                    </button>
                                </div>
                            </div>

                            <!-- SELF-LEARNING REVIEW QUEUE (Feature 5) -->
                            <div v-if="reviewQueueCount > 0" class="rounded-2xl border border-amber-200 bg-amber-50/40 p-4 mb-4">
                                <div class="flex items-center gap-2 mb-3">
                                    <UIcon name="i-heroicons-inbox-arrow-down" class="w-4 h-4 text-[#C2683F]" />
                                    <h3 class="text-sm font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Review queue</h3>
                                    <span class="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">{{ reviewQueueCount }} pending</span>
                                    <button v-if="canEdit" type="button" :disabled="approvingAll" class="ms-auto inline-flex items-center gap-1.5 text-[11px] font-semibold text-white bg-[#3f9e6a] hover:bg-[#357f57] rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50" @click="approveAllPending">
                                        <Spinner v-if="approvingAll" class="h-3 w-3 text-white" />
                                        <UIcon v-else name="i-heroicons-check" class="w-3.5 h-3.5" />
                                        Approve all ({{ reviewQueueCount }})
                                    </button>
                                </div>
                                <div class="flex items-center justify-between mb-3">
                                    <p class="text-[11px] text-[#9a958c]">Auto-proposed rules &amp; examples (from learning + auto-configure). Approve to make them live, or reject to dismiss.</p>
                                    <label v-if="canEdit" class="inline-flex items-center gap-1.5 text-[11px] text-[#6b6b6b] cursor-pointer select-none shrink-0 ms-3">
                                        <UToggle v-model="autoApproveReview" size="2xs" /> Auto-approve on train
                                    </label>
                                </div>

                                <!-- pending instructions -->
                                <ul v-if="pendingInstructions.length" class="space-y-1.5 mb-2">
                                    <li v-for="ins in pendingInstructions" :key="'pi'+ins.id" class="flex items-start justify-between gap-3 rounded-lg border border-[#E7E5DD] bg-white p-2.5">
                                        <div class="min-w-0 flex-1">
                                            <span class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 me-1">rule</span>
                                            <span class="text-xs text-[#1f2328] whitespace-pre-wrap">{{ ins.content }}</span>
                                        </div>
                                        <div v-if="canEdit" class="flex items-center gap-1 shrink-0">
                                            <UButton color="green" variant="soft" size="2xs" icon="i-heroicons-check" @click="approveInstruction(ins)">{{ $t('studio.approve') }}</UButton>
                                            <UButton color="red" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="rejectInstruction(ins)">{{ $t('studio.reject') }}</UButton>
                                        </div>
                                    </li>
                                </ul>

                                <!-- pending examples -->
                                <ul v-if="pendingExamples.length" class="space-y-1.5">
                                    <li v-for="ex in pendingExamples" :key="'pe'+ex.id" class="flex items-start justify-between gap-3 rounded-lg border border-[#E7E5DD] bg-white p-2.5">
                                        <div class="min-w-0 flex-1">
                                            <span class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-[#F4E5DA] text-[#A8542F] me-1">example</span>
                                            <span class="text-xs font-medium text-[#1f2328]">{{ ex.question }}</span>
                                            <p v-if="ex.answer" class="text-[11px] text-[#6b6b6b] mt-0.5 whitespace-pre-wrap">{{ ex.answer }}</p>
                                            <pre v-if="ex.sql" class="text-[10px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded px-2 py-1 mt-1 overflow-x-auto whitespace-pre-wrap">{{ ex.sql }}</pre>
                                        </div>
                                        <div v-if="canEdit" class="flex items-center gap-1 shrink-0">
                                            <UButton color="green" variant="soft" size="2xs" icon="i-heroicons-check" @click="approveExample(ex)">{{ $t('studio.approve') }}</UButton>
                                            <UButton color="red" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="rejectExample(ex)">{{ $t('studio.reject') }}</UButton>
                                        </div>
                                    </li>
                                </ul>
                            </div>

                            <div v-if="loadingInstr" class="flex items-center justify-center py-10 text-[#9a958c]">
                                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                            </div>
                            <div v-else-if="instructions.length === 0" class="py-10 text-center border border-dashed border-[#E7E5DD] rounded-2xl">
                                <UIcon name="i-heroicons-clipboard-document-list" class="w-7 h-7 mx-auto text-[#9a958c] mb-1.5" />
                                <p class="text-xs text-[#6b6b6b]">{{ $t('studio.noInstructions') }}</p>
                            </div>
                            <ul v-else class="space-y-2">
                                <li
                                    v-for="ins in instructions"
                                    :key="ins.id"
                                    class="rounded-2xl border border-[#E7E5DD] bg-white p-3"
                                >
                                    <div class="flex items-start justify-between gap-3">
                                        <div class="min-w-0 flex-1">
                                            <span :class="statusBadgeClass(ins.status)" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded">
                                                {{ statusLabel(ins.status) }}
                                            </span>
                                            <p v-if="editingInstrId !== ins.id" class="text-xs text-[#1f2328] mt-1.5 whitespace-pre-wrap">{{ ins.content }}</p>
                                            <UTextarea v-else v-model="editInstrDraft" :rows="3" size="sm" class="mt-1.5" />
                                        </div>
                                        <div v-if="canEdit" class="flex items-center gap-1 shrink-0">
                                            <template v-if="editingInstrId === ins.id">
                                                <UButton color="orange" size="2xs" :loading="savingInstr" @click="saveInstructionEdit(ins)">{{ $t('common.save') }}</UButton>
                                                <UButton color="gray" variant="ghost" size="2xs" @click="editingInstrId = null">{{ $t('common.cancel') }}</UButton>
                                            </template>
                                            <template v-else>
                                                <UButton v-if="ins.status === 'pending'" color="green" variant="soft" size="2xs" icon="i-heroicons-check" @click="approveInstruction(ins)">{{ $t('studio.approve') }}</UButton>
                                                <UButton v-if="ins.status === 'pending'" color="red" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="rejectInstruction(ins)">{{ $t('studio.reject') }}</UButton>
                                                <UButton color="gray" variant="ghost" size="2xs" icon="i-heroicons-pencil-square" @click="startInstructionEdit(ins)">{{ $t('studio.edit') }}</UButton>
                                                <UButton color="gray" variant="ghost" size="2xs" icon="i-heroicons-trash" @click="deleteInstruction(ins)" />
                                            </template>
                                        </div>
                                    </div>
                                </li>
                            </ul>
                        </section>

                        <!-- EXAMPLES -->
                        <section v-else-if="activeTab === 'examples'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.examplesTitle') }}</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('studio.examplesHint') }}</p>
                                </div>
                                <div v-if="canEdit" class="flex items-center gap-2">
                                    <button type="button" :disabled="regenEx" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors disabled:opacity-50" @click="regenerateExamples">
                                        <Spinner v-if="regenEx" class="h-3.5 w-3.5" />
                                        <UIcon v-else name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F]" />
                                        {{ $t('studio.regenerate') }}
                                    </button>
                                    <button type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-1.5 transition-colors" @click="openAddExample">
                                        <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5" />
                                        {{ $t('studio.addExample') }}
                                    </button>
                                </div>
                            </div>

                            <div v-if="loadingEx" class="flex items-center justify-center py-10 text-[#9a958c]">
                                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                            </div>
                            <div v-else-if="examples.length === 0" class="py-10 text-center border border-dashed border-[#E7E5DD] rounded-2xl">
                                <UIcon name="i-heroicons-academic-cap" class="w-7 h-7 mx-auto text-[#9a958c] mb-1.5" />
                                <p class="text-xs text-[#6b6b6b]">{{ $t('studio.noExamples') }}</p>
                            </div>
                            <ul v-else class="space-y-2">
                                <li
                                    v-for="ex in examples"
                                    :key="ex.id"
                                    class="rounded-2xl border border-[#E7E5DD] bg-white p-3"
                                >
                                    <div class="flex items-start justify-between gap-3">
                                        <div class="min-w-0 flex-1">
                                            <span :class="statusBadgeClass(ex.status)" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded">
                                                {{ statusLabel(ex.status) }}
                                            </span>
                                            <template v-if="editingExId !== ex.id">
                                                <p class="text-xs font-medium text-[#1f2328] mt-1.5">{{ ex.question }}</p>
                                                <p v-if="ex.answer" class="text-xs text-[#6b6b6b] mt-1 whitespace-pre-wrap">{{ ex.answer }}</p>
                                                <pre v-if="ex.sql" class="text-[11px] text-[#6b6b6b] bg-[#F4F1EA] border border-[#E7E5DD] rounded px-2 py-1.5 mt-1.5 overflow-x-auto whitespace-pre-wrap">{{ ex.sql }}</pre>
                                            </template>
                                            <div v-else class="mt-1.5 space-y-1.5">
                                                <UInput v-model="editEx.question" :placeholder="$t('studio.exampleQuestion')" size="sm" />
                                                <UTextarea v-model="editEx.answer" :placeholder="$t('studio.exampleAnswer')" :rows="2" size="sm" />
                                                <UTextarea v-model="editEx.sql" :placeholder="$t('studio.exampleSql')" :rows="2" size="sm" />
                                            </div>
                                        </div>
                                        <div v-if="canEdit" class="flex items-center gap-1 shrink-0">
                                            <template v-if="editingExId === ex.id">
                                                <UButton color="orange" size="2xs" :loading="savingEx" @click="saveExampleEdit(ex)">{{ $t('common.save') }}</UButton>
                                                <UButton color="gray" variant="ghost" size="2xs" @click="editingExId = null">{{ $t('common.cancel') }}</UButton>
                                            </template>
                                            <template v-else>
                                                <UButton v-if="ex.status === 'pending'" color="green" variant="soft" size="2xs" icon="i-heroicons-check" @click="approveExample(ex)">{{ $t('studio.approve') }}</UButton>
                                                <UButton v-if="ex.status === 'pending'" color="red" variant="ghost" size="2xs" icon="i-heroicons-x-mark" @click="rejectExample(ex)">{{ $t('studio.reject') }}</UButton>
                                                <UButton color="gray" variant="ghost" size="2xs" icon="i-heroicons-pencil-square" @click="startExampleEdit(ex)">{{ $t('studio.edit') }}</UButton>
                                                <UButton color="gray" variant="ghost" size="2xs" icon="i-heroicons-trash" @click="deleteExample(ex)" />
                                            </template>
                                        </div>
                                    </div>
                                </li>
                            </ul>
                        </section>

                        <!-- SKILLS -->
                        <section v-else-if="activeTab === 'skills'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.skillsTitle') }}</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('studio.skillsHint') }}</p>
                                </div>
                                <button v-if="canEdit" type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-1.5 transition-colors" @click="openAddSkill">
                                    <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5" />
                                    {{ $t('studio.pinSkill') }}
                                </button>
                            </div>

                            <div v-if="loadingSkills" class="flex items-center justify-center py-10 text-[#9a958c]">
                                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                            </div>
                            <div v-else-if="pinnedSkills.length === 0" class="py-10 text-center border border-dashed border-[#E7E5DD] rounded-2xl">
                                <UIcon name="i-heroicons-sparkles" class="w-7 h-7 mx-auto text-[#9a958c] mb-1.5" />
                                <p class="text-xs text-[#6b6b6b]">{{ $t('studio.noSkillsPinned') }}</p>
                            </div>
                            <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-3">
                                <div
                                    v-for="sk in pinnedSkills"
                                    :key="sk.id"
                                    class="flex items-start justify-between p-3 rounded-2xl border border-[#E7E5DD] bg-white"
                                >
                                    <div class="min-w-0">
                                        <div class="flex items-center gap-1.5">
                                            <UIcon name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F] shrink-0" />
                                            <span class="text-xs font-medium text-[#1f2328] truncate">{{ sk.name }}</span>
                                        </div>
                                        <p v-if="sk.description" class="text-[11px] text-[#6b6b6b] line-clamp-2 mt-0.5">{{ sk.description }}</p>
                                    </div>
                                    <UButton
                                        v-if="canEdit"
                                        color="gray"
                                        variant="ghost"
                                        size="2xs"
                                        icon="i-heroicons-x-mark"
                                        @click="unpinSkill(sk.id)"
                                    >
                                        {{ $t('studio.unpinSkill') }}
                                    </UButton>
                                </div>
                            </div>
                        </section>

                        <!-- ARTIFACTS -->
                        <section v-else-if="activeTab === 'artifacts'">
                            <ArtifactsPanel :studio-id="studioId" :can-edit="canEdit" />
                        </section>

                        <!-- CONNECTION (Data Agent parity; scoped to pinned sources) -->
                        <section v-else-if="activeTab === 'connection'">
                            <StudioConnection :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- TABLES -->
                        <section v-else-if="activeTab === 'tables'">
                            <StudioTables :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- TOOLS -->
                        <section v-else-if="activeTab === 'tools'">
                            <StudioTools :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- KNOWLEDGE: SEMANTIC -->
                        <section v-else-if="activeTab === 'k_semantic'">
                            <StudioQueries :studio-id="studioId" :sources="sources" :can-edit="canEdit" :forceTab="'semantic'" />
                        </section>

                        <!-- KNOWLEDGE: METRICS -->
                        <section v-else-if="activeTab === 'k_metrics'">
                            <StudioQueries :studio-id="studioId" :sources="sources" :can-edit="canEdit" :forceTab="'metrics'" />
                        </section>

                        <!-- KNOWLEDGE: QUERIES -->
                        <section v-else-if="activeTab === 'k_queries'">
                            <StudioQueries :studio-id="studioId" :sources="sources" :can-edit="canEdit" :forceTab="'queries'" />
                        </section>

                        <!-- KNOWLEDGE: ASSETS -->
                        <section v-else-if="activeTab === 'k_assets'">
                            <StudioQueries :studio-id="studioId" :sources="sources" :can-edit="canEdit" :forceTab="'assets'" />
                        </section>

                        <!-- KNOWLEDGE: REVIEW -->
                        <section v-else-if="activeTab === 'k_review'">
                            <StudioQueries :studio-id="studioId" :sources="sources" :can-edit="canEdit" :forceTab="'review'" />
                        </section>

                        <!-- TEACH (paste an analysis → classify into reviewable spans) -->
                        <section v-else-if="activeTab === 'teach'">
                            <StudioTeach :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- SKILLS (review/approve bound domain packs) -->
                        <section v-else-if="activeTab === 'skills'">
                            <StudioSkills :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- EVALS -->
                        <section v-else-if="activeTab === 'evals'">
                            <StudioEvals :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- MONITORING -->
                        <section v-else-if="activeTab === 'monitoring'">
                            <StudioMonitoring :studio-id="studioId" :sources="sources" :can-edit="canEdit" />
                        </section>

                        <!-- SETTINGS (auto avatar + voice + summary) -->
                        <section v-else-if="activeTab === 'settings'">
                            <div class="mb-4">
                                <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.settingsTitle') }}</h2>
                                <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('studio.settingsHint') }}</p>
                            </div>

                            <!-- Avatar (auto) -->
                            <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mb-3">
                                <div class="flex items-center justify-between mb-1">
                                    <label class="text-xs font-medium text-[#1f2328]">{{ $t('studio.avatarLabel') }}</label>
                                    <span class="text-[10px] text-[#9a958c]">{{ $t('studio.autoBadge') }}</span>
                                </div>
                                <div class="flex items-center gap-3 mt-2">
                                    <div class="shrink-0 flex items-center justify-center w-10 h-10 rounded-lg bg-[#F4F1EA] border border-[#E7E5DD] text-xl text-[#C2683F] overflow-hidden">
                                        <img v-if="isImageAvatar" :src="studio?.avatar || ''" alt="" class="w-full h-full object-cover" />
                                        <span v-else-if="studio?.avatar">{{ studio?.avatar }}</span>
                                        <UIcon v-else name="i-heroicons-film" class="w-5 h-5 text-[#C2683F]" />
                                    </div>
                                    <button v-if="canEdit" type="button" :disabled="regenAvatar" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors disabled:opacity-50" @click="regenerateAvatar">
                                        <Spinner v-if="regenAvatar" class="h-3.5 w-3.5" />
                                        <UIcon v-else name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F]" />
                                        {{ $t('studio.regenerate') }}
                                    </button>
                                </div>
                            </div>

                            <!-- Voice (= persona, auto, editable) -->
                            <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mb-3">
                                <div class="flex items-center justify-between mb-1">
                                    <label class="text-xs font-medium text-[#1f2328]">{{ $t('studio.voiceLabel') }}</label>
                                    <span class="text-[10px] text-[#9a958c]">{{ $t('studio.autoEditableBadge') }}</span>
                                </div>
                                <p class="text-[11px] text-[#6b6b6b] mb-2">{{ $t('studio.voiceHint') }}</p>
                                <UTextarea v-model="voiceDraft" :rows="3" size="sm" :disabled="!canEdit" :placeholder="$t('studio.voicePlaceholder')" />
                                <div v-if="canEdit" class="mt-2 flex items-center gap-2">
                                    <UButton color="orange" size="xs" :loading="savingVoice" :disabled="voiceDraft === (studio?.persona || '')" @click="saveVoice">
                                        {{ $t('common.save') }}
                                    </UButton>
                                    <button type="button" :disabled="regenVoice" class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors disabled:opacity-50" @click="regenerateVoice">
                                        <Spinner v-if="regenVoice" class="h-3.5 w-3.5" />
                                        <UIcon v-else name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F]" />
                                        {{ $t('studio.regenerate') }}
                                    </button>
                                </div>
                            </div>

                            <!-- Summary (auto) -->
                            <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4">
                                <div class="flex items-center justify-between mb-1">
                                    <label class="text-xs font-medium text-[#1f2328]">{{ $t('studio.summaryLabel') }}</label>
                                    <span class="text-[10px] text-[#9a958c]">{{ $t('studio.autoBadge') }}</span>
                                </div>
                                <p v-if="summaryText" class="text-xs text-[#1f2328] mt-1.5 whitespace-pre-wrap">{{ summaryText }}</p>
                                <p v-else class="text-xs text-[#9a958c] italic mt-1.5">{{ $t('studio.noSummary') }}</p>
                            </div>
                        </section>

                        <!-- MEMBERS / SHARE -->
                        <section v-else-if="activeTab === 'members'">
                            <div class="flex items-start justify-between mb-4">
                                <div>
                                    <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.membersTitle') }}</h2>
                                    <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('studio.membersHint') }}</p>
                                </div>
                                <button type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-1.5 transition-colors" @click="showShare = true">
                                    <UIcon name="i-heroicons-share" class="w-3.5 h-3.5" />
                                    {{ $t('studio.shareTitle') }}
                                </button>
                            </div>
                            <p class="text-xs text-[#6b6b6b]">
                                {{ $t('studio.shareScope') }}: <span class="font-medium text-[#1f2328]">{{ scopeLabel }}</span>
                            </p>
                            <button type="button" class="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors" @click="showShare = true">
                                <UIcon name="i-heroicons-users" class="w-3.5 h-3.5 text-[#9a958c]" />
                                {{ $t('studio.tabMembers') }}
                            </button>

                            <div v-if="role === 'owner'" class="mt-8 pt-4 border-t border-[#E7E5DD]">
                                <UButton color="red" variant="outline" size="xs" icon="i-heroicons-trash" :loading="deleting" @click="deleteStudio">
                                    {{ $t('studio.deleteStudio') }}
                                </UButton>
                            </div>
                        </section>
                    </div>
                </main>
            </template>

            <!-- Share modal -->
            <ShareModal
                v-if="studio"
                v-model="showShare"
                :studio-id="studioId"
                :owner-user-id="String(studio.owner_user_id)"
                :can-manage="role === 'owner'"
                :share-scope="studio.share_scope"
                :share-token="studio.share_token"
                @updated="onShareUpdated"
            />

            <!-- Add source modal -->
            <UModal v-model="showAddSource" :ui="{ width: 'sm:max-w-md' }">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.pickSource') }}</h2>
                        <button @click="showAddSource = false" class="text-[#9a958c] hover:text-[#6b6b6b]">
                            <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
                        </button>
                    </div>
                    <div v-if="loadingAgents" class="flex items-center justify-center py-8 text-[#9a958c]">
                        <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                    </div>
                    <div v-else-if="pinnableAgents.length === 0" class="py-8 text-center text-xs text-[#6b6b6b]">
                        {{ $t('studio.noAgentsToPin') }}
                    </div>
                    <ul v-else class="space-y-1 max-h-80 overflow-y-auto">
                        <li
                            v-for="a in pinnableAgents"
                            :key="a.id"
                            class="flex items-center justify-between gap-2 rounded-lg px-2 py-2 hover:bg-[#faf8f3] cursor-pointer"
                            @click="pinSource(a)"
                        >
                            <div class="flex items-center gap-2 min-w-0">
                                <DataSourceIcon v-if="(a.connections || [])[0]?.type" class="h-4 shrink-0" :type="(a.connections || [])[0]?.type" />
                                <UIcon v-else name="i-heroicons-circle-stack" class="w-4 h-4 shrink-0 text-[#9a958c]" />
                                <span class="text-xs text-[#1f2328] truncate">{{ a.name }}</span>
                            </div>
                            <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5 text-[#9a958c] shrink-0" />
                        </li>
                    </ul>
                </div>
            </UModal>

            <!-- Upload spreadsheet → auto-pin to this studio -->
            <UploadSpreadsheetModal
                :open="showUploadSource"
                :studio-id="studioId"
                @close="showUploadSource = false"
                @created="onUploadCreated"
            />

            <!-- Add skill modal -->
            <UModal v-model="showAddSkill" :ui="{ width: 'sm:max-w-md' }">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.pinSkill') }}</h2>
                        <button @click="showAddSkill = false" class="text-[#9a958c] hover:text-[#6b6b6b]">
                            <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
                        </button>
                    </div>
                    <div v-if="loadingAllSkills" class="flex items-center justify-center py-8 text-[#9a958c]">
                        <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                    </div>
                    <div v-else-if="pinnableSkills.length === 0" class="py-8 text-center text-xs text-[#6b6b6b]">
                        {{ $t('studio.noSkillsToPin') }}
                    </div>
                    <ul v-else class="space-y-1 max-h-80 overflow-y-auto">
                        <li
                            v-for="sk in pinnableSkills"
                            :key="sk.id"
                            class="flex items-center justify-between gap-2 rounded-lg px-2 py-2 hover:bg-[#faf8f3] cursor-pointer"
                            @click="pinSkill(sk)"
                        >
                            <div class="min-w-0">
                                <div class="flex items-center gap-1.5">
                                    <UIcon name="i-heroicons-sparkles" class="w-3.5 h-3.5 text-[#C2683F] shrink-0" />
                                    <span class="text-xs text-[#1f2328] truncate">{{ sk.name }}</span>
                                </div>
                                <p v-if="sk.description" class="text-[11px] text-[#9a958c] line-clamp-1">{{ sk.description }}</p>
                            </div>
                            <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5 text-[#9a958c] shrink-0" />
                        </li>
                    </ul>
                </div>
            </UModal>

            <!-- Add instruction modal -->
            <UModal v-model="showAddInstruction" :ui="{ width: 'sm:max-w-md' }">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.addInstruction') }}</h2>
                        <button @click="showAddInstruction = false" class="text-[#9a958c] hover:text-[#6b6b6b]">
                            <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
                        </button>
                    </div>
                    <UTextarea v-model="newInstrDraft" :rows="4" size="sm" :placeholder="$t('studio.instructionPlaceholder')" />
                    <div class="mt-4 flex items-center justify-end gap-2">
                        <UButton color="gray" variant="outline" size="sm" @click="showAddInstruction = false">{{ $t('common.cancel') }}</UButton>
                        <UButton color="orange" size="sm" :loading="savingInstr" :disabled="!newInstrDraft.trim()" @click="createInstruction">{{ $t('studio.addInstruction') }}</UButton>
                    </div>
                </div>
            </UModal>

            <!-- Add example modal -->
            <UModal v-model="showAddExample" :ui="{ width: 'sm:max-w-md' }">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ $t('studio.addExample') }}</h2>
                        <button @click="showAddExample = false" class="text-[#9a958c] hover:text-[#6b6b6b]">
                            <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
                        </button>
                    </div>
                    <div class="space-y-2">
                        <UInput v-model="newEx.question" size="sm" :placeholder="$t('studio.exampleQuestion')" />
                        <UTextarea v-model="newEx.answer" :rows="2" size="sm" :placeholder="$t('studio.exampleAnswer')" />
                        <UTextarea v-model="newEx.sql" :rows="2" size="sm" :placeholder="$t('studio.exampleSql')" />
                    </div>
                    <div class="mt-4 flex items-center justify-end gap-2">
                        <UButton color="gray" variant="outline" size="sm" @click="showAddExample = false">{{ $t('common.cancel') }}</UButton>
                        <UButton color="orange" size="sm" :loading="savingEx" :disabled="!newEx.question.trim()" @click="createExample">{{ $t('studio.addExample') }}</UButton>
                    </div>
                </div>
            </UModal>
    </div>
</template>

<script setup lang="ts">
import ShareModal from '~/components/studio/ShareModal.vue'
import ArtifactsPanel from '~/components/studio/ArtifactsPanel.vue'
import DataSourceIcon from '~/components/DataSourceIcon.vue'
import UploadSpreadsheetModal from '~/components/data/UploadSpreadsheetModal.vue'
import Spinner from '~/components/Spinner.vue'
// Data Agent parity tabs (additive, flag-gated by the Studios workspace itself).
import StudioConnection from '~/components/studio/StudioConnection.vue'
import StudioTables from '~/components/studio/StudioTables.vue'
import StudioTools from '~/components/studio/StudioTools.vue'
import StudioQueries from '~/components/studio/StudioQueries.vue'
import StudioEvals from '~/components/studio/StudioEvals.vue'
import StudioTeach from '~/components/studio/StudioTeach.vue'
import StudioSkills from '~/components/studio/StudioSkills.vue'
import StudioMonitoring from '~/components/studio/StudioMonitoring.vue'

definePageMeta({ auth: true, layout: 'default' })

interface Studio {
    id: string
    name: string
    description?: string | null
    persona?: string | null
    avatar?: string | null
    owner_user_id: string
    share_scope: string
    share_token?: string | null
    config?: Record<string, any>
}
interface Source { id: string; studio_id: string; agent_id: string; name?: string | null; type?: string | null }
interface SkillItem { id: string; name: string; description?: string | null; scope?: string; status?: string }
interface ChatItem { id: string; title?: string; studio_id?: string }
interface Instruction { id: string; content: string; status: string; source?: string }
interface Example { id: string; question: string; answer?: string | null; sql?: string | null; status: string; source?: string }
interface ArtifactItem { id: string; kind: string; content?: string | null }

const { t } = useI18n()
const toast = useToast()
const route = useRoute()
const router = useRouter()
const { data: currentUser } = useAuth()

const studioId = computed(() => String(route.params.id))

const studio = ref<Studio | null>(null)
const role = ref<string>('viewer')

// Teach Box tab — gated by the per-org HYBRID_TEACH_BOX flag. Fail-soft to OFF.
const teachEnabled = ref(false)
async function loadTeachFlag() {
    try {
        const { data } = await useMyFetch<any>('/api/organization/hybrid-flags')
        const rows: any[] = Array.isArray(data.value) ? (data.value as any[]) : []
        const row = rows.find((r: any) => r?.env_name === 'HYBRID_TEACH_BOX' || r?.key === 'teach_box')
        if (row && typeof row.effective === 'boolean') teachEnabled.value = row.effective
    } catch { /* flag plumbing absent → leave OFF */ }
}

// Skills tab (bound domain packs) — gated by the per-org HYBRID_DOMAIN_PACKS flag.
const packsEnabled = ref(false)
async function loadPacksFlag() {
    try {
        const { data } = await useMyFetch<any>('/api/organization/hybrid-flags')
        const rows: any[] = Array.isArray(data.value) ? (data.value as any[]) : []
        const row = rows.find((r: any) => r?.env_name === 'HYBRID_DOMAIN_PACKS' || r?.key === 'domain_packs')
        if (row && typeof row.effective === 'boolean') packsEnabled.value = row.effective
    } catch { /* flag plumbing absent → leave OFF */ }
}
const loading = ref(true)
const notFound = ref(false)

const sources = ref<Source[]>([])
const pinnedSkills = ref<SkillItem[]>([])
const loadingSkills = ref(false)
const chats = ref<ChatItem[]>([])
const loadingChats = ref(false)

// Studio landing = Sources (training-first home), not chat. Chat stays reachable
// via the studio-header button; it is just no longer the default surface.
const activeTab = ref('autopilot')

// pre-train (Column Intelligence) — Sources hero "Auto-train" button.
// Wired to POST /data_sources/{id}/pretrain (self-gates on COLUMN_INTEL flag).
const pretraining = ref(false)
const autoApprove = ref(false)
const pretrainResult = ref<any>(null)
const showShare = ref(false)
const showAddSource = ref(false)
const showUploadSource = ref(false)
const showAddSkill = ref(false)
const deleting = ref(false)
const creatingChat = ref(false)
const improving = ref(false)

// instructions
const instructions = ref<Instruction[]>([])
const loadingInstr = ref(false)
const regenInstr = ref(false)
const savingInstr = ref(false)
const showAddInstruction = ref(false)
const newInstrDraft = ref('')
const editingInstrId = ref<string | null>(null)
const editInstrDraft = ref('')

// examples
const examples = ref<Example[]>([])
const loadingEx = ref(false)
const regenEx = ref(false)
const savingEx = ref(false)
const showAddExample = ref(false)
const newEx = reactive({ question: '', answer: '', sql: '' })
const editingExId = ref<string | null>(null)
const editEx = reactive({ question: '', answer: '', sql: '' })

// settings (auto avatar/voice/summary)
const voiceDraft = ref('')
const savingVoice = ref(false)
const regenVoice = ref(false)
const regenAvatar = ref(false)
const summaryText = ref('')

// suggested questions (chat empty-state chips)
const suggestedQuestions = ref<string[]>([])

// knowledge docs
interface KnowledgeDoc { id: string; title: string; source?: string; status: string; chunks?: number; created_at?: string; data_source_id?: string | null }
const docs = ref<KnowledgeDoc[]>([])
const docStats = ref<{ total: number; approved: number; pending: number }>({ total: 0, approved: 0, pending: 0 })
const loadingDocs = ref(false)
const savingDoc = ref(false)
const docsDisabled = ref(false)
const docRejectHidden = ref(false)   // hide reject if its route 404s
const newDoc = reactive({ title: '', body: '' })
// null = org-wide; otherwise a pinned source's agent_id. In the merged view this
// is set by the card's "+ Add" button (no dropdown → no wrong default), then the
// inline paste form writes the doc straight onto that source.
const docSourceId = ref<string | null>(null)
// (the old org-wide/source dropdown is gone — add is per-card now)
// which add-form is open: a source agent_id, '__org__' for org-wide, or '' none.
const addTarget = ref<string>('')
// docs grouped by the source they ground (org-wide = no data_source_id).
const docsForSource = (agentId: string | null) =>
    docs.value.filter(d => String(d.data_source_id || '') === String(agentId || ''))
const orgDocs = computed(() => docs.value.filter(d => !d.data_source_id))
function openAddKnowledge(agentId: string | null) {
    addTarget.value = agentId == null ? '__org__' : String(agentId)
    docSourceId.value = agentId == null ? null : String(agentId)
    newDoc.title = ''
    newDoc.body = ''
}
function closeAddKnowledge() { addTarget.value = '' }
// "↑ Doc" on a card → pre-map auto-configure to that source + reveal the dropzone.
function openAutoConfigure(agentId: string) {
    acSourceId.value = String(agentId)
    acReset()
    nextTick(() => document.getElementById('studio-autoconfigure')?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}
const docStatusBadgeClass = (s?: string) =>
    s === 'approved' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'

// ---- in-card tabs: Tables · Knowledge · Insights · Connection ----
const cardTabDefs = [
    { k: 'tables', label: 'Tables' },
    { k: 'knowledge', label: 'Knowledge' },
    { k: 'insights', label: 'Insights' },
    { k: 'connection', label: 'Connection' },
]
const cardTabs = reactive<Record<string, string>>({})
const cardTabOf = (id: any) => cardTabs[String(id)] || 'tables'
const setCardTab = (id: any, k: string) => { cardTabs[String(id)] = k; if (k === 'tables' || k === 'insights') fetchIntel(id) }

// ---- column intelligence per source (GET /data_sources/{id}/columns/intel) ----
const intel = reactive<Record<string, { tables: any[]; loading: boolean; loaded: boolean; disabled: boolean }>>({})
const _emptyIntel = { tables: [] as any[], loading: false, loaded: false, disabled: false }
// PURE reader — never writes (writing reactive state inside a computed getter
// breaks tracking → was the "0 columns trained" bug). fetchIntel owns the slot.
const intelFor = (id: any) => intel[String(id)] || _emptyIntel
async function fetchIntel(id: any, force = false) {
    const key = String(id)
    if (!intel[key]) intel[key] = { tables: [], loading: false, loaded: false, disabled: false }
    const slot = intel[key]
    if (slot.loading || (slot.loaded && !force)) return
    slot.loading = true
    try {
        const { data, error } = await useMyFetch<any>(`/data_sources/${id}/columns/intel`, { method: 'GET' })
        if (error?.value) throw error.value
        const r = data.value || {}
        slot.disabled = !!r.disabled
        slot.tables = (r.tables || [])
        slot.loaded = true
    } catch (e) { slot.tables = []; slot.loaded = true }
    finally { slot.loading = false }
}

// table-cell helpers
const roleClass = (r: string) => (({ dimension: 'bg-[#EEF1F4] text-[#475569]', dim: 'bg-[#EEF1F4] text-[#475569]', measure: 'bg-[#E7F2EC] text-[#2f7a52]', date: 'bg-[#F4E5DA] text-[#A8542F]', id: 'bg-[#F1ECF6] text-[#7c5cab]' } as Record<string, string>)[r] || 'bg-gray-100 text-gray-500')
const nullClass = (n: any) => (Number(n) || 0) >= 50 ? 'text-[#C2683F] font-semibold' : 'text-[#6b6b6b]'
const fmtNull = (n: any) => (n == null ? '—' : `${Math.round(Number(n))}%`)

// ---- insights derived from the column profile (honest — no invented numbers) ----
function insightsFor(id: any): string[] {
    const t = intelFor(id).tables
    if (!t.length) return []
    const cols = t.flatMap((x: any) => x.columns || [])
    const isDim = (c: any) => c.role === 'dimension' || c.role === 'dim'
    const out: string[] = []
    // 1. coverage / scale
    const dims = cols.filter(isDim).length
    const meas = cols.filter((c: any) => c.role === 'measure').length
    const dates = cols.filter((c: any) => c.role === 'date').length
    out.push(`${t.length} table${t.length > 1 ? 's' : ''} · ${cols.length} columns — ${dims} dimensions · ${meas} measures · ${dates} dates.`)
    // 2. widest breakdown (dimension with most distinct values)
    const rich = cols.filter((c: any) => isDim(c) && c.distinct).sort((a: any, b: any) => (b.distinct || 0) - (a.distinct || 0))[0]
    if (rich) out.push(`${rich.name} has ${rich.distinct} distinct values — your widest breakdown.`)
    // 3. a categorical with real sample values
    const cat = cols.find((c: any) => isDim(c) && (c.values || []).length >= 2)
    if (cat) out.push(`${cat.name}: ${cat.values.slice(0, 4).join(', ')}${cat.values.length > 4 ? '…' : ''}.`)
    // 4. date span
    const dt = cols.find((c: any) => c.role === 'date' && (c.min != null || c.max != null))
    if (dt) out.push(`${dt.name} spans ${dt.min} … ${dt.max}.`)
    // 5. a measure range
    const ms = cols.find((c: any) => c.role === 'measure' && (c.min != null || c.max != null))
    if (ms) out.push(`${ms.name} ranges ${ms.min} … ${ms.max}.`)
    // 6. ONE worst data-quality caveat (not a wall of them)
    const hi = cols.filter((c: any) => (c.null_pct || 0) >= 50).sort((a: any, b: any) => (b.null_pct || 0) - (a.null_pct || 0))[0]
    if (hi) out.push(`Caveat: ${hi.name} is ${Math.round(hi.null_pct)}% empty — avoid rollups on it.`)
    return out
}
const studioInsights = computed<string[]>(() => {
    const all: string[] = []
    for (const s of sources.value) all.push(...insightsFor((s as any).agent_id).slice(0, 2))
    return all.slice(0, 6)
})

// ---- federation (join graph: GET /knowledge/joins, POST /knowledge/joins/mine) ----
const joinEdges = ref<any[]>([])
const joinsDisabled = ref(false)
const miningJoins = ref(false)
async function fetchJoins() {
    const seen = new Set<string>(); const acc: any[] = []
    for (const s of sources.value) {
        try {
            const { data, error } = await useMyFetch<any>(`/knowledge/joins?data_source_id=${encodeURIComponent(String((s as any).agent_id))}`, { method: 'GET' })
            if (error?.value) continue
            for (const e of ((data.value as any)?.edges || [])) { if (!seen.has(e.id)) { seen.add(e.id); acc.push(e) } }
        } catch { /* fail-soft */ }
    }
    joinEdges.value = acc.sort((a, b) => (b.join_count || 0) - (a.join_count || 0))
}
async function mineJoins() {
    if (miningJoins.value) return
    miningJoins.value = true
    try {
        for (const s of sources.value) {
            const { data } = await useMyFetch<any>(`/knowledge/joins/mine`, { method: 'POST', body: { data_source_id: String((s as any).agent_id) } })
            if ((data.value as any)?.disabled) joinsDisabled.value = true
        }
        await fetchJoins()
    } finally { miningJoins.value = false }
}
async function approveJoin(e: any) {
    try { await useMyFetch(`/knowledge/join/${e.id}/approve`, { method: 'POST' }); e.status = 'approved' } catch { /* noop */ }
}
async function refreshSchema(id: any) {
    try { await useMyFetch(`/data_sources/${id}/refresh_schema`, { method: 'GET' }); await fetchIntel(id, true); toast.add({ title: 'Schema refreshed', color: 'green', icon: 'i-heroicons-check-circle' }) }
    catch { toast.add({ title: 'Refresh failed', color: 'red' }) }
}

// ============ AI AUTO-PILOT ============
// readiness signals derived from already-loaded surfaces (no extra calls)
const profiledCols = computed(() => {
    let n = 0
    for (const s of sources.value) for (const t of intelFor((s as any).agent_id).tables) n += (t.columns || []).filter((c: any) => c.role).length
    return n
})
// Count EXISTENCE (auto-train creates them; some land pending for review). The
// rail badges show these too — readiness shouldn't read 0 just because they're
// awaiting approval.
const activeInstr = computed(() => instructions.value.length)
const activeExamples = computed(() => examples.value.length)
const readiness = computed(() => {
    const checks = [
        { label: 'Sources pinned', done: sources.value.length > 0, w: 20 },
        { label: 'Columns profiled', done: profiledCols.value > 0, w: 20, hint: 'Auto-train' },
        { label: 'Knowledge applied', done: docs.value.length > 0, w: 15, hint: 'Add a doc' },
        { label: 'Instructions added', done: activeInstr.value > 0, w: 15 },
        { label: 'Examples added', done: activeExamples.value > 0, w: 10 },
        { label: 'Joins mined', done: joinEdges.value.length > 0, w: 10, hint: 'Mine joins' },
        { label: 'Artifacts generated', done: studioArtifactCount.value > 0, w: 10, hint: 'Auto-train' },
    ]
    const score = checks.reduce((a, c) => a + (c.done ? c.w : 0), 0)
    return { score, checks }
})
const readinessOffset = computed(() => Math.round(226 - (226 * readiness.value.score / 100)))

// studio artifacts count (auto-generated on train)
const studioArtifactCount = ref(0)
async function fetchArtifactCount() {
    try {
        const { data } = await useMyFetch<any>(`/studios/${studioId.value}/artifacts`, { method: 'GET' })
        studioArtifactCount.value = Array.isArray(data.value) ? data.value.length : ((data.value as any)?.length || 0)
    } catch { /* noop */ }
}

// capability map (status chips)
const capabilities = computed(() => [
    { key: 'tables', title: 'Tables & values', tag: 'auto', icon: 'i-heroicons-table-cells', desc: 'Columns profiled — role, distinct, sample values, null %.', meta: `${profiledCols.value} columns` },
    { key: 'knowledge', title: 'Knowledge', tag: 'auto', icon: 'i-heroicons-shield-check', desc: 'Definitions extracted from docs, applied live.', meta: `${docs.value.length} docs` },
    { key: 'evals', title: 'Evals', tag: studioArtifactCount.value ? 'auto' : 'manual', icon: 'i-heroicons-beaker', desc: 'Golden tests catch regressions on retrain.', meta: 'open Evals →', go: 'evals' },
    { key: 'artifacts', title: 'Artifacts', tag: 'auto', icon: 'i-heroicons-document-text', desc: 'Summary · FAQ · Briefing — regenerated each train.', meta: `${studioArtifactCount.value} generated`, go: 'artifacts' },
    { key: 'federation', title: 'Federation', tag: joinEdges.value.length ? 'auto' : 'manual', icon: 'i-heroicons-arrows-right-left', desc: 'Auto-mined joins across sources.', meta: `${joinEdges.value.length} joins`, go: 'sources' },
    { key: 'skills', title: 'Skills', tag: 'off', icon: 'i-heroicons-sparkles', desc: 'Off for stability — agent answers from data + knowledge.', meta: 'not needed' },
])

// AI next-best-actions
const aiSuggestions = computed(() => {
    const out: any[] = []
    if (!studioArtifactCount.value) out.push({ text: 'Generate Summary · FAQ · Briefing from your sources.', action: 'Generate', fn: 'artifacts' })
    for (const s of sources.value) {
        const hi = intelFor((s as any).agent_id).tables.flatMap((t: any) => t.columns || []).filter((c: any) => (c.null_pct || 0) >= 50)
        if (hi.length) { out.push({ text: `${hi[0].name} is ${Math.round(hi[0].null_pct)}% null — add a guardrail or drop it from prompts.`, action: 'Instructions', fn: 'instructions' }); break }
    }
    if (sources.value.length < 2) out.push({ text: 'Add a 2nd source (e.g. geo) to unlock cross-source federation.', action: 'Add source', fn: 'sources' })
    if (!joinEdges.value.length && sources.value.length >= 2) out.push({ text: 'Mine joins across your sources for correlation.', action: 'Mine', fn: 'sources' })
    out.push({ text: 'Build a starter dashboard from your KPIs.', action: 'New report', fn: 'report' })
    return out.slice(0, 4)
})
function doSuggestion(fn: string) {
    if (fn === 'artifacts') { generateAllArtifacts(); activeTab.value = 'artifacts' }
    else if (fn === 'report') { router.push('/reports/new') }
    else activeTab.value = fn
}

// generate all 6 auto artifacts — used by full train
async function generateAllArtifacts() {
    for (const kind of ['summary', 'faq', 'briefing', 'notes', 'kpi_pack', 'data_dictionary']) {
        try { await useMyFetch(`/studios/${studioId.value}/artifacts/generate`, { method: 'POST', body: { kind } }) } catch { /* fail-soft */ }
    }
    await fetchArtifactCount()
}

// auto-generate verified example SQL (Queries tab) for pinned sources
async function generateAutoQueries() {
    try { const { data } = await useMyFetch<any>(`/studios/${studioId.value}/auto-queries`, { method: 'POST', body: {} }); return (data.value as any) || {} } catch { return {} }
}
// auto-generate golden eval cases from real data
async function generateAutoEvals() {
    try { const { data } = await useMyFetch<any>(`/studios/${studioId.value}/auto-evals`, { method: 'POST', body: {} }); return (data.value as any) || {} } catch { return {} }
}

// ONE button: profile + knowledge + joins + artifacts, all live
const trainingAll = ref(false)
// Async, NON-BLOCKING: kick the background train job + poll status. The heavy
// LLM work (profile/queries/evals/artifacts/joins) runs server-side; the FE only
// polls a % and never holds the request open. You can navigate away — it keeps
// running. On completion the FE does the light tail (auto-enable joins, auto-approve).
const TRAIN_STEP_LABEL: Record<string, string> = {
    starting: 'Starting', profiling: 'Profiling columns', queries: 'Writing example queries',
    evals: 'Writing eval goldens', artifacts: 'Generating artifacts', joins: 'Mining joins', done: 'Done',
}
async function runFullTrain() {
    if (trainingAll.value || !sources.value.length) return
    trainingAll.value = true
    const act = useActivity()
    act.openPanel(); act.start('Auto-training studio'); act.setState('processing')
    try {
        const { data } = await useMyFetch<any>(`/studios/${studioId.value}/train`, { method: 'POST', body: {} })
        const kick = (data.value as any) || {}
        if (kick.status === 'error') { act.fail(kick.error || 'Could not start training'); return }
        act.log('Training started in background…')
        // poll up to ~3 min; the job survives even if we stop polling
        let terminal = ''
        for (let i = 0; i < 100 && !terminal; i++) {
            await new Promise(r => setTimeout(r, 1800))
            const { data: s } = await useMyFetch<any>(`/studios/${studioId.value}/train/status`, { method: 'GET' })
            const st = (s.value as any) || {}
            if (st.step) act.log(`${TRAIN_STEP_LABEL[st.step] || st.step} · ${st.pct || 0}%`)
            if (st.status === 'done') { terminal = 'done'; act.done('Studio trained — agent ready.') }
            else if (st.status === 'error') { terminal = 'error'; act.fail(st.error || 'Training failed') }
        }
        // refresh every surface the job touched
        await Promise.all([fetchInstructions(), fetchExamples(), fetchDocs(), fetchJoins(), fetchArtifactCount()])
        for (const s of sources.value) fetchIntel((s as any).agent_id, true)
        // light tail: auto-enable high-confidence joins + auto-approve (toggle)
        const strong = joinEdges.value.filter((e: any) => (e.confidence || 0) >= 0.7 && e.status !== 'approved')
        for (const e of strong) await approveJoin(e).catch(() => {})
        if (autoApproveReview.value) {
            await Promise.all([fetchInstructions(), fetchExamples(), fetchDocs()])
            if (pendingInstructions.value.length + pendingExamples.value.length) await approveAllPending().catch(() => {})
        }
    } finally { trainingAll.value = false }
}

// ---- Feature 1: auto-configure from document ----
interface AcFile { name: string; file: File; uploading: boolean; fileId: string | null; error: string }
interface AcColumn { column: string; description: string; matched: boolean; match_kind?: string; table_id?: string | null; matched_column?: string | null; include: boolean }
interface AcInstruction { content: string; compliance: boolean; include: boolean }
interface AcExample { question: string; answer?: string | null; sql?: string | null; include: boolean }

const acDisabled = ref(false)
const acDragging = ref(false)
const acFiles = ref<AcFile[]>([])
const acSourceId = ref<string | null>(null)
const acAnalyzing = ref(false)
const acApplying = ref(false)
const acError = ref('')
const acProposal = ref<any>(null)
const acColumns = ref<AcColumn[]>([])
const acUnmatched = ref<string[]>([])
const acInstructions = ref<AcInstruction[]>([])
const acExamples = ref<AcExample[]>([])

// Picker maps a pinned source's data_source id. Studio sources expose agent_id
// which IS the DataSource id in Dash (a connection is a data_source is an agent).
const acSourceOptions = computed(() =>
    sources.value.map(s => ({ label: s.name || s.agent_id, value: String(s.agent_id) }))
)
const acReady = computed(() =>
    !!acSourceId.value &&
    acFiles.value.length > 0 &&
    acFiles.value.some(f => f.fileId) &&
    !acFiles.value.some(f => f.uploading)
)
const acColumnsChecked = computed(() => acColumns.value.filter(c => c.include).length)
const acInstructionsChecked = computed(() => acInstructions.value.filter(i => i.include).length)
const acExamplesChecked = computed(() => acExamples.value.filter(e => e.include).length)

// default the source picker to the first pinned source
watch(sources, (v) => {
    if (!acSourceId.value && v.length) acSourceId.value = String(v[0].agent_id)
}, { immediate: true })

function onAcFileInput(e: Event) {
    const list = (e.target as HTMLInputElement).files
    if (list) addAcFiles(Array.from(list))
    ;(e.target as HTMLInputElement).value = ''
}
function onAcDrop(e: DragEvent) {
    acDragging.value = false
    const list = e.dataTransfer?.files
    if (list) addAcFiles(Array.from(list))
}
function addAcFiles(files: File[]) {
    acError.value = ''
    acProposal.value = null
    for (const f of files) {
        const ext = f.name.toLowerCase().split('.').pop() || ''
        if (!['xlsx', 'pptx'].includes(ext)) { acError.value = `Unsupported file "${f.name}" — use .xlsx or .pptx`; continue }
        const entry: AcFile = { name: f.name, file: f, uploading: true, fileId: null, error: '' }
        acFiles.value.push(entry)
        uploadAcFile(entry)
    }
}
async function uploadAcFile(entry: AcFile) {
    const act = useActivity()
    act.openPanel(); act.start('Auto-configuring from document'); act.setState('processing')
    act.log(`Uploading ${entry.name}…`)
    try {
        const formData = new FormData()
        formData.append('file', entry.file)
        // Mirror UploadSpreadsheetModal: POST /files (multipart, field `file`).
        const { data, error } = await useMyFetch<any>('/files', { method: 'POST', body: formData })
        if (error?.value || !data?.value) {
            entry.error = (error?.value as any)?.data?.detail || 'upload failed'
            act.fail(entry.error || 'Upload failed')
            return
        }
        entry.fileId = (data.value as any).id
        act.log(`Uploaded ${entry.name}`, 'ok')
    } catch (e: any) {
        entry.error = e?.data?.detail || 'upload failed'
        act.fail(entry.error || 'Upload failed')
    } finally {
        entry.uploading = false
    }
}
function removeAcFile(i: number) { acFiles.value.splice(i, 1) }

const acAnalyze = async () => {
    if (!acReady.value) return
    const act = useActivity()
    act.openPanel(); act.start('Auto-configuring from document'); act.setState('processing')
    acAnalyzing.value = true
    acError.value = ''
    acProposal.value = null
    try {
        const fileIds = acFiles.value.map(f => f.fileId).filter(Boolean) as string[]
        act.log('Reading docs · matching columns…')
        const { data, error } = await useMyFetch<any>(`/studios/${studioId.value}/auto-configure/preview`, {
            method: 'POST',
            body: { file_ids: fileIds, data_source_id: acSourceId.value },
        })
        if (error?.value) {
            const st = (error.value as any)?.statusCode || (error.value as any)?.status
            if (st === 404) { acDisabled.value = true; act.fail('Auto-configure unavailable'); return }
            acError.value = (error.value as any)?.data?.detail || (error.value as any)?.message || 'Analyze failed.'
            act.fail(acError.value || 'Analyze failed')
            return
        }
        const res = data.value as any
        if (res?.error) { acError.value = res.error; act.fail(res.error || 'Analyze failed'); return }
        acDisabled.value = false
        acProposal.value = res
        // matched column descriptions — default checked when matched
        acColumns.value = (res.column_descriptions || []).map((c: any) => ({
            column: c.column,
            description: c.description,
            matched: !!c.matched,
            match_kind: c.match_kind,
            table_id: c.table_id,
            matched_column: c.matched_column,
            include: !!c.matched,
        }))
        acUnmatched.value = res.unmatched_columns || []
        // instructions + compliance folded in as additional instructions
        const instr = (res.instructions || []).map((i: any) => ({ content: i.content, compliance: false, include: true }))
        const comp = (res.compliance || []).map((c: any) => ({ content: c.content, compliance: true, include: true }))
        acInstructions.value = [...instr, ...comp]
        acExamples.value = (res.examples || []).map((e: any) => ({ question: e.question, answer: e.answer, sql: e.sql, include: true }))
        // Preview summary: matched columns / rules (instructions+compliance) / examples.
        const matched = acColumns.value.filter(c => c.matched).length
        const total = acColumns.value.length + acUnmatched.value.length
        const nInstr = acInstructions.value.length
        const nEx = acExamples.value.length
        act.log(`Matched ${matched}/${total} columns · ${nInstr} rules · ${nEx} examples`, 'ok')
        if (comp.length) act.log(`${comp.length} compliance rule${comp.length === 1 ? '' : 's'} proposed`, 'warn')
        act.done('Preview ready — review and apply')
    } catch (e: any) {
        acError.value = e?.data?.detail || e?.message || 'Analyze failed.'
        act.fail(acError.value || 'Analyze failed')
    } finally {
        acAnalyzing.value = false
    }
}

const acApply = async () => {
    const act = useActivity()
    act.openPanel(); act.start('Applying configuration'); act.setState('processing')
    act.log('Writing descriptions · drafting rules…')
    acApplying.value = true
    acError.value = ''
    try {
        const payload = {
            data_source_id: acSourceId.value,
            column_descriptions: acColumns.value
                .filter(c => c.include && c.matched)
                .map(c => ({ table_id: c.table_id || null, column: c.column, description: c.description })),
            instructions: acInstructions.value.filter(i => i.include).map(i => ({ content: i.content })),
            examples: acExamples.value.filter(e => e.include).map(e => ({ question: e.question, answer: e.answer || null, sql: e.sql || null })),
        }
        const { data, error } = await useMyFetch<any>(`/studios/${studioId.value}/auto-configure/apply`, {
            method: 'POST',
            body: payload,
        })
        if (error?.value) throw error.value
        const r = data.value as any
        const descWritten = r?.descriptions_written ?? 0
        const instr = r?.instructions_created ?? 0
        const ex = r?.examples_created ?? 0
        toast.add({
            title: 'Applied',
            description: `${descWritten} descriptions · ${instr} instructions · ${ex} examples (pending review)`,
            color: 'green',
            icon: 'i-heroicons-check-circle',
        })
        act.done(`Applied — ${descWritten} descriptions, ${instr} drafts to review`)
        acReset()
        // applied rows land status='pending' → refresh the review queue
        await Promise.all([fetchInstructions(), fetchExamples(), fetchDocs()])
    } catch (e: any) {
        acError.value = e?.data?.detail || e?.message || 'Apply failed.'
        act.fail(acError.value || 'Apply failed')
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        acApplying.value = false
    }
}

const acReset = () => {
    acFiles.value = []
    acProposal.value = null
    acColumns.value = []
    acUnmatched.value = []
    acInstructions.value = []
    acExamples.value = []
    acError.value = ''
}

// ---- Feature 5: self-learning review queue (pending instr + examples) ----
const pendingInstructions = computed(() => instructions.value.filter(i => i.status === 'pending'))
const pendingExamples = computed(() => examples.value.filter(e => e.status === 'pending'))
const reviewQueueCount = computed(() => pendingInstructions.value.length + pendingExamples.value.length)

// auto-approve auto-generated rules/examples (per studio, persisted). When on,
// Auto-train approves what it generates — the "no manual steps" promise.
const autoApproveReview = ref(true)
if (process.client) {
    const saved = localStorage.getItem('ca_auto_approve_review')
    if (saved !== null) autoApproveReview.value = saved === '1'
}
watch(autoApproveReview, (v) => { if (process.client) localStorage.setItem('ca_auto_approve_review', v ? '1' : '0') })

const approvingAll = ref(false)
async function approveAllPending() {
    if (approvingAll.value) return
    approvingAll.value = true
    try {
        // fire all approvals concurrently (bounded by the browser's own pool)
        const calls: Promise<any>[] = []
        for (const ins of [...pendingInstructions.value]) {
            calls.push(useMyFetch(`/studios/${studioId.value}/instructions/${ins.id}/approve`, { method: 'POST' }).catch(() => {}))
        }
        for (const ex of [...pendingExamples.value]) {
            calls.push(useMyFetch(`/studios/${studioId.value}/examples/${ex.id}/approve`, { method: 'POST' }).catch(() => {}))
        }
        for (const d of docs.value.filter((x: any) => x.status !== 'approved')) {
            calls.push(useMyFetch(`/knowledge/doc/${d.id}/approve`, { method: 'POST' }).catch(() => {}))
        }
        await Promise.allSettled(calls)
        await Promise.all([fetchInstructions(), fetchExamples(), fetchDocs()])
    } finally { approvingAll.value = false }
}

// Per-tab count badges in the left rail. Only items whose data is loaded on this
// page have a count; sub-component tabs (tables/tools/queries) self-render counts.
const tabCounts = computed<Record<string, number>>(() => ({
    sources: sources.value.length,
    knowledge: docs.value.length,
    instructions: instructions.value.length,
    examples: examples.value.length,
    skills: pinnedSkills.value.length,
}))

// Pre-train every pinned source: profile columns + propose knowledge. The studio
// source's agent_id IS the DataSource id (a connection is a data_source in Dash).
async function runStudioPretrain() {
    if (pretraining.value || !sources.value.length) return
    const act = useActivity()
    act.openPanel(); act.start('Pre-training agent'); act.setState('processing')
    act.log('Profiling columns · learning real values…')
    pretraining.value = true
    pretrainResult.value = null
    let rows = 0, cols = 0, know = 0, disabled = false, trained = 0
    try {
        for (const s of sources.value) {
            const dsId = String(s.agent_id)
            try {
                const { data, error } = await useMyFetch<any>(`/data_sources/${dsId}/pretrain`, {
                    method: 'POST',
                    // Auto-apply everything live — no review step (per the unified design).
                    body: { suggest_knowledge: true, auto_approve: true },
                })
                if (error?.value) throw error.value
                const r = data.value || {}
                if (r.disabled) { disabled = true; continue }
                trained += 1
                rows += Number(r.row_count || 0)
                cols += Number(r.columns_written || 0)
                const k = r.knowledge || {}
                know += (k.semantics?.length || 0) + (k.metrics?.length || 0)
                act.log(`${s.name || dsId}: ${r.columns_written || 0} columns · ${r.row_count || 0} rows`)
            } catch (e: any) {
                act.log(`${s.name || dsId}: ${e?.data?.detail || e?.message || 'failed'}`)
            }
        }
        if (disabled && !trained) {
            act.fail('Pre-train is off — enable Column Intelligence in Settings → Feature Flags.')
            toast.add({ title: 'Pre-train disabled', description: 'Enable Column Intelligence in Settings → Feature Flags.', color: 'amber', icon: 'i-heroicons-information-circle' })
            return
        }
        pretrainResult.value = { row_count: rows, columns_written: cols, knowledge: know, sources: trained }
        act.done(`Trained on ${rows.toLocaleString()} rows · ${cols} columns · ${know} knowledge`)
        toast.add({ title: 'Agent pre-trained', description: `${rows.toLocaleString()} rows · ${cols} columns · ${know} knowledge`, color: 'green', icon: 'i-heroicons-check-circle' })
        // refresh every surface the train touched
        await Promise.all([fetchInstructions(), fetchExamples(), fetchDocs(), fetchJoins()])
        for (const s of sources.value) fetchIntel((s as any).agent_id, true)
    } finally {
        pretraining.value = false
    }
}

const tabs = computed(() => [
    // Chat has no rail entry (the studio header acts as the chat/home button and the
    // content header carries a New chat button) — keep it as a hidden tab value.
    { value: 'chat', label: t('studio.tabChat'), icon: 'i-heroicons-chat-bubble-left-right', group: 'hidden' },
    // AI Auto-pilot — the studio home: readiness, capability map, one-button train.
    { value: 'autopilot', label: 'Auto-pilot', icon: 'i-heroicons-sparkles', group: 'main' },
    // Sources + Knowledge are ONE surface now: each pinned agent card holds the
    // docs that ground it; org-wide knowledge sits below. (Design A.)
    { value: 'sources', label: t('studio.tabSources'), icon: 'i-heroicons-circle-stack', group: 'knowledge' },
    // Connection + Tables now live INSIDE each source card (Design A). Tools/Queries stay.
    { value: 'tools', label: t('studio.tabTools') || 'Tools', icon: 'i-heroicons-wrench-screwdriver', group: 'knowledge' },
    // The 5 knowledge sub-tabs, each mounting StudioQueries pinned to one sub-tab via :forceTab.
    { value: 'k_semantic', label: 'Semantic', icon: 'i-heroicons-rectangle-group', group: 'knowledge' },
    { value: 'k_metrics', label: 'Metrics', icon: 'i-heroicons-variable', group: 'knowledge' },
    { value: 'k_queries', label: 'Queries', icon: 'i-heroicons-code-bracket-square', group: 'knowledge' },
    { value: 'k_assets', label: 'Assets', icon: 'i-heroicons-cube', group: 'knowledge' },
    { value: 'k_review', label: 'Review', icon: 'i-heroicons-check-circle', group: 'knowledge' },
    { value: 'instructions', label: t('studio.tabInstructions'), icon: 'i-heroicons-clipboard-document-list', group: 'behavior' },
    { value: 'examples', label: t('studio.tabExamples'), icon: 'i-heroicons-academic-cap', group: 'behavior' },
    // Teach Box — paste an analysis, classify into skill/instruction/data-rule/knowledge.
    // Gated by HYBRID_TEACH_BOX (per-org flag); hidden when off.
    ...(teachEnabled.value ? [{ value: 'teach', label: 'Teach', icon: 'i-heroicons-sparkles', group: 'behavior' }] : []),
    // Skills — review/approve domain packs bound to this studio's data.
    // Gated by HYBRID_DOMAIN_PACKS (per-org flag); hidden when off.
    ...(packsEnabled.value ? [{ value: 'skills', label: 'Skills', icon: 'i-heroicons-puzzle-piece', group: 'behavior' }] : []),
    // Skills hidden — off platform-wide for stability; a grounded agent answers from
    // data + knowledge. (Re-add with group:'behavior' to expose.)
    { value: 'evals', label: t('studio.tabEvals') || 'Evals', icon: 'i-heroicons-beaker', group: 'operate' },
    { value: 'monitoring', label: t('studio.tabMonitoring') || 'Monitoring', icon: 'i-heroicons-chart-bar', group: 'operate' },
    { value: 'artifacts', label: t('studio.tabArtifacts'), icon: 'i-heroicons-document-text', group: 'operate' },
    { value: 'settings', label: t('studio.tabSettings'), icon: 'i-heroicons-cog-6-tooth', group: 'manage' },
    { value: 'members', label: t('studio.tabMembers'), icon: 'i-heroicons-users', group: 'manage' },
])

// Group the tabs into the left-rail sections. Group headers are literal English
// (these are new labels; no i18n key yet — and i18n t() returns the key string
// when missing, which would leak the raw key).
const navGroups = computed(() => {
    const order = [
        { key: 'main', label: '' },
        { key: 'knowledge', label: 'Knowledge' },
        { key: 'behavior', label: 'Behavior' },
        { key: 'operate', label: 'Operate' },
        { key: 'manage', label: 'Manage' },
    ]
    return order.map(o => ({ ...o, items: tabs.value.filter(tb => tb.group === o.key) }))
})

// Owner derives editor+viewer; the page reads `role` returned from the studio
// access path. The backend GET doesn't return the caller role, so we infer it:
// owner_user_id match → owner; otherwise default viewer (editor actions still
// enforced server-side, which gives the authoritative answer on write).
const canEdit = computed(() => role.value === 'owner' || role.value === 'editor')

const isImageAvatar = computed(() => {
    const a = studio.value?.avatar || ''
    return /^https?:\/\//.test(a) || a.startsWith('/')
})
const scopeLabel = computed(() => {
    const s = (studio.value?.share_scope || 'private').toLowerCase()
    if (s === 'org') return t('studio.scopeOrg')
    if (s === 'link') return t('studio.scopeLink')
    return t('studio.scopePrivate')
})
const scopeBadgeClass = computed(() => {
    const s = (studio.value?.share_scope || 'private').toLowerCase()
    if (s === 'org') return 'bg-[#F4E5DA] text-[#A8542F]'
    if (s === 'link') return 'bg-purple-100 text-purple-700'
    return 'bg-gray-100 text-gray-600'
})

const fetchStudio = async () => {
    loading.value = true
    notFound.value = false
    try {
        const { data, error } = await useMyFetch<Studio>(`/studios/${studioId.value}`, { method: 'GET' })
        if (error?.value) throw error.value
        studio.value = data.value
        voiceDraft.value = studio.value?.persona || ''
        // Infer caller role from ownership; editor/viewer distinction is enforced
        // server-side on write. Owner gets the management UI.
        const uid = String((currentUser.value as any)?.id ?? '')
        role.value = studio.value && String(studio.value.owner_user_id) === uid ? 'owner' : 'editor'
    } catch (e: any) {
        console.error('Failed to load studio:', e)
        notFound.value = true
    } finally {
        loading.value = false
    }
}

const fetchSources = async () => {
    try {
        const { data, error } = await useMyFetch<Source[]>(`/studios/${studioId.value}/sources`, { method: 'GET' })
        if (error?.value) throw error.value
        sources.value = data.value || []
    } catch (e: any) {
        if (e?.statusCode === 404 || e?.status === 404) sources.value = []
        else console.error('Failed to load sources:', e)
    }
}

const fetchPinnedSkills = async () => {
    loadingSkills.value = true
    try {
        const { data, error } = await useMyFetch<SkillItem[]>(`/studios/${studioId.value}/skills`, { method: 'GET' })
        if (error?.value) throw error.value
        pinnedSkills.value = data.value || []
    } catch (e: any) {
        // 404 = studio_skills route not available yet → empty, don't crash.
        if (e?.statusCode === 404 || e?.status === 404) pinnedSkills.value = []
        else console.error('Failed to load pinned skills:', e)
    } finally {
        loadingSkills.value = false
    }
}

const fetchChats = async () => {
    loadingChats.value = true
    try {
        // No studio_id filter on /reports, so fetch the user's reports and filter
        // client-side by studio_id. Bounded by limit.
        const { data, error } = await useMyFetch<any>('/reports?filter=my&limit=50', { method: 'GET' })
        if (error?.value) throw error.value
        const items = (data.value?.reports || data.value?.items || data.value || []) as any[]
        chats.value = items.filter((r: any) => String(r.studio_id || '') === studioId.value)
    } catch (e: any) {
        console.error('Failed to load studio chats:', e)
        chats.value = []
    } finally {
        loadingChats.value = false
    }
}

// ---- sources ----
const allAgents = ref<any[]>([])
const loadingAgents = ref(false)
const pinnableAgents = computed(() => {
    const pinnedIds = new Set(sources.value.map(s => String(s.agent_id)))
    return allAgents.value.filter(a => !pinnedIds.has(String(a.id)))
})

const openAddSource = async () => {
    showAddSource.value = true
    loadingAgents.value = true
    try {
        const { data, error } = await useMyFetch<any[]>('/data_sources', { method: 'GET' })
        if (error?.value) throw error.value
        allAgents.value = data.value || []
    } catch (e: any) {
        console.error('Failed to load data sources:', e)
        allAgents.value = []
    } finally {
        loadingAgents.value = false
    }
}

const pinSource = async (agent: any) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/sources`, {
            method: 'POST',
            body: { agent_id: String(agent.id) },
        })
        if (error?.value) throw error.value
        showAddSource.value = false
        await fetchSources()
    } catch (e: any) {
        console.error('Failed to pin source:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const openUploadSource = () => { showUploadSource.value = true }

// Upload modal created a NEW Data Agent → auto-pin it to this studio (reuse the
// same pinSource path: POST /studios/{id}/sources {agent_id}), then refresh.
const onUploadCreated = async (dataSource: any) => {
    showUploadSource.value = false
    if (!dataSource?.id) { await fetchSources(); return }
    try {
        await pinSource(dataSource)   // reads dataSource.id, posts {agent_id}
        await fetchSources()
        toast.add({ title: dataSource.name ? `“${dataSource.name}” pinned` : t('studio.savedSharing'), color: 'green', icon: 'i-heroicons-check-circle' })
    } catch (e: any) {
        console.error('Failed to auto-pin uploaded source:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const unpinSource = async (agentId: string) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/sources/${agentId}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        await fetchSources()
    } catch (e: any) {
        console.error('Failed to unpin source:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

// ---- skills ----
const allSkills = ref<SkillItem[]>([])
const loadingAllSkills = ref(false)
const pinnableSkills = computed(() => {
    const pinnedIds = new Set(pinnedSkills.value.map(s => String(s.id)))
    return allSkills.value.filter(s => !pinnedIds.has(String(s.id)))
})

const openAddSkill = async () => {
    showAddSkill.value = true
    loadingAllSkills.value = true
    try {
        const { data, error } = await useMyFetch<SkillItem[]>('/skills', { method: 'GET' })
        if (error?.value) throw error.value
        allSkills.value = data.value || []
    } catch (e: any) {
        console.error('Failed to load skills:', e)
        allSkills.value = []
    } finally {
        loadingAllSkills.value = false
    }
}

const pinSkill = async (skill: SkillItem) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/skills`, {
            method: 'POST',
            body: { skill_id: String(skill.id) },
        })
        if (error?.value) throw error.value
        showAddSkill.value = false
        await fetchPinnedSkills()
    } catch (e: any) {
        console.error('Failed to pin skill:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const unpinSkill = async (skillId: string) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/skills/${skillId}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        await fetchPinnedSkills()
    } catch (e: any) {
        console.error('Failed to unpin skill:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

// ---- chat ----
// Lightest integration: create a report carrying studio_id + the studio's pinned
// sources, then navigate to the existing report chat UI (/reports/{id}).
const startChat = async (seed?: string) => {
    if (sources.value.length === 0) return
    creatingChat.value = true
    try {
        const body: Record<string, any> = {
            title: `${studio.value?.name || 'Studio'} chat`,
            files: [],
            data_sources: sources.value.map(s => String(s.agent_id)),
            studio_id: studioId.value,
        }
        // A suggested-question chip seeds the first prompt; the report chat reads
        // ?prompt= to auto-send on open (graceful no-op if it doesn't).
        const q = typeof seed === 'string' ? seed.trim() : ''
        const { data, error } = await useMyFetch<any>('/reports', { method: 'POST', body })
        if (error?.value) throw error.value
        const created = data.value
        if (created?.id) {
            router.push(q ? `/reports/${created.id}?prompt=${encodeURIComponent(q)}` : `/reports/${created.id}`)
        }
    } catch (e: any) {
        console.error('Failed to start studio chat:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        creatingChat.value = false
    }
}

const openChat = (reportId: string) => router.push(`/reports/${reportId}`)

// ---- status badges (shared by instructions + examples) ----
const statusLabel = (s?: string) => {
    if (s === 'active' || s === 'approved') return t('studio.statusActive')
    if (s === 'rejected') return t('studio.statusRejected')
    return t('studio.statusPending')
}
const statusBadgeClass = (s?: string) => {
    if (s === 'active' || s === 'approved') return 'bg-green-100 text-green-700'
    if (s === 'rejected') return 'bg-gray-100 text-gray-500'
    return 'bg-amber-100 text-amber-700'
}

// ---- instructions ----
// All routes are flag-gated server-side; a 404 means the harness flag is OFF →
// render an empty tab rather than crash.
const fetchInstructions = async () => {
    loadingInstr.value = true
    try {
        const { data, error } = await useMyFetch<Instruction[]>(`/studios/${studioId.value}/instructions`, { method: 'GET' })
        if (error?.value) throw error.value
        instructions.value = data.value || []
    } catch (e: any) {
        if (e?.statusCode === 404 || e?.status === 404) instructions.value = []
        else console.error('Failed to load instructions:', e)
    } finally {
        loadingInstr.value = false
    }
}

const openAddInstruction = () => { newInstrDraft.value = ''; showAddInstruction.value = true }

const createInstruction = async () => {
    if (!newInstrDraft.value.trim()) return
    savingInstr.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/instructions`, {
            method: 'POST',
            body: { content: newInstrDraft.value.trim() },
        })
        if (error?.value) throw error.value
        showAddInstruction.value = false
        await fetchInstructions()
    } catch (e: any) {
        console.error('Failed to add instruction:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        savingInstr.value = false
    }
}

const startInstructionEdit = (ins: Instruction) => { editingInstrId.value = ins.id; editInstrDraft.value = ins.content }

const saveInstructionEdit = async (ins: Instruction) => {
    savingInstr.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/instructions/${ins.id}`, {
            method: 'PATCH',
            body: { content: editInstrDraft.value },
        })
        if (error?.value) throw error.value
        editingInstrId.value = null
        await fetchInstructions()
    } catch (e: any) {
        console.error('Failed to edit instruction:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        savingInstr.value = false
    }
}

const approveInstruction = async (ins: Instruction) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/instructions/${ins.id}/approve`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchInstructions()
    } catch (e: any) {
        console.error('Failed to approve instruction:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const rejectInstruction = async (ins: Instruction) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/instructions/${ins.id}/reject`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchInstructions()
    } catch (e: any) {
        console.error('Failed to reject instruction:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const deleteInstruction = async (ins: Instruction) => {
    if (!window.confirm(t('studio.deleteConfirmGeneric'))) return
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/instructions/${ins.id}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        await fetchInstructions()
    } catch (e: any) {
        console.error('Failed to delete instruction:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const regenerateInstructions = async () => {
    regenInstr.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/instructions/regenerate`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchInstructions()
        toast.add({ title: t('studio.regenerated'), color: 'green', icon: 'i-heroicons-sparkles' })
    } catch (e: any) {
        console.error('Failed to regenerate instructions:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        regenInstr.value = false
    }
}

// ---- examples ----
const fetchExamples = async () => {
    loadingEx.value = true
    try {
        const { data, error } = await useMyFetch<Example[]>(`/studios/${studioId.value}/examples`, { method: 'GET' })
        if (error?.value) throw error.value
        examples.value = data.value || []
    } catch (e: any) {
        if (e?.statusCode === 404 || e?.status === 404) examples.value = []
        else console.error('Failed to load examples:', e)
    } finally {
        loadingEx.value = false
    }
}

const openAddExample = () => { newEx.question = ''; newEx.answer = ''; newEx.sql = ''; showAddExample.value = true }

const createExample = async () => {
    if (!newEx.question.trim()) return
    savingEx.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/examples`, {
            method: 'POST',
            body: {
                question: newEx.question.trim(),
                answer: newEx.answer.trim() || null,
                sql: newEx.sql.trim() || null,
            },
        })
        if (error?.value) throw error.value
        showAddExample.value = false
        await fetchExamples()
    } catch (e: any) {
        console.error('Failed to add example:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        savingEx.value = false
    }
}

const startExampleEdit = (ex: Example) => {
    editingExId.value = ex.id
    editEx.question = ex.question
    editEx.answer = ex.answer || ''
    editEx.sql = ex.sql || ''
}

const saveExampleEdit = async (ex: Example) => {
    savingEx.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/examples/${ex.id}`, {
            method: 'PATCH',
            body: {
                question: editEx.question,
                answer: editEx.answer || null,
                sql: editEx.sql || null,
            },
        })
        if (error?.value) throw error.value
        editingExId.value = null
        await fetchExamples()
    } catch (e: any) {
        console.error('Failed to edit example:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        savingEx.value = false
    }
}

const approveExample = async (ex: Example) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/examples/${ex.id}/approve`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchExamples()
    } catch (e: any) {
        console.error('Failed to approve example:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const rejectExample = async (ex: Example) => {
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/examples/${ex.id}/reject`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchExamples()
    } catch (e: any) {
        console.error('Failed to reject example:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const deleteExample = async (ex: Example) => {
    if (!window.confirm(t('studio.deleteConfirmGeneric'))) return
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/examples/${ex.id}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        await fetchExamples()
    } catch (e: any) {
        console.error('Failed to delete example:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const regenerateExamples = async () => {
    regenEx.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}/examples/regenerate`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchExamples()
        toast.add({ title: t('studio.regenerated'), color: 'green', icon: 'i-heroicons-sparkles' })
    } catch (e: any) {
        console.error('Failed to regenerate examples:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        regenEx.value = false
    }
}

// ---- settings: voice (= persona) + auto avatar/summary ----
const saveVoice = async () => {
    savingVoice.value = true
    try {
        const { data, error } = await useMyFetch<Studio>(`/studios/${studioId.value}`, {
            method: 'PATCH',
            body: { persona: voiceDraft.value },
        })
        if (error?.value) throw error.value
        if (data.value) { studio.value = data.value; voiceDraft.value = data.value.persona || '' }
        toast.add({ title: t('studio.savedSharing'), color: 'green', icon: 'i-heroicons-check-circle' })
    } catch (e: any) {
        console.error('Failed to save voice:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        savingVoice.value = false
    }
}

// Voice/avatar regenerate reuse the bootstrap pipeline via "improve now"; if a
// dedicated regen route isn't exposed yet we fall back to improveNow + refetch.
const regenerateVoice = async () => {
    regenVoice.value = true
    try {
        await runImprove()
        await fetchStudio()
    } finally {
        regenVoice.value = false
    }
}
const regenerateAvatar = async () => {
    regenAvatar.value = true
    try {
        await runImprove()
        await fetchStudio()
    } finally {
        regenAvatar.value = false
    }
}

// ---- artifacts (suggested questions + summary) ----
const fetchStudioArtifacts = async () => {
    try {
        const { data, error } = await useMyFetch<ArtifactItem[]>(`/studios/${studioId.value}/artifacts`, { method: 'GET' })
        if (error?.value) throw error.value
        const items = data.value || []
        const sq = items.find(a => a.kind === 'suggested_questions')
        suggestedQuestions.value = parseSuggested(sq?.content)
        const sum = items.find(a => a.kind === 'summary')
        summaryText.value = sum?.content || ''
    } catch (e: any) {
        if (e?.statusCode === 404 || e?.status === 404) { suggestedQuestions.value = []; summaryText.value = '' }
        else console.error('Failed to load studio artifacts:', e)
    }
}

// suggested_questions content may be a JSON array, newline list, or markdown
// bullets — normalize all into a string[].
const parseSuggested = (raw?: string | null): string[] => {
    if (!raw) return []
    const s = raw.trim()
    try {
        const j = JSON.parse(s)
        if (Array.isArray(j)) return j.map(x => String(x).trim()).filter(Boolean).slice(0, 6)
    } catch { /* not JSON, fall through */ }
    return s.split('\n')
        .map(l => l.replace(/^[\s\-*\d.)]+/, '').trim())
        .filter(Boolean)
        .slice(0, 6)
}

// ---- improve now ----
const runImprove = async () => {
    const { data, error } = await useMyFetch<any>(`/studios/${studioId.value}/improve`, { method: 'POST' })
    if (error?.value) throw error.value
    return data.value
}

const improveNow = async () => {
    improving.value = true
    try {
        const res = await runImprove()
        const ex = res?.examples ?? 0
        const rules = res?.rules ?? 0
        toast.add({
            title: t('studio.improveDone'),
            description: t('studio.improveCounts', { examples: ex, rules }),
            color: 'green',
            icon: 'i-heroicons-sparkles',
        })
        await Promise.all([fetchInstructions(), fetchExamples(), fetchStudioArtifacts()])
    } catch (e: any) {
        console.error('Failed to improve studio:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        improving.value = false
    }
}

// ---- share / delete ----
const onShareUpdated = (payload: { share_scope: string; share_token: string | null }) => {
    if (studio.value) {
        studio.value.share_scope = payload.share_scope
        studio.value.share_token = payload.share_token
    }
}

const deleteStudio = async () => {
    if (!window.confirm(t('studio.deleteConfirm'))) return
    deleting.value = true
    try {
        const { error } = await useMyFetch(`/studios/${studioId.value}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        toast.add({ title: t('studio.studioDeleted'), color: 'green', icon: 'i-heroicons-check-circle' })
        router.push('/studios')
    } catch (e: any) {
        console.error('Failed to delete studio:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        deleting.value = false
    }
}

// ---- knowledge docs ----
const fetchDocs = async () => {
    loadingDocs.value = true
    try {
        // Merged view groups docs per source client-side → always fetch the full set.
        const { data, error } = await useMyFetch<any>(`/knowledge/docs`, { method: 'GET' })
        if (error?.value) throw error.value
        docs.value = (data.value?.docs || []) as KnowledgeDoc[]
        const st = data.value?.stats || {}
        docStats.value = { total: st.total || 0, approved: st.approved || 0, pending: st.pending || 0 }
    } catch (e: any) {
        if (e?.statusCode === 404 || e?.status === 404) { docs.value = []; docStats.value = { total: 0, approved: 0, pending: 0 } }
        else console.error('Failed to load knowledge docs:', e)
    } finally {
        loadingDocs.value = false
    }
}

const createDoc = async () => {
    if (!newDoc.title.trim() || !newDoc.body.trim()) return
    savingDoc.value = true
    try {
        const { data, error } = await useMyFetch<any>('/knowledge/docs', {
            method: 'POST',
            body: {
                title: newDoc.title.trim(),
                body: newDoc.body.trim(),
                source: 'paste',
                data_source_id: docSourceId.value,
            },
        })
        if (error?.value) throw error.value
        if (data.value?.disabled) {
            docsDisabled.value = true
            return
        }
        docsDisabled.value = false
        newDoc.title = ''
        newDoc.body = ''
        closeAddKnowledge()
        toast.add({ title: t('studio.addToKnowledge') || 'Added to knowledge', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchDocs()
    } catch (e: any) {
        console.error('Failed to add knowledge doc:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    } finally {
        savingDoc.value = false
    }
}

const approveDoc = async (d: KnowledgeDoc) => {
    try {
        const { error } = await useMyFetch(`/knowledge/doc/${d.id}/approve`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchDocs()
    } catch (e: any) {
        console.error('Failed to approve doc:', e)
        toast.add({ title: t('studio.actionFailed'), color: 'red' })
    }
}

const rejectDoc = async (d: KnowledgeDoc) => {
    try {
        const { error } = await useMyFetch(`/knowledge/doc/${d.id}/reject`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchDocs()
    } catch (e: any) {
        // Reject route may not exist → hide the button and keep approve.
        if (e?.statusCode === 404 || e?.status === 404) { docRejectHidden.value = true }
        else { console.error('Failed to reject doc:', e); toast.add({ title: t('studio.actionFailed'), color: 'red' }) }
    }
}

// Sources + Auto-pilot both need docs/intel/joins (readiness reads them).
watch(activeTab, (tab) => {
    if (tab !== 'sources' && tab !== 'autopilot') return
    fetchDocs(); fetchJoins(); fetchArtifactCount()
    for (const s of sources.value) fetchIntel((s as any).agent_id)
}, { immediate: true })
// sources may load after the tab is already active → backfill intel + joins.
watch(sources, (v) => {
    if (activeTab.value === 'sources' || activeTab.value === 'autopilot') {
        for (const s of v) fetchIntel((s as any).agent_id)
        if (v.length) fetchJoins()
    }
})

onMounted(async () => {
    await fetchStudio()
    if (!notFound.value) {
        await Promise.all([
            fetchSources(),
            fetchPinnedSkills(),
            fetchChats(),
            fetchInstructions(),
            fetchExamples(),
            fetchStudioArtifacts(),
            loadTeachFlag(),
            loadPacksFlag(),
        ])
    }
})
</script>

<style scoped>
.line-clamp-1 {
    display: -webkit-box;
    -webkit-line-clamp: 1;
    line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.line-clamp-2 {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

/* Claude redesign: neutralize the scope-badge palette.
   scopeBadgeClass (script computed) emits clay tints for org (bg-[#F4E5DA]/text-[#A8542F])
   and bg-purple-100/text-purple-700 (link). Only the purple link utilities need recoloring
   here to clay-soft per the mockup; the org badge is already clay via its computed classes. */
.bg-purple-100 { background-color: #F3E7DF !important; }
.text-purple-700 { color: #C2683F !important; }
</style>
