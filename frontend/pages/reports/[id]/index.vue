<template>

	<!-- Loading until report and completions are fetched -->
	<div v-if="(!report || !completionsLoaded) && !reportNotFound" class="h-full w-full flex items-center justify-center text-gray-500">
		<Spinner class="w-5 h-5 me-2" />
		<span class="text-sm">{{ $t('reportView.loadingReport') }}</span>
	</div>

	<!-- Report not found / no access -->
	<div v-else-if="reportNotFound" class="h-full w-full flex flex-col items-center justify-center text-gray-400">
		<span class="text-5xl font-light">404</span>
		<span class="mt-2 text-sm">{{ $t('reportView.reportNotFound') }}</span>
		<NuxtLink to="/reports" class="mt-4 text-sm text-[#C2541E] hover:text-[#A8330F] hover:underline">{{ $t('reportView.backToReports') }}</NuxtLink>
	</div>

	<SplitScreenLayout v-else
		:isSplitScreen="isSplitScreen && !isMobile"
		:leftPanelWidth="leftPanelWidth"
		:isResizing="isResizing"
		:dashboardFirst="dashboardFirst && !isMobile"
		:dockWidth="dockWidth"
		@startResize="startResize"
		@update:dockWidth="setDockWidth"
	>
		<template #left>
	<div class="chat-pane flex flex-col h-full overflow-y-hidden bg-[#FAF8F3] relative"
		:class="{ 'dash-dock': dashboardFirst && !isMobile }"
		:style="(dashboardFirst && !isMobile) ? { minWidth: 0, overflowX: 'hidden' } : undefined">
		<!-- Dashboard-first: collapsed chat dock = thin rail (just an expand chevron). -->
		<div
			v-if="dashboardFirst && !isMobile && dockCollapsed"
			class="absolute inset-0 z-40 bg-[#FAF8F3] border-s border-[#E9E0D3] flex flex-col items-center pt-3"
		>
			<button
				@click="toggleDockCollapsed"
				aria-label="Expand chat dock"
				title="Expand chat"
				class="flex items-center justify-center w-8 h-8 rounded-lg text-[#6b6b6b] hover:bg-[#F4EEE5] transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2541E]"
			>
				<Icon name="heroicons:chat-bubble-left-right" class="w-5 h-5 text-[#C2541E]" />
			</button>
		</div>
		<!-- Dashboard-first: dock header (collapse chevron + "Switch to chat-first"). -->
		<div
			v-if="dashboardFirst && !isMobile && !dockCollapsed"
			class="shrink-0 flex items-center justify-between gap-2 px-3 py-2 border-b border-[#E9E0D3] bg-[#FAF8F3]"
		>
			<button
				@click="exitDashboardFirst"
				class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-[#E9E0D3] text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2541E]"
			>
				<Icon name="heroicons:chat-bubble-left-right" class="w-4 h-4" />
				Switch to chat-first
			</button>
			<button
				@click="toggleDockCollapsed"
				aria-label="Collapse chat dock"
				title="Collapse chat"
				class="flex-none flex items-center justify-center w-7 h-7 rounded-lg text-[#9a958c] hover:text-[#1f2328] hover:bg-[#F4EEE5] transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2541E]"
			>
				<Icon name="heroicons:chevron-double-right" class="w-4 h-4" />
			</button>
		</div>
		<!-- Slide-workspace dock header: replaces the conversation title + Share with a
		     clean "Edit & analyze slides" label so the dock reads as a slide assistant,
		     not the raw historical thread. Same chat/composer below is untouched. -->
		<header
			v-if="report && slidesFocus && !isMobile"
			class="sticky top-0 bg-white z-10 flex flex-row pt-1 h-[40px] pb-1 pe-2 ps-2 items-center border-gray-200"
		>
			<svg width="18" height="18" viewBox="0 0 48 48" class="flex-none me-2"><circle cx="27" cy="21" r="15" fill="url(#ppO)"/><rect x="6" y="17" width="22" height="22" rx="5" fill="url(#ppP)"/><path d="M12 22h6.5a4 4 0 0 1 0 8H15v4h-3V22zm3 3v2.5h3.2a1.25 1.25 0 0 0 0-2.5H15z" fill="#fff"/></svg>
			<h1 class="text-sm font-semibold text-[#1f2328] truncate">Edit &amp; analyze slides</h1>
			<button
				@click="exitDashboardFirst"
				title="Switch to chat-first layout"
				class="ms-auto flex-none inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-[#E9E0D3] text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E]"
			>
				<Icon name="heroicons:chat-bubble-left-right" class="w-3.5 h-3.5" />
				Chat-first
			</button>
		</header>
		<ReportHeader
			v-else-if="report"
			:report="report"
			:isSplitScreen="isSplitScreen"
			:isStreaming="isStreaming"
			:isMobile="isMobile"
			:mobileView="mobileView"
			@toggleSplitScreen="toggleSplitScreen"
			@stop="abortStream"
			@update:mobileView="(v: any) => mobileView = v"
		/>

		<!-- Grounding strip (bounded-context visibility): what Knowledge grounds
		     this report's answers. Only shows when the data sources have approved
		     semantic tables. -->
		<div
			v-if="!isMobile && groundingScope.tables_total > 0"
			class="shrink-0 px-4 py-1.5 border-b border-gray-100 flex items-center justify-center"
		>
			<div class="flex items-center gap-2 text-[11px] text-gray-400">
				<UIcon name="i-heroicons-circle-stack" class="w-3 h-3" />
				<span>Grounded on
					<template v-if="groundingScope.tables_injected === groundingScope.tables_total"><span class="text-gray-600 font-medium">all {{ groundingScope.tables_total }}</span> tables</template>
					<template v-else><span class="text-gray-600 font-medium">{{ groundingScope.tables_injected }}</span> of {{ groundingScope.tables_total }} tables</template>
				</span>
				<template v-if="groundingScope.metrics_total">
					<span class="text-gray-300">·</span>
					<span>
						<template v-if="groundingScope.metrics_injected === groundingScope.metrics_total"><span class="text-gray-600 font-medium">all {{ groundingScope.metrics_total }}</span> metrics</template>
						<template v-else><span class="text-gray-600 font-medium">{{ groundingScope.metrics_injected }}</span> of {{ groundingScope.metrics_total }} metrics</template>
					</span>
				</template>
			</div>
		</div>

		<!-- Mobile right panel content (full screen) -->
		<div v-if="isMobile && mobileView !== 'chat'" class="flex-1 min-h-0 overflow-hidden flex flex-col">
			<div class="flex-1 min-h-0 p-2">
				<div class="h-full w-full bg-[#f8f8f7] rounded-xl border border-black/[0.08] overflow-hidden">
					<!-- Summary View -->
					<div v-if="mobileView === 'summary'" class="h-full overflow-y-auto">
						<ChatSummary
							:reportId="report_id"
							:latestAnswer="latestAnswer"
							:messages="messages"
							:scheduledPrompts="scheduledPrompts"
							:artifactList="reportArtifacts"
							:queryList="queryList"
							:queryExecutions="summaryQueries"
							:trainingInstructions="summaryInstructions"
							:reportInstructions="reportInstructions"
							:pendingBuildId="pendingTrainingBuild?.id || null"
							:pendingTrainingBuild="pendingTrainingBuild"
							:pendingTrainingBuildDiff="pendingTrainingBuildDiff"
							:sessionSummary="sessionSummary"
							:sessionSummaryStale="sessionSummaryStale"
							:sessionSummaryLoading="sessionSummaryLoading"
							:senseMaking="latestSenseMaking"
							:senseMakingPending="decisionForming"
							@refreshSessionSummary="onRefreshSessionSummary"
							@approveTrainingBuild="onApproveTrainingBuild"
							@discardTrainingBuild="onDiscardTrainingBuild"
							@discardTrainingInstruction="onDiscardTrainingInstruction"
							@editScheduledPrompt="editScheduledPrompt"
							@openArtifact="handleOpenArtifact"
							@scrollToMessage="scrollToMessage"
						/>
					</div>
					<!-- Agent View -->
					<div v-else-if="mobileView === 'agent'" class="h-full overflow-y-auto">
						<ReportAgentPanel ref="mobileAgentPanelRef" :agents="currentAgents" @starter-click="handleExampleClick" @connected="handleAgentConnected" />
					</div>
					<!-- Dashboard View -->
					<ArtifactFrame
						v-else-if="mobileView === 'dashboard' && reportLoaded && report?.id"
						:report-id="report.id"
						:report="report"
						@close="mobileView = 'chat'"
						class="h-full"
					/>
				</div>
			</div>
		</div>

		<!-- Chat content (hidden on mobile when viewing other tabs) -->
		<template v-if="!isMobile || mobileView === 'chat'">
		<!-- Fork banner -->
		<ForkBanner
			v-if="report?.forked_from_id"
			:forked-from-id="report.forked_from_id"
			:forked-from-title="report.forked_from_title"
			:forked-from-user-name="report.forked_from_user_name"
		/>

		<!-- Messages -->
		<div class="flex-1 overflow-y-auto mt-4 pb-4" :class="{ 'compact-messages': isExcel }" ref="scrollContainer">
			<div class="ps-4 pe-2 pb-[3px] max-w-2xl w-full mx-auto">

				<!-- Forked queries panel (shown for forked reports) -->
				<ForkedQueriesPanel
					v-if="forkedQueries.length > 0"
					:queries="forkedQueries"
					:artifact-ref="forkedArtifactRef"
				/>

				<!-- Fork summary separator -->
				<div v-if="report?.forked_from_id && nonSeedMessages.length > 0" class="flex items-center gap-3 my-4">
					<div class="flex-1 border-t border-dashed border-gray-200"></div>
					<span class="text-[10px] text-gray-300 uppercase tracking-wider">{{ $t('reportView.yourConversation') }}</span>
					<div class="flex-1 border-t border-dashed border-gray-200"></div>
				</div>

				<ul v-if="messages.length > 0" class="mx-auto w-full">
					<!-- Top loader for older pages -->
					<li v-if="hasMore && isLoadingMore" class="text-gray-500 mb-2 text-xs text-center">
						<Spinner class="w-4 h-4 inline me-2" /> {{ $t('reportView.loadingOlderMessages') }}
					</li>
					<li v-for="m in messages" :key="m.id" :data-message-id="m.id" class="text-gray-700 mb-2 text-sm ca-msg-in">
						<!-- Fork summary card (special rendering) -->
						<div v-if="(m as any).is_fork_summary" class="rounded-lg border border-amber-100 bg-amber-50/50 p-3 mb-4">
							<div class="flex items-center gap-1.5 text-xs text-amber-600 mb-2">
								<Icon name="heroicons:arrow-path-rounded-square" class="w-3.5 h-3.5" />
								<span class="font-medium">{{ $t('reportView.summaryOfOriginal') }}</span>
							</div>
							<div class="text-xs text-gray-600 leading-relaxed whitespace-pre-line">{{ (m as any).completion?.content || '' }}</div>
						</div>

						<!-- Scheduled prompt: collapsible header + user bubble when expanded -->
						<div v-else-if="m.scheduled_prompt_id && m.role === 'user'">
							<button
								@click="toggleScheduledExpand(m.id)"
								class="w-full flex items-center gap-1.5 px-3 py-2 text-xs text-gray-400 rounded-lg border border-gray-100 bg-gray-50/50 hover:bg-gray-50 transition-colors mb-2"
							>
								<Icon name="heroicons-clock" class="w-3.5 h-3.5" />
								<span class="font-medium text-gray-500">{{ $t('reportView.scheduledRun') }}</span>
								<span class="text-gray-300">{{ formatScheduledDate(m.created_at) }}</span>
								<span v-if="getScheduledStats(m)" class="text-gray-300">&middot;</span>
								<span v-if="getScheduledStats(m)" class="text-gray-400">{{ getScheduledStats(m) }}</span>
								<Icon :name="isScheduledExpanded(m.id) ? 'heroicons-chevron-up' : 'heroicons-chevron-down'" class="w-3 h-3 ms-auto flex-shrink-0" />
							</button>
							<!-- User bubble shown inside the collapsible area -->
							<div v-if="isScheduledExpanded(m.id)" class="flex rounded-lg p-1 justify-end">
								<div class="flex items-start gap-2 max-w-xl w-full mb-4">
									<div class="flex-1 flex justify-end">
										<div class="inline-block rounded-xl px-3 py-2 bg-gray-50 text-gray-900 text-start" dir="auto">
											<div v-if="m.prompt?.content" class="pt-1">
												<InstructionText
													:text="m.prompt.content"
													:references="promptMentionsToRefs(m.prompt.mentions)"
													:prose="true"
												/>
											</div>
										</div>
									</div>
									<div class="flex-shrink-0 hidden md:block md:w-[28px]">
										<div class="h-7 w-7 uppercase flex items-center justify-center text-xs border border-[#E8C9B5] bg-[#F4E5DA] rounded-full inline-block">
											{{ report?.user?.name?.charAt(0) }}
										</div>
									</div>
								</div>
							</div>
						</div>

						<!-- Scheduled system message: hide when user header is collapsed -->
						<template v-else-if="m.scheduled_prompt_id && m.role === 'system' && !isScheduledSystemExpanded(m)">
							<!-- collapsed -->
						</template>

						<!-- Inbound webhook event entry (compact) -->
						<div v-else-if="m.role === 'external'" class="my-2">
							<div class="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-100 bg-gray-50/50">
								<Icon :name="webhookSourceIcon((m as any).external_platform)" class="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
								<span class="text-xs text-gray-600 truncate flex-1">{{ m.prompt?.summary || m.prompt?.content }}</span>
								<span v-if="m.status === 'in_progress'" class="flex items-center" :title="'Working…'">
									<Icon name="heroicons-eye" class="w-4 h-4 text-gray-400 animate-pulse" />
								</span>
								<Icon v-else-if="m.status === 'success'" name="heroicons-check-circle" class="w-4 h-4 text-green-500" :title="webhookActed(m) ? 'Responded' : 'No action needed'" />
								<Icon v-else-if="m.status === 'error'" name="heroicons-exclamation-circle" class="w-4 h-4 text-red-400" title="Error" />
								<span v-if="m.created_at" class="text-[10px] text-gray-400 flex-shrink-0">{{ formatMessageDate(m.created_at) }}</span>
							</div>
							<div v-if="webhookDecision(m) && webhookDecision(m).act === false" class="mt-1 ps-3 text-[11px] text-gray-400 italic">
								No action needed<span v-if="webhookDecision(m).reason"> — {{ webhookDecision(m).reason }}</span>
							</div>
						</div>

						<!-- Regular message rendering -->
						<div
							v-else
							class="flex rounded-lg p-1"
							:class="m.role === 'user' ? 'justify-end' : 'justify-start'"
						>
							<!-- User message (start-edge bubble; flips to opposite edge under RTL via ul dir) -->
							<template v-if="m.role === 'user'">
								<div class="group/usermsg flex flex-col items-end max-w-xl w-full mb-3 ms-auto">
									<div class="flex items-start gap-2 w-full">
										<!-- User message bubble -->
										<div class="flex-1 flex justify-end">
											<div class="inline-block rounded-xl px-3 py-2 bg-gray-50 text-gray-900 text-start" dir="auto">
												<div v-if="m.prompt?.content" class="pt-1">
													<InstructionText
														:text="m.prompt.content"
														:references="promptMentionsToRefs(m.prompt.mentions)"
														:prose="true"
													/>
												</div>
												<!-- Attached images thumbnail -->
												<div v-if="getAttachedImages(m).length > 0" class="mt-2 flex flex-wrap gap-1.5">
													<div v-for="file in getAttachedImages(m)" :key="file.id" class="relative group">
														<AuthenticatedImage
															:file-id="file.id"
															:alt="file.filename"
															img-class="h-16 w-16 object-cover rounded-lg border border-gray-200 cursor-pointer hover:opacity-90 transition-opacity"
															@click="openImagePreview(file)" />
													</div>
												</div>
											</div>
										</div>
										<!-- User avatar on the right (hidden on mobile) -->
										<div class="flex-shrink-0 hidden md:block md:w-[28px]">
											<div class="h-7 w-7 uppercase flex items-center justify-center text-xs border border-[#E8C9B5] bg-[#F4E5DA] rounded-full inline-block">
												{{ report?.user?.name?.charAt(0) }}
											</div>
										</div>
									</div>
									<!-- Hover-reveal: copy + timestamp -->
									<div class="flex items-center gap-2 me-[36px] mt-1 opacity-0 group-hover/usermsg:opacity-100 transition-opacity duration-150">
										<UTooltip :text="copiedMessageId === m.id ? 'Copied!' : 'Copy'" :popper="{ placement: 'bottom' }">
											<button
												@click="copyToClipboard(m.prompt?.content, m.id)"
												class="text-[10px] text-gray-400 hover:text-gray-600 flex items-center gap-0.5"
											>
												<Icon :name="copiedMessageId === m.id ? 'heroicons-check' : 'heroicons-clipboard'" class="w-3 h-3" />
												{{ copiedMessageId === m.id ? 'Copied!' : 'Copy' }}
											</button>
										</UTooltip>
										<span v-if="m.created_at" class="text-[10px] text-gray-400">{{ formatMessageDate(m.created_at) }}</span>
									</div>
								</div>
							</template>

							<!-- System / assistant message (left-aligned, keep existing styling) -->
							<template v-else>
								<!-- AI avatar (hidden on mobile) -->
								<div class="w-[28px] me-2 flex-shrink-0 hidden md:block">
									<div class="h-7 w-7 flex font-bold items-center justify-center text-xs rounded-lg inline-block bg-contain bg-center bg-no-repeat" style="background-image: url('/assets/logo-128.png')">
									</div>
								</div>
								<div class="w-full ms-4 max-w-2xl min-w-0">
									<!-- System message -->
									<div>
										<!-- Claude-style "thought process" summary header (steps derived from blocks) -->
										<div
											v-if="(m.completion_blocks || []).some(b => b.tool_execution)"
											class="flex items-center gap-2 mb-2 text-[13px] text-[#7A7066] select-none"
										>
											<template v-if="m.status === 'in_progress'">
												<span class="cai-wave" aria-hidden="true"><svg viewBox="0 0 40 18" preserveAspectRatio="none"><path class="wv wv1" d="M0 9 Q5 3 10 9 T20 9 T30 9 T40 9" stroke="#D67037"/><path class="wv wv2" d="M0 9 Q5 15 10 9 T20 9 T30 9 T40 9" stroke="#C2541E" style="opacity:.55"/></svg></span>
												<span class="ui-serif font-medium text-[#2A2420] truncate cc-shimmer">{{ runningStageText(m) }}</span>
												<span class="cai-wave cai-flip" aria-hidden="true"><svg viewBox="0 0 40 18" preserveAspectRatio="none"><path class="wv wv1" d="M0 9 Q5 3 10 9 T20 9 T30 9 T40 9" stroke="#D67037"/><path class="wv wv2" d="M0 9 Q5 15 10 9 T20 9 T30 9 T40 9" stroke="#C2541E" style="opacity:.55"/></svg></span>
												<span class="ml-1 tabular-nums text-[11.5px] text-[#9A8678] flex-none">{{ liveElapsed(m) }}</span>
											</template>
											<template v-else>
												<Icon name="heroicons:check-circle" class="w-4 h-4 text-[#3F7A4F]" />
												<span class="ui-serif">Thought process · {{ blocksToSteps(m.completion_blocks || []).length }} step{{ blocksToSteps(m.completion_blocks || []).length === 1 ? '' : 's' }} · Done</span>
											</template>
										</div>
										<!-- Render each completion block - unified structure -->
										<div v-for="(block, blockIndex) in (m.completion_blocks || []).filter(b => b.phase !== 'knowledge_harness')" :key="block.id"
												:class="{ 'cc-step': !!block.tool_execution && block.tool_execution.tool_name !== 'clarify', 'cc-step--done': !!block.tool_execution && block.tool_execution.status === 'success', 'cc-step--err': !!block.tool_execution && block.tool_execution.status === 'error' }">
											<!-- 1. Thinking box (reasoning only) -->
											<div v-if="block.plan_decision?.reasoning || block.reasoning || block.status === 'stopped'" class="thinking-box">
												<div class="thinking-header" @click="toggleReasoning(block.id)">
													<Icon :name="isReasoningCollapsed(block.id) ? 'heroicons-chevron-right' : 'heroicons-chevron-down'" class="w-4 h-4 text-gray-400 rtl-flip" />
													<span v-if="hasCompletedContent(block) || block.tool_execution" class="ms-1">
														{{ getThoughtProcessLabel(block) }}
													</span>
													<span v-else class="ms-1">
														<div class="dots" />
													</span>
												</div>
												<Transition name="fade">
													<div 
														v-if="!isReasoningCollapsed(block.id)" 
														:ref="el => setReasoningRef(block.id, el)"
														class="thinking-content"
													>
														<template v-if="block.plan_decision?.reasoning || block.reasoning">
															<MarkdownRender
																:content="block.plan_decision?.reasoning || block.reasoning || ''"
																:final="isBlockFinalized(block)"
																:typewriter="!isBlockFinalized(block)"
																:render-code-blocks-as-pre="true"
																class="markdown-content"
															/>
														</template>
														<template v-else-if="block.status === 'stopped'">
															<div class="text-gray-400 italic">{{ $t('reportView.generationStoppedBefore') }}</div>
														</template>
													</div>
												</Transition>
											</div>

							<!-- 2. Block content - assistant message (hybrid streaming) -->
							<!-- Prioritize final_answer over assistant - final_answer is the actual response -->
							<!-- Show content section when: content exists OR final_answer exists OR assistant exists -->
							<div v-if="(block.content || block.plan_decision?.final_answer || block.plan_decision?.assistant) && block.status !== 'error' && block.tool_execution?.tool_name !== 'clarify'" class="block-content markdown-wrapper" dir="auto">
								<MarkdownRender
									:content="block.content || block.plan_decision?.final_answer || block.plan_decision?.assistant || ''"
									:final="isBlockFinalized(block)"
									:typewriter="!isBlockFinalized(block)"
									:render-code-blocks-as-pre="true"
									class="markdown-content"
								/>
					<span v-if="!isBlockFinalized(block)" class="stream-caret"></span>
											</div>

											<!-- 3. Tool execution (ALWAYS visible outside thinking) -->
											<div v-if="block.tool_execution" class="tool-execution-container" :data-step-id="block.tool_execution?.created_step?.id || block.tool_execution?.created_step_id || ''">
												<component
													v-if="shouldUseToolComponent(block.tool_execution)"
													:is="getToolComponent(block.tool_execution.tool_name)"
													:key="`${block.id}:${(block.tool_execution && block.tool_execution.id) ? block.tool_execution.id : 'noid'}`"
													:tool-execution="block.tool_execution"
													:already-answered="block.tool_execution.tool_name === 'clarify' && m.id !== messages[messages.length - 1]?.id"
													:data-sources="report?.data_sources"
													:system-completion-id="m.system_completion_id || m.id"
													@addWidget="handleAddWidgetFromPreview"
													@refreshDashboard="refreshDashboardFast"
													@toggleSplitScreen="toggleSplitScreen"
													@editQuery="handleEditQuery"
													@openArtifact="handleOpenArtifact"
													@openInstruction="openInstructionById"
													@openScheduledTask="openScheduledTaskById"
												/>
												<!-- Fallback to generic expandable tool display -->
												<div v-else>
													<div class="text-xs text-gray-500 mb-1">
														<span class="cursor-pointer hover:text-gray-700" @click="toggleToolDetails(block.tool_execution.id)" v-if="block.tool_execution.tool_name !== 'clarify' && block.tool_execution.tool_name !== 'suggest_instructions'">
															{{ toolDisplayLabel(block.tool_execution) }} ({{ block.tool_execution.status }})
														</span>
														<div v-if="isToolDetailsExpanded(block.tool_execution.id)" class="ms-2 mt-1 text-xs text-gray-400 bg-gray-50 p-2 rounded space-y-2">
															<div v-if="toolDetail(block.tool_execution).what" class="text-gray-500">{{ toolDetail(block.tool_execution).what }}</div>
															<div v-if="block.tool_execution.result_summary">{{ block.tool_execution.result_summary }}</div>
															<!-- Claude-Code style code view: SQL + skill/tool source -->
															<div v-for="(seg, si) in toolDetail(block.tool_execution).code" :key="si" class="rounded border border-gray-200 overflow-hidden bg-white">
																<div class="flex items-center justify-between px-2 py-1 bg-gray-100 text-gray-500 font-mono text-[11px]">
																	<span class="truncate">{{ seg.path }}</span>
																	<span class="cursor-pointer hover:text-gray-800 shrink-0 ms-2" @click.stop="copyText(seg.body)">copy</span>
																</div>
																<pre class="m-0 p-2 overflow-auto max-h-72 text-[11px] leading-snug text-gray-700 font-mono whitespace-pre"><code>{{ seg.body }}</code></pre>
															</div>
															<div v-if="block.tool_execution.duration_ms">{{ $t('reportView.duration', { ms: block.tool_execution.duration_ms }) }}</div>
															<div v-if="block.tool_execution.created_widget_id" class="text-green-600">{{ $t('reportView.widgetRef', { id: block.tool_execution.created_widget_id }) }}</div>
															<div v-if="block.tool_execution.created_step_id" class="text-purple-600">{{ $t('reportView.stepRef', { id: block.tool_execution.created_step_id }) }}</div>
														</div>
													</div>
												</div>
											</div>
											
											<!-- Tool widget preview -->
											<div class="mt-1" v-if="shouldShowToolWidgetPreview(block.tool_execution) && block.tool_execution">
												<ToolWidgetPreview :tool-execution="block.tool_execution" @addWidget="handleAddWidgetFromPreview" @toggleSplitScreen="toggleSplitScreen" @editQuery="handleEditQuery" />
											</div>

																	</div>

										<!-- Fallback: cache-served / blockless answers carry content on the
										     completion itself, not in completion_blocks. Render it so the
										     answer isn't blank. -->
										<div
											v-if="m.completion?.content && !(m.completion_blocks || []).some(b => b.content || b.plan_decision?.final_answer || b.plan_decision?.assistant || b.tool_execution)"
											class="block-content markdown-wrapper"
											dir="auto"
										>
											<MarkdownRender
												:content="m.completion.content"
												:final="true"
												:render-code-blocks-as-pre="true"
												class="markdown-content"
											/>
										</div>

										<!-- F10 DECISION card — sense_making lives as a TOP-LEVEL field on the
										     system completion (carried into the message build). Render it once per
										     finished answer turn, right under the answer. Was lost when the chat
										     thread was rewritten off CompletionMessageComponent. -->
										<DecisionCard
											v-if="m.role === 'system' && m.status !== 'in_progress' && m.sense_making"
											:sense="m.sense_making"
											:compact="false"
											class="mt-3"
										/>

										<!-- Knowledge group: harness-phase blocks rendered as a single collapsible card -->
										<KnowledgeGroup
											v-if="(m as any)._harness_running || (m.completion_blocks || []).some(b => (b as any).phase === 'knowledge_harness')"
											:blocks="((m.completion_blocks || []).filter(b => (b as any).phase === 'knowledge_harness') as any)"
											:harness-running="!!(m as any)._harness_running"
											:knowledge-harness-build="(m as any).knowledge_harness_build || null"
											@open-instruction="openInstructionById"
											@published="() => loadCompletions({ skipEstimate: true })"
										/>

										<!-- Thinking pill when system is working but no visible progress - moved to end -->
										<div v-if="shouldShowWorkingDots(m)" class="mt-2 flex items-center gap-2.5 text-[13px] text-[#7A7066]">
											<span class="cai-wave" aria-hidden="true"><svg viewBox="0 0 40 18" preserveAspectRatio="none"><path class="wv wv1" d="M0 9 Q5 3 10 9 T20 9 T30 9 T40 9" stroke="#D67037"/><path class="wv wv2" d="M0 9 Q5 15 10 9 T20 9 T30 9 T40 9" stroke="#C2541E" style="opacity:.55"/></svg></span>
											<span class="ui-serif font-medium text-[#2A2420] truncate cc-shimmer">{{ runningStageText(m) }}</span>
											<span class="cai-wave cai-flip" aria-hidden="true"><svg viewBox="0 0 40 18" preserveAspectRatio="none"><path class="wv wv1" d="M0 9 Q5 3 10 9 T20 9 T30 9 T40 9" stroke="#D67037"/><path class="wv wv2" d="M0 9 Q5 15 10 9 T20 9 T30 9 T40 9" stroke="#C2541E" style="opacity:.55"/></svg></span>
											<span class="ml-1 tabular-nums text-[11.5px] text-[#9A8678] flex-none">{{ liveElapsed(m) }}</span>
										</div>
									</div>

									<!-- Show status messages for stopped/error completions -->
									<div class="mt-2" v-if="isRealCompletion(m) && m.status === 'success' && !hasClarifyBlock(m)">
										<div class="flex items-center gap-1">
											<CompletionItemFeedback
												:completion="{ id: (m.system_completion_id || m.id) }"
												:feedbackScore="m.feedback_score || 0"
												:initialUserFeedback="m.user_feedback"
												@suggestionsLoading="() => handleSuggestionsLoading(m)"
												@suggestionsReceived="(suggestions) => handleSuggestionsReceived(m, suggestions)"
											/>

											<!-- Instructions loaded indicator with popover -->
											<UPopover v-if="visibleInstructions(m).length" :popper="{ placement: 'top-start' }" ref="instructionsPopoverRef">
												<UButton variant="ghost" color="gray" size="xs" class="!px-1.5">
													<Icon name="heroicons-cube" class="w-3.5 h-3.5" />
													<span class="text-xs text-gray-700 font-normal">{{ $t('reportView.instructionsCount', { count: visibleInstructions(m).length }) }}</span>
												</UButton>
												<template #panel="{ close }">
													<div class="p-3 w-[380px] max-h-[300px] overflow-y-auto">
														<div class="text-[11px] uppercase tracking-wide text-gray-400 mb-2">{{ $t('reportView.instructionsLoaded') }}</div>
														<div class="space-y-0.5">
															<div
																v-for="ins in visibleInstructions(m)"
																:key="ins.id"
																class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer text-xs text-gray-700"
																@click="close(); openInstructionById(ins.id)"
															>
																<DataSourceIcon v-if="ins.data_source_type" :type="ins.data_source_type" class="h-3.5 w-3.5 flex-shrink-0" />
																<Icon v-else name="heroicons-cube" class="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
																<span class="flex-1 truncate">{{ ins.title || $t('reportView.untitled') }}</span>
																<span class="text-[10px] text-gray-400 flex-shrink-0">{{ ins.category || 'general' }}</span>
																<span class="text-[9px] px-1.5 py-0.5 rounded flex-shrink-0"
																	:class="(ins.load_mode || 'always') === 'always' ? 'bg-green-50 text-green-600' : 'bg-[#F6EFEA] text-[#A8330F]'">
																	{{ ins.load_mode || 'always' }}
																</span>
															</div>
														</div>
													</div>
												</template>
											</UPopover>

											<!-- Debug button -->
											<button
												v-if="canViewConsole"
												@click="openTraceModal(m.system_completion_id || m.id)"
												class="flex items-center justify-center w-6 h-6 hover:bg-gray-50 rounded-md transition-colors group"
												:title="$t('reportView.viewAgentTrace')"
											>
												<Icon name="heroicons-bug-ant" class="w-4 h-4 text-gray-500 group-hover:text-gray-900" />
											</button>

											<!-- AI message timestamp -->
											<span v-if="m.created_at" class="text-[10px] text-gray-400 ms-1">{{ formatMessageDate(m.created_at) }}</span>
										</div>
									</div>

									<!-- Instruction Suggestions (below thumbs) - show when loading or has suggestions -->
									<div v-if="report?.mode !== 'training' && !((m.completion_blocks || []).some(b => (b as any).phase === 'knowledge_harness')) && ((m.instruction_suggestions && m.instruction_suggestions.length > 0) || m.instruction_suggestions_loading)" class="mt-3">
										<InstructionSuggestions
											:tool-execution="{
												id: `suggestions-${m.id}`,
												tool_name: 'suggest_instructions',
												status: m.instruction_suggestions_loading ? 'running' : 'success',
												result_json: { drafts: m.instruction_suggestions || [] }
											}"
										/>
									</div>
									<div v-if="m.status === 'stopped'" class="text-xs text-gray-500 mt-2 italic">
										<Icon name="heroicons-stop-circle" class="w-4 h-4 inline me-1" />
										Generation stopped
									</div>
									<div v-else-if="m.status === 'error'" class="text-xs text-red-500 mt-2">
										{{ getMessageError(m) || 'An error occurred' }}
									</div>

									<!-- Suggested follow-up questions (under the last system message only) -->
									<div v-if="m.id === lastSystemMessage?.id && report?.mode !== 'training'" class="mt-3">
										<div v-if="(m as any).followups_loading && !awaitingClarify" class="flex items-center gap-2">
											<span class="px-3 py-1.5 text-xs rounded-full border border-gray-200 bg-gray-50 text-gray-400 animate-pulse">Thinking of follow-ups…</span>
										</div>
										<div v-else-if="(m as any).followups?.length">
											<div class="text-[11px] text-gray-400 mb-1.5">Ask a follow-up</div>
											<div class="flex flex-wrap gap-2 dock-followups">
												<button
													v-for="(q, qi) in (m as any).followups"
													:key="qi"
													:title="q"
													class="cursor-pointer px-3 py-1.5 text-xs rounded-full border border-gray-200 bg-gray-50 text-gray-700 hover:bg-[#FBEFE4] hover:border-[#C2541E] transition-colors"
													@click="handleExampleClick(q)"
												>
													{{ q }}
												</button>
											</div>
										</div>
									</div>
								</div>
							</template>
						</div>
					</li>
			</ul>
			<div v-else class="mt-32 fade-in">
				<!-- Training mode empty state -->
				<template v-if="currentPromptMode === 'training'">
					<h1 class="text-4xl mb-4">🎓</h1>
					<h1 class="text-lg font-semibold">{{ $t('reports.trainingEmptyTitle') }}</h1>
					<hr class="my-4">
					<p class="text-gray-500 text-sm"><span class="font-semibold">{{ $t('reports.trainingEmptyTipLabel') }}</span> <br />
						{{ $t('reports.trainingEmptyBody') }}
					</p>
					<div class="mt-4 flex flex-wrap gap-2">
						<button
							v-for="s in ($tm('reports.trainingStarters') as any[])"
							:key="s.title"
							class="px-3 py-1.5 text-xs rounded-full border border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100 transition-colors"
							@click="handleExampleClick(s.title === s.prompt ? s.prompt : `${s.title}\n\n${s.prompt}`)"
						>
							{{ s.title }}
						</button>
					</div>
				</template>
				<!-- Chat / deep mode empty state -->
				<template v-else>
					<div class="flex flex-col items-center text-center min-h-[58vh] justify-center">
						<div class="text-[11px] tracking-wide uppercase text-[#A8A294] mb-2">New report · no messages yet</div>
							<h1 class="text-lg font-semibold" style="font-family: 'Spectral', ui-serif, Georgia, serif">{{ $t('reports.emptyTitle') }}</h1>
						<div v-if="agentConversationStarters.length > 0" class="mt-5 flex flex-wrap justify-center gap-2">
							<button
								v-for="s in agentConversationStarters"
								:key="s.title"
								class="px-3 py-1.5 text-xs rounded-full border border-gray-200 bg-gray-50 text-gray-700 hover:bg-[#FBEFE4] hover:border-[#C2541E] transition-colors"
								@click="handleExampleClick(s.title === s.prompt ? s.prompt : `${s.title}\n\n${s.prompt}`)"
							>
								{{ s.title }}
							</button>
						</div>
					</div>
				</template>
			</div>
			</div>
		</div>

		<!-- Run paused waiting for the user's clarify answer: calm chip, NOT a spinner. -->
		<div v-if="awaitingClarify" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="inline-flex items-center gap-2 text-xs text-gray-500 bg-[#FBFAF6] border border-[#E9E0D3] rounded-full px-3 py-1.5">
				<Icon name="heroicons-clock" class="w-3.5 h-3.5 text-gray-400" />
				<span>Waiting for your answer — run paused</span>
			</div>
		</div>
		<!-- Minimal reconnect banner while polling after refresh (bottom, above prompt) -->
		<div v-else-if="isPolling" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="text-xs text-gray-500 flex items-center">
				<Spinner class="w-3 h-3 me-2 text-gray-400" />
				<span class="poll-shimmer">Loading… showing recent progress</span>
			</div>
		</div>
		<div v-if="report.report_type === 'test'" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="text-xs text-gray-500 flex items-center">
				<span class="text-xs">
					<span class="font-medium bg-yellow-100 text-yellow-800 px-2 py-1 rounded-md">Note
						This report is a report generated from a test run
					</span>
					</span>
				</div>
			</div>
		<div v-if="report.external_platform?.platform_type === 'mcp'" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="text-xs flex items-center">
				<span class="font-medium bg-[#F6EFEA] text-[#A8330F] px-3 py-2 rounded-md flex items-center gap-2">
					<img src="/icons/mcp.png" class="h-4 w-4" />
					<span>This session was created via MCP. The conversation reflects tool calls made by an external AI assistant. You can view the generated data and visualizations above.</span>
				</span>
			</div>
		</div>
		<div v-if="report.external_platform?.platform_type === 'slack'" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="text-xs flex items-center">
				<span class="font-medium bg-[#F6EFEA] text-[#A8330F] px-3 py-2 rounded-md flex items-center gap-2">
					<img src="/icons/slack.png" class="h-4 w-4" />
					<span>This session was created via Slack.</span>
				</span>
			</div>
		</div>
		<div v-if="report.external_platform?.platform_type === 'teams'" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="text-xs flex items-center">
				<span class="font-medium bg-[#F6EFEA] text-[#A8330F] px-3 py-2 rounded-md flex items-center gap-2">
					<img src="/icons/teams.png" class="h-4 w-4" />
					<span>This session was created via Microsoft Teams.</span>
				</span>
			</div>
		</div>
		<div v-if="report.external_platform?.platform_type === 'excel' && !isExcel" class="mx-auto px-4 mt-2 mb-2 max-w-2xl w-full">
			<div class="text-xs flex items-center">
				<span class="font-medium bg-green-50 text-green-700 px-3 py-2 rounded-md flex items-center gap-2">
					<img src="/data_sources_icons/excel.png" class="h-4 w-4" />
					<span>This session was created via Excel.</span>
				</span>
			</div>
		</div>
		<!-- Prompt box (in normal flow at the bottom of the left column) -->
		<div class="shrink-0 bg-[#FAF8F3] pt-2 pb-6">
			<!-- Persistent run-status strip: live wave + current step + elapsed,
			     docked just above the composer so progress stays in view even when
			     the message thread is scrolled up. Shows only while a run is live. -->
			<!-- Dock strip ONLY for the post-run auto-build phase (the live run already
			     shows its wave inline in the thread — no duplicate while running). -->
			<div v-if="autoBuilding || decisionForming" class="mx-auto w-full px-4 max-w-2xl mb-2">
				<div class="flex items-center gap-2.5 px-3.5 py-2 rounded-xl border border-[#EFE3D5] bg-gradient-to-b from-[#FCF4EC] to-[#FAF8F3] text-[13px] text-[#7A7066]">
					<span class="cai-wave" aria-hidden="true"><svg viewBox="0 0 40 18" preserveAspectRatio="none"><path class="wv wv1" d="M0 9 Q5 3 10 9 T20 9 T30 9 T40 9" stroke="#D67037"/><path class="wv wv2" d="M0 9 Q5 15 10 9 T20 9 T30 9 T40 9" stroke="#C2541E" style="opacity:.55"/></svg></span>
					<span class="ui-serif font-medium text-[#2A2420] truncate cc-shimmer">{{ (decisionForming && !autoBuilding) ? 'Reading the result… forming the decision' : 'Building a dashboard from your data…' }}</span>
					<span class="cai-wave cai-flip" aria-hidden="true"><svg viewBox="0 0 40 18" preserveAspectRatio="none"><path class="wv wv1" d="M0 9 Q5 3 10 9 T20 9 T30 9 T40 9" stroke="#D67037"/><path class="wv wv2" d="M0 9 Q5 15 10 9 T20 9 T30 9 T40 9" stroke="#C2541E" style="opacity:.55"/></svg></span>
					<span class="ml-auto flex-none text-[11px] text-[#9A8678]">auto · one-click</span>
				</div>
			</div>
			<div :class="['mx-auto w-full', isExcel ? 'px-0' : 'px-4 max-w-2xl']">
				<!-- Slide-workspace composer framing: PromptBoxV2 owns its own placeholder
				     (i18n, internal), so we surface the slide-scoped intent as a hint chip
				     above the same composer — the agent can already edit/analyze the deck. -->
				<div v-if="slidesFocus" class="flex items-center gap-1.5 mb-1.5 text-[12px] text-[#7A7066]">
					<Icon name="heroicons:presentation-chart-bar" class="w-3.5 h-3.5 text-[#C2541E] flex-none" />
					<span>Ask to edit a slide or analyze the deck&hellip;</span>
				</div>
				<PromptBoxV2
					ref="promptBoxRef"
					:report_id="report_id"
					:initialSelectedDataSources="report?.data_sources || []"
					:initialMode="report?.mode || 'chat'"
					:textareaContent="prefillText"
					:latestInProgressCompletion="runActive ? {} : undefined"
					:isStopping="false"
					:queryList="queryList"
					:scheduledPrompts="scheduledPrompts"
					:trainingInstructions="summaryInstructions"
						:pendingTrainingBuild="pendingTrainingBuild"
						:pendingTrainingBuildDiff="pendingTrainingBuildDiff"
						:isPublishingBuild="isPublishingBuild"
						@approveTrainingBuild="onApproveTrainingBuild"
						@discardTrainingBuild="onDiscardTrainingBuild"
						@discardTrainingInstruction="onDiscardTrainingInstruction"
					:hasArtifacts="hasArtifacts"
					:compact="isExcel"
					@submitCompletion="onSubmitCompletion"
					@stopGeneration="abortStream"
					@viewDashboard="() => { if (isMobile) { mobileView = 'dashboard'; } else { if (!isSplitScreen) toggleSplitScreen(); setPanelView('artifact', true); } }"
					@scrollToMessage="scrollToMessage"
					@editScheduledPrompt="editScheduledPrompt"
					@editTrainingInstruction="editTrainingInstruction"
					@openInstructions="() => { if (isMobile) { mobileView = 'agent'; } else { if (!isSplitScreen) toggleSplitScreen(); setPanelView('agent', true); } }"
					@update:selectedDataSources="(val: any[]) => currentAgents = val"
					@update:mode="(m: any) => currentPromptMode = m"
					@deleteScheduledPrompt="deleteScheduledPrompt"
					@toggleScheduledPrompt="toggleScheduledPromptActive"
					@scheduledPromptSaved="loadScheduledPrompts"
					:showContextIndicator="showContextIndicator"
				/>
			</div>
			<p v-if="!isExcel" class="text-center text-[11px] text-gray-400 mt-2">City Agent can make mistakes - double-check results.</p>
		</div>
		</template>
		<!-- Training instruction edit modal -->
		<InstructionModalComponent
			v-model="showTrainingInstructionModal"
			:instruction="editingTrainingInstruction"
			:initial-type="'global'"
			@instruction-saved="showTrainingInstructionModal = false"
		/>
		<!-- Edit scheduled prompt modal -->
		<ScheduledPromptModal
			v-model="showEditScheduledPromptModal"
			:reportId="report_id"
			:scheduledPrompt="editingScheduledPrompt"
			:initialDataSources="report?.data_sources || []"
			@saved="loadScheduledPrompts"
		/>
	</div>
		</template>
		<template #right-header>
			<!-- FIX 1 (Option A): compact icon+label tabs (shortened labels),
			     icon-only Auto toggle, ✕ pinned far right. Tab group can scroll
			     horizontally (hidden scrollbar) so it never wraps; Auto + ✕ stay
			     fixed. -->
			<!-- Real product-icon tabs (icon-only, hover/native title = label).
			     Gradient defs declared once below, referenced by url(#id). -->
			<svg width="0" height="0" class="absolute" aria-hidden="true"><defs>
				<radialGradient id="ppO" cx="35%" cy="30%" r="80%"><stop offset="0%" stop-color="#FFA25B"/><stop offset="55%" stop-color="#F36C3D"/><stop offset="100%" stop-color="#D24726"/></radialGradient>
				<linearGradient id="ppP" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#CA4C2C"/><stop offset="100%" stop-color="#B7472A"/></linearGradient>
				<linearGradient id="xlG" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#21A366"/><stop offset="100%" stop-color="#185C37"/></linearGradient>
				<linearGradient id="pbiY" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stop-color="#E6AE48"/><stop offset="100%" stop-color="#F2C811"/></linearGradient>
				<linearGradient id="tblB" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#3B82F6"/><stop offset="100%" stop-color="#1E40AF"/></linearGradient>
				<linearGradient id="agV" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#8B5CF6"/><stop offset="50%" stop-color="#6366F1"/><stop offset="100%" stop-color="#22D3EE"/></linearGradient>
				<linearGradient id="acR" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#F59E0B"/><stop offset="100%" stop-color="#EF4444"/></linearGradient>
			</defs></svg>
			<!-- Slide-workspace header: in slidesFocus mode the deck owns the panel,
			     so we hide the confusing tab strip and show a clean "Edit & analyze
			     slides" label instead. Close ✕ + expand control (further right) stay. -->
			<div v-if="slidesFocus" class="flex items-center gap-1.5 min-w-0 ps-1">
				<svg width="18" height="18" viewBox="0 0 48 48" class="flex-none"><circle cx="27" cy="21" r="15" fill="url(#ppO)"/><rect x="6" y="17" width="22" height="22" rx="5" fill="url(#ppP)"/><path d="M12 22h6.5a4 4 0 0 1 0 8H15v4h-3V22zm3 3v2.5h3.2a1.25 1.25 0 0 0 0-2.5H15z" fill="#fff"/></svg>
				<span class="text-sm font-semibold text-[#1f2328] truncate">Edit &amp; analyze slides</span>
			</div>
			<div v-else class="flex items-center gap-0.5 min-w-0">
				<button
					@click="setPanelView('studio', true)"
					class="tabico relative flex items-center justify-center w-9 h-8 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E] hover:bg-gray-100"
					:class="rightPanelView === 'studio' ? 'bg-[#F6EFEA]' : ''"
				>
					<svg width="19" height="19" viewBox="0 0 48 48" class="flex-none"><path d="M24 6l4 12 12 4-12 4-4 12-4-12-12-4 12-4z" fill="#C2541E"/></svg>
					<span class="ttip">Studio</span>
				</button>
				<button
					@click="setPanelView('summary', true)"
					class="tabico relative flex items-center justify-center w-9 h-8 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E] hover:bg-gray-100"
					:class="rightPanelView === 'summary' ? 'bg-gray-100' : ''"
				>
					<svg width="19" height="19" viewBox="0 0 48 48" class="flex-none"><rect x="6" y="8" width="36" height="32" rx="5" fill="url(#tblB)"/><rect x="6" y="8" width="36" height="9" rx="5" fill="#1E3A8A"/><g stroke="#fff" stroke-width="1.6" opacity=".9"><path d="M6 24h36M6 32h36M18 17v23M30 17v23"/></g></svg>
					<span class="ttip">{{ $t('reportView.tabSummary') }}</span>
				</button>
				<button
					@click="setPanelView('artifact', true)"
					class="tabico relative flex items-center justify-center w-9 h-8 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E] hover:bg-gray-100"
					:class="rightPanelView === 'artifact' || rightPanelView === 'grid' ? 'bg-gray-100' : ''"
				>
					<svg width="19" height="19" viewBox="0 0 48 48" class="flex-none"><rect x="9" y="20" width="7" height="20" rx="2.5" fill="url(#pbiY)"/><rect x="20" y="10" width="7" height="30" rx="2.5" fill="url(#pbiY)"/><rect x="31" y="26" width="7" height="14" rx="2.5" fill="url(#pbiY)"/></svg>
					<span class="ttip">Dashboard</span>
				</button>
				<button
					@click="setPanelView('agent', true)"
					class="tabico relative flex items-center justify-center w-9 h-8 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E] hover:bg-gray-100"
					:class="rightPanelView === 'agent' ? 'bg-gray-100' : ''"
				>
					<svg width="19" height="19" viewBox="0 0 48 48" class="flex-none"><path d="M24 7c4 0 6 3 7 7s4 6 8 7c-4 1-6 3-7 7s-3 7-8 8c1-4-1-7-4-9s-7-2-9 1c0-5 2-7 6-9s7-5 7-12z" fill="url(#agV)"/></svg>
					<span class="ttip">{{ currentAgents.length > 1 ? $t('reportView.tabAgents') : (currentAgents[0]?.name || $t('reportView.tabAgent')) }}</span>
				</button>
				<button
					@click="setPanelView('slides', true)"
					class="tabico relative flex items-center justify-center w-9 h-8 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E] hover:bg-gray-100"
					:class="rightPanelView === 'slides' ? 'bg-gray-100' : ''"
				>
					<svg width="19" height="19" viewBox="0 0 48 48" class="flex-none"><circle cx="27" cy="21" r="15" fill="url(#ppO)"/><rect x="6" y="17" width="22" height="22" rx="5" fill="url(#ppP)"/><path d="M12 22h6.5a4 4 0 0 1 0 8H15v4h-3V22zm3 3v2.5h3.2a1.25 1.25 0 0 0 0-2.5H15z" fill="#fff"/></svg>
					<span class="ttip">{{ $t('reportView.tabSlides') }}</span>
				</button>
				<button
					@click="setPanelView('excel', true)"
					class="tabico relative flex items-center justify-center w-9 h-8 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E] hover:bg-gray-100"
					:class="rightPanelView === 'excel' ? 'bg-gray-100' : ''"
				>
					<svg width="19" height="19" viewBox="0 0 48 48" class="flex-none"><path d="M27 6H13a3 3 0 0 0-3 3v30a3 3 0 0 0 3 3h22a3 3 0 0 0 3-3V17L27 6z" fill="#E6E6E6"/><path d="M27 6l11 11H30a3 3 0 0 1-3-3V6z" fill="#C8C8C8"/><rect x="6" y="15" width="20" height="18" rx="3" fill="url(#xlG)"/><path d="M11 19l4.5 5L11 29h3l3-3.4L20 29h3l-4.5-5L23 19h-3l-3 3.4L14 19h-3z" fill="#fff"/></svg>
					<span class="ttip">{{ $t('reportView.tabExcel') }}</span>
				</button>
			</div>
			<!-- Dashboard-first: quick switch back to chat-first from the panel header. -->
			<button
				v-if="dashboardFirst && !isMobile"
				@click="exitDashboardFirst"
				title="Switch to chat-first layout"
				class="ms-auto flex-none inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-[#E9E0D3] text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E]"
			>
				<Icon name="heroicons:chat-bubble-left-right" class="w-3.5 h-3.5" />
				Chat-first
			</button>
			<!-- Auto-pilot toggle: icon-only bolt (filled when on, slashed/outline
			     when off), pinned after the tab group. -->
			<button
				@click="toggleAutoPilot"
				:title="autoPilotPanel ? 'Auto-pilot on: panel follows the run. Click to turn off.' : 'Auto-pilot off: manual panel. Click to turn on.'"
				aria-label="Auto-pilot"
				class="ms-auto flex-none flex items-center justify-center w-7 h-7 rounded-lg transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E]"
				:class="autoPilotPanel ? 'text-[#8B4427] bg-[#F6EFEA]' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'"
			>
				<Icon :name="autoPilotPanel ? 'heroicons:bolt' : 'heroicons:bolt-slash'" class="w-3.5 h-3.5" />
			</button>
			<!-- ✕ close pinned to the far right, visually separated from the tabs. -->
			<button
				@click="userClosedPanel = true; toggleSplitScreen()"
				aria-label="Close panel"
				class="flex-none ms-1 p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-[#C2541E]"
			>
				<Icon name="heroicons:x-mark" class="w-4 h-4" />
			</button>
		</template>
		<template #right>
			<!-- Studio launcher (compact: output cards on top + slim live panel below) -->
			<div v-if="rightPanelView === 'studio'" class="h-full overflow-y-auto">

				<!-- ============================================================
				     COWORK PANEL (HYBRID_COWORK_PANEL ON) — Claude-Cowork look.
				     Create/Activity toggle · NOW · numbered PROGRESS plan with
				     live auto-scrolling sub-steps · Working-folders tree · Context.
				     ============================================================ -->
				<template v-if="coworkEnabled">
					<div class="p-3">
						<!-- Create / Activity segmented toggle -->
						<div class="flex gap-1 bg-[#F0EEEC] rounded-lg p-[3px] mb-3">
							<button
								@click="coworkTab = 'create'"
								:class="['flex-1 text-[12px] font-semibold py-1.5 rounded-md transition-colors cursor-pointer', coworkTab === 'create' ? 'bg-white text-[#1f2329] shadow-sm' : 'text-gray-500 hover:text-gray-700']"
							>+ Create</button>
							<button
								@click="coworkTab = 'activity'"
								:class="['flex-1 text-[12px] font-semibold py-1.5 rounded-md transition-colors cursor-pointer', coworkTab === 'activity' ? 'bg-white text-[#1f2329] shadow-sm' : 'text-gray-500 hover:text-gray-700']"
							>Activity</button>
						</div>

						<!-- ============ CREATE TAB ============ -->
						<div v-show="coworkTab === 'create'">
							<div class="flex items-center gap-2 mb-1.5">
								<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Make an output</span>
								<span class="h-px flex-1 bg-gray-100"></span>
								<span class="text-[9px] text-gray-400">tap &rarr; generate</span>
							</div>
							<div class="grid grid-cols-3 gap-1.5">
								<button @click="handleExampleClick('Build a dashboard for: ' + (lastUserQuestion || report?.title || 'this data'))" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#F4F7FF] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
									<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-blue-100 text-blue-700">AI</span>
									<svg width="15" height="15" fill="none" stroke="#3B6FE0" stroke-width="1.9" viewBox="0 0 24 24"><rect x="3" y="11" width="4" height="9"/><rect x="10" y="6" width="4" height="14"/><rect x="17" y="3" width="4" height="17"/></svg>
									<div class="mt-1.5 text-[10.5px] font-semibold text-[#2C53A8] leading-tight">Dashboard</div>
								</button>
								<button @click="handleExampleClick('Write a narrative report with key findings for: ' + (lastUserQuestion || report?.title || 'this data'))" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#F6F4FF] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
									<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-violet-100 text-violet-700">AI</span>
									<svg width="15" height="15" fill="none" stroke="#7A5CD0" stroke-width="1.8" viewBox="0 0 24 24"><path d="M6 3h9l5 5v13H6z"/><path d="M15 3v5h5"/></svg>
									<div class="mt-1.5 text-[10.5px] font-semibold text-[#5A41A8] leading-tight">Report</div>
								</button>
								<button @click="setPanelView('slides', true)" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#FFF4EF] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
									<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#FEE9DF] text-[#C2541E]">PPT</span>
									<svg width="15" height="15" fill="none" stroke="#D2603A" stroke-width="1.8" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="13" rx="1.5"/><path d="M8 21h8M12 17v4"/></svg>
									<div class="mt-1.5 text-[10.5px] font-semibold text-[#C2541E] leading-tight">Slides</div>
								</button>
								<button @click="setPanelView('excel', true)" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#EEFAF1] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
									<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#D8F3E1] text-[#157A43]">XLS</span>
									<svg width="15" height="15" fill="none" stroke="#1E9E57" stroke-width="1.8" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 8l8 8M16 8l-8 8"/></svg>
									<div class="mt-1.5 text-[10.5px] font-semibold text-[#157A43] leading-tight">Excel</div>
								</button>
								<div class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#FBEFF6] cursor-default opacity-65">
									<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#F6D9EC] text-[#C13D8C]">SOON</span>
									<svg width="15" height="15" fill="none" stroke="#C13D8C" stroke-width="1.8" viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="9" cy="8" r="2"/><path d="M13 7h4M7 14h10M7 17h7"/></svg>
									<div class="mt-1.5 text-[10.5px] font-semibold text-[#A52E72] leading-tight">Infographic</div>
								</div>
								<div class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#F1EEFB] cursor-default opacity-65">
									<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#E3DBF8] text-[#6B4FD0]">SOON</span>
									<svg width="15" height="15" fill="none" stroke="#6B4FD0" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 12h6M13 12l4-5M13 12l4 5"/></svg>
									<div class="mt-1.5 text-[10.5px] font-semibold text-[#5A41B0] leading-tight">Insight Map</div>
								</div>
							</div>
						</div>

						<!-- ============ ACTIVITY TAB ============ -->
						<div v-show="coworkTab === 'activity'" class="space-y-2.5">

							<!-- NOW -->
							<div class="rounded-xl border border-[#EAD8CD] bg-[#FFF6F1] px-3 py-2 flex items-center gap-2">
								<span class="w-1.5 h-1.5 rounded-full flex-none" :class="activityNow ? 'bg-[#C2541E] animate-pulse' : 'bg-gray-300'"></span>
								<span class="text-[10px] font-extrabold tracking-wide text-[#C2541E] flex-none">NOW</span>
								<span class="text-[12px] text-gray-700 truncate">{{ activityNow || 'Idle' }}</span>
							</div>

							<!-- PROGRESS = numbered plan + live sub-steps (auto-scroll) -->
							<div class="rounded-xl border border-gray-200 bg-white p-3">
								<div class="flex items-center justify-between mb-2">
									<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Progress</span>
									<span class="text-[11px] font-semibold text-gray-500">{{ coworkProgressLabel }}</span>
								</div>
								<div
									ref="coworkStepWrap"
									@scroll="onCoworkScroll"
									class="max-h-[230px] overflow-y-auto no-scrollbar pr-0.5 scroll-smooth"
								>
									<!-- PLAN MODE -->
									<ul v-if="activityPlan.length" class="list-none m-0 p-0">
										<li v-for="(task, idx) in activityPlan" :key="'plan-' + idx">
											<div class="flex items-start gap-2.5 py-1">
												<span
													class="w-5 h-5 rounded-full flex-none grid place-items-center text-[10.5px] font-bold border"
													:class="coworkTaskNumClass(task, idx)"
												>
													<span v-if="coworkTaskState(task, idx) === 'done'">&#10003;</span>
													<span v-else-if="coworkTaskState(task, idx) === 'run'" class="w-2 h-2 rounded-full border-2 border-[#C2541E] border-t-transparent animate-spin"></span>
													<span v-else>{{ idx + 1 }}</span>
												</span>
												<span
													class="text-[12.5px] flex-1 pt-0.5"
													:class="coworkTaskState(task, idx) === 'done' ? 'text-gray-400 line-through' : (coworkTaskState(task, idx) === 'run' ? 'font-semibold text-[#2b313a]' : 'text-[#2b313a]')"
												>{{ task.title }}</span>
											</div>
											<!-- live sub-steps stream UNDER the current task -->
											<ul
												v-if="idx === coworkActiveTaskIndex && activeSteps.length"
												class="list-none mt-0.5 mb-1 ml-[9px] pl-[21px] border-l border-dashed border-[#e6e3df]"
											>
												<li
													v-for="s in activeSteps"
													:key="'sub-' + s.id"
													class="flex items-center gap-2 py-[2.5px] text-[11.5px]"
													:class="s.status === 'run' ? 'text-[#2b313a] font-semibold' : 'text-gray-500'"
												>
													<span class="w-1.5 h-1.5 rounded-full flex-none" :class="coworkSubDotClass(s)"></span>
													<span class="truncate">{{ (s.recovered || s.status === 'warn') ? (s.recoveredLabel || s.title) : s.title }}</span>
													<span
														v-if="s.recovered || s.status === 'warn'"
														class="ms-auto text-[8.5px] font-bold px-1.5 rounded bg-[#fef3cd] text-[#b45309] flex-none"
													>{{ s.recoveredLabel || 'self-fixed' }}</span>
												</li>
											</ul>
										</li>
									</ul>
									<!-- FALLBACK (no plan): live steps, like the legacy panel -->
									<div v-else-if="activeSteps.length" class="space-y-1.5 text-[12px]">
										<div v-for="step in activeSteps" :key="step.id" class="flex items-center gap-2">
											<span class="w-2 h-2 rounded-full flex-none" :class="coworkSubDotClass(step)"></span>
											<span class="font-medium truncate" :class="step.status === 'done' ? 'text-gray-400' : 'text-[#2b313a]'">{{ (step.recovered || step.status === 'warn') ? (step.recoveredLabel || step.title) : step.title }}</span>
											<span v-if="step.recovered || step.status === 'warn'" class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 flex-none">retry</span>
											<span v-else-if="step.status === 'done'" class="ms-auto text-green-500 flex-none">&#10003;</span>
										</div>
									</div>
									<div v-else class="text-[12px] text-gray-400 py-1">No steps yet for this run.</div>
								</div>
								<div class="h-1.5 bg-[#f0eeec] rounded-full overflow-hidden mt-2.5">
									<div class="h-full bg-[#C2541E] transition-all" :style="{ width: coworkProgressPct + '%' }"></div>
								</div>
								<div class="text-[10.5px] text-gray-400 mt-1.5">{{ coworkProgressMeta }}</div>
							</div>

							<!-- WORKING FOLDERS = data sources (file + database) tree -->
							<details open class="rounded-xl border border-gray-200 bg-white">
								<summary class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none">
									<svg class="chev flex-none" width="11" height="11" fill="none" stroke="#9aa1ac" stroke-width="2.4" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>
									<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Working folders</span>
									<span class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ (report?.data_sources || []).length }}</span>
								</summary>
								<div class="px-3 pb-2 text-[12.5px] max-h-[200px] overflow-y-auto">
									<div v-for="ds in (report?.data_sources || [])" :key="ds?.id">
										<div class="flex items-center gap-2 py-1">
											<span class="flex-none w-4 grid place-items-center">{{ coworkDsIcon(ds) }}</span>
											<span class="truncate">{{ ds?.name || ds?.alias || 'source' }}</span>
											<span v-if="coworkDsType(ds)" class="ms-auto text-[9px] text-gray-400 border border-gray-200 rounded px-1.5 flex-none">{{ coworkDsType(ds) }}</span>
											<span
												class="text-[9px] font-bold px-1.5 py-0.5 rounded-full flex-none ms-1.5"
												:class="ds?.active === false ? 'bg-gray-100 text-gray-500' : 'bg-[#ecfdf3] text-[#15803d]'"
											>{{ ds?.active === false ? 'ref' : 'active' }}</span>
										</div>
										<div
											v-for="(tbl, ti) in coworkDsTables(ds)"
											:key="'tbl-' + ti"
											class="flex items-center gap-2 py-0.5 pl-7 text-gray-500"
										>
											<span class="flex-none">&#9638;</span>
											<span class="truncate">{{ tbl }}</span>
										</div>
									</div>
									<div v-if="!(report?.data_sources || []).length" class="text-gray-400 py-1">none</div>
								</div>
							</details>

							<!-- CONTEXT = Skills + Sub-agents chips -->
							<details open class="rounded-xl border border-gray-200 bg-white">
								<summary class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none">
									<svg class="chev flex-none" width="11" height="11" fill="none" stroke="#9aa1ac" stroke-width="2.4" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>
									<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Context</span>
								</summary>
								<div class="px-3 pb-2.5">
									<div class="text-[10px] font-bold uppercase tracking-wide text-gray-400 mt-1 mb-1.5">Skills</div>
									<div class="flex flex-wrap gap-1.5 mb-2">
										<span
											v-for="skill in activitySkills"
											:key="skill.id"
											class="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-full border border-gray-200 bg-white text-[#3b4250]"
										>
											<span class="w-1.5 h-1.5 rounded-full bg-[#C2541E]"></span>
											{{ skill.title }}
											<span
												class="text-[8.5px] font-extrabold px-1.5 rounded"
												:class="skill.badge === 'load_skill' ? 'bg-[#eef2fe] text-[#2C53A8]' : 'bg-[#FFF6F1] text-[#C2541E]'"
											>{{ skill.badge === 'load_skill' ? 'LOADED' : 'USED' }}</span>
										</span>
										<span v-if="!activitySkills.length" class="text-[11.5px] text-gray-400">none this run</span>
									</div>
									<div class="text-[10px] font-bold uppercase tracking-wide text-gray-400 mb-1.5">Sub-agents</div>
									<div class="flex flex-wrap gap-1.5">
										<span
											v-for="sa in activitySubagents"
											:key="sa.id"
											class="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-full border border-gray-200 bg-white text-[#3b4250]"
										>
											<span class="w-1.5 h-1.5 rounded-full bg-[#2C53A8]"></span>
											{{ sa.title }}
											<span
												class="text-[8.5px] font-extrabold px-1.5 rounded"
												:class="sa.status === 'done' ? 'bg-[#ecfdf3] text-[#15803d]' : 'bg-[#fff3cd] text-[#b45309]'"
											>{{ sa.status === 'done' ? 'DONE' : 'RUN' }}</span>
										</span>
										<span v-if="!activitySubagents.length" class="text-[11.5px] text-gray-400">none this run</span>
									</div>
								</div>
							</details>

						</div>
					</div>
				</template>

				<!-- ============ LEGACY PANEL (HYBRID_COWORK_PANEL OFF) ============ -->
				<template v-else>

				<!-- ============ TOP: COMPACT OUTPUT CARDS ============ -->
				<div class="p-3">
					<div class="flex items-center gap-2 mb-1.5">
						<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Outputs</span>
						<span class="h-px flex-1 bg-gray-100"></span>
						<span class="text-[9px] text-gray-400">tap &rarr; generate</span>
					</div>

					<!-- 3-col compact tiles: icon + absolute badge + label.
					     Forecast + Anomaly render as dimmed "SOON" cards in-grid. -->
					<div class="grid grid-cols-3 gap-1.5">
						<button @click="handleExampleClick('Build a dashboard for: ' + (lastUserQuestion || report?.title || 'this data'))" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#F4F7FF] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-blue-100 text-blue-700">AI</span>
							<svg width="15" height="15" fill="none" stroke="#3B6FE0" stroke-width="1.9" viewBox="0 0 24 24"><rect x="3" y="11" width="4" height="9"/><rect x="10" y="6" width="4" height="14"/><rect x="17" y="3" width="4" height="17"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#2C53A8] leading-tight">Dashboard</div>
						</button>
						<button @click="handleExampleClick('Write a narrative report with key findings for: ' + (lastUserQuestion || report?.title || 'this data'))" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#F6F4FF] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-violet-100 text-violet-700">AI</span>
							<svg width="15" height="15" fill="none" stroke="#7A5CD0" stroke-width="1.8" viewBox="0 0 24 24"><path d="M6 3h9l5 5v13H6z"/><path d="M15 3v5h5"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#5A41A8] leading-tight">Report</div>
						</button>
						<button @click="setPanelView('slides', true)" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#FFF4EF] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#FEE9DF] text-[#C2541E]">PPT</span>
							<svg width="15" height="15" fill="none" stroke="#D2603A" stroke-width="1.8" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="13" rx="1.5"/><path d="M8 21h8M12 17v4"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#C2541E] leading-tight">Slides</div>
						</button>
						<button @click="setPanelView('excel', true)" class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#EEFAF1] transition cursor-pointer hover:-translate-y-px hover:shadow-md hover:border-[#d9c4b6]">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#D8F3E1] text-[#157A43]">XLS</span>
							<svg width="15" height="15" fill="none" stroke="#1E9E57" stroke-width="1.8" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 8l8 8M16 8l-8 8"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#157A43] leading-tight">Excel</div>
						</button>
						<div class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#FBEFF6] cursor-default opacity-65">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#F6D9EC] text-[#C13D8C]">SOON</span>
							<svg width="15" height="15" fill="none" stroke="#C13D8C" stroke-width="1.8" viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="9" cy="8" r="2"/><path d="M13 7h4M7 14h10M7 17h7"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#A52E72] leading-tight">Infographic</div>
						</div>
						<div class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#F1EEFB] cursor-default opacity-65">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#E3DBF8] text-[#6B4FD0]">SOON</span>
							<svg width="15" height="15" fill="none" stroke="#6B4FD0" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 12h6M13 12l4-5M13 12l4 5"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#5A41B0] leading-tight">Insight Map</div>
						</div>
						<div class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#EAF7F4] cursor-default opacity-65">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#D5EBE5] text-[#147a68]">SOON</span>
							<svg width="15" height="15" fill="none" stroke="#147a68" stroke-width="1.9" viewBox="0 0 24 24"><path d="M3 17l5-5 4 3 7-8"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#147a68] leading-tight">Forecast</div>
						</div>
						<div class="relative text-left rounded-lg border border-gray-200 p-2 bg-[#FDEFEF] cursor-default opacity-65">
							<span class="absolute top-1.5 right-1.5 text-[8px] font-bold leading-none px-1 py-0.5 rounded bg-[#F8DADA] text-[#B83434]">SOON</span>
							<svg width="15" height="15" fill="none" stroke="#B83434" stroke-width="1.9" viewBox="0 0 24 24"><path d="M12 3l9 16H3z"/></svg>
							<div class="mt-1.5 text-[10.5px] font-semibold text-[#B83434] leading-tight">Anomaly</div>
						</div>
					</div>
				</div>

				<!-- ============ BOTTOM: MERGED ACTIVITY (NOW + Progress + collapsibles + Outputs) ============ -->
				<div class="px-3 pb-4 space-y-2.5">

					<!-- NOW banner (always visible) -->
					<div class="rounded-xl border border-[#EAD8CD] bg-[#FFF9F6] px-3 py-2 flex items-center gap-2">
						<span class="w-1.5 h-1.5 rounded-full flex-none" :class="activityNow ? 'bg-[#C2541E] animate-pulse' : 'bg-gray-300'"></span>
						<span class="text-[10px] font-bold tracking-wide text-[#C2541E] flex-none">NOW</span>
						<span class="text-[12px] text-gray-700 truncate">{{ activityNow || 'Idle' }}</span>
					</div>

					<!-- PROGRESS card (always visible) -->
					<div class="rounded-xl border border-gray-200 p-3">
						<div class="flex items-center justify-between mb-2">
							<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Progress</span>
							<span class="text-[11px] font-semibold text-gray-500">{{ activityDoneCount }} / {{ activityTotal }}</span>
						</div>
						<div v-if="activeSteps.length" class="space-y-1.5 text-[12px] max-h-[220px] overflow-y-auto no-scrollbar">
							<div v-for="step in activeSteps" :key="step.id" class="flex items-center gap-2">
								<span
									class="w-2 h-2 rounded-full flex-none"
									:class="step.status === 'done' ? 'bg-green-500'
										: (step.recovered || step.status === 'warn') ? 'bg-amber-400'
										: step.status === 'err' ? 'bg-red-500'
										: step.status === 'run' ? 'bg-[#C2541E] animate-pulse'
										: 'bg-gray-300'"
								></span>
								<span class="font-medium truncate">{{ (step.recovered || step.status === 'warn') ? (step.recoveredLabel || 'self-fixed') : step.title }}</span>
								<span
									v-if="step.recovered || step.status === 'warn'"
									class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 flex-none"
								>retry</span>
								<span v-else-if="step.status === 'done'" class="ms-auto text-green-500 flex-none">&#10003;</span>
								<span v-else-if="step.status === 'err'" class="ms-auto text-red-500 flex-none">&#9888;</span>
							</div>
						</div>
						<div v-else class="text-[12px] text-gray-400 py-1">No steps yet for this run.</div>
						<div class="h-1.5 bg-gray-100 rounded-full overflow-hidden mt-2.5">
							<div class="h-full bg-[#C2541E] transition-all" :style="{ width: activityProgressPct + '%' }"></div>
						</div>
						<div class="text-[10px] text-gray-400 mt-1.5">{{ activityDoneCount }} of {{ activityTotal }} steps · context budget &mdash; / &mdash; tokens</div>
					</div>

					<!-- DATA SOURCES (collapsible, open by default) -->
					<details open class="rounded-xl border border-gray-200">
						<summary class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none">
							<svg class="chev flex-none" width="11" height="11" fill="none" stroke="#9aa1ac" stroke-width="2.4" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>
							<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Data sources</span>
							<span class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ (report?.data_sources || []).length }}</span>
						</summary>
						<div class="px-3 pb-2 space-y-1 text-[12px] max-h-[150px] overflow-y-auto">
							<div
								v-for="ds in (report?.data_sources || [])"
								:key="ds?.id"
								class="flex items-center gap-2"
							>
								<svg width="13" height="13" fill="none" stroke="#9aa1ac" stroke-width="1.8" viewBox="0 0 24 24" class="flex-none"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.6 3.6 3 8 3s8-1.4 8-3V5"/></svg>
								<span class="truncate">{{ ds?.name || ds?.alias || 'source' }}</span>
								<span
									class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded flex-none"
									:class="ds?.active === false ? 'bg-gray-100 text-gray-500' : 'bg-green-100 text-green-700'"
								>{{ ds?.active === false ? 'ref' : 'active' }}</span>
							</div>
							<div v-if="!(report?.data_sources || []).length" class="text-[12px] text-gray-400 py-1">none</div>
						</div>
					</details>

					<!-- SKILLS USED (collapsible, closed) -->
					<details class="rounded-xl border border-gray-200">
						<summary class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none">
							<svg class="chev flex-none" width="11" height="11" fill="none" stroke="#9aa1ac" stroke-width="2.4" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>
							<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Skills used</span>
							<span class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ activitySkills.length }}</span>
						</summary>
						<div class="px-3 pb-2 space-y-1 text-[12px]">
							<div
								v-for="skill in activitySkills"
								:key="skill.id"
								class="flex items-center gap-2"
							>
								<svg width="13" height="13" fill="none" stroke="#C2541E" stroke-width="1.9" viewBox="0 0 24 24" class="flex-none"><path d="M12 3l2.2 5.6L20 9.8l-4.4 3.6L17 19l-5-3-5 3 1.4-5.6L4 9.8l5.8-1.2z"/></svg>
								<span class="font-medium truncate">{{ skill.title }}</span>
								<span class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#FBEFE4] text-[#C2541E] flex-none">{{ skill.badge === 'run_skill_file' ? 'ran' : 'used' }}</span>
							</div>
							<div v-if="!activitySkills.length" class="text-[12px] text-gray-400 py-1">none this run</div>
						</div>
					</details>

					<!-- SUB-AGENTS (collapsible, closed) -->
					<details class="rounded-xl border border-gray-200">
						<summary class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none">
							<svg class="chev flex-none" width="11" height="11" fill="none" stroke="#9aa1ac" stroke-width="2.4" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>
							<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Sub-agents</span>
							<span class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ activitySubagents.length }}</span>
						</summary>
						<div class="px-3 pb-2 space-y-1 text-[12px]">
							<div
								v-for="step in activitySubagents"
								:key="step.id"
								class="flex items-center gap-2"
							>
								<svg width="13" height="13" fill="none" stroke="#9aa1ac" stroke-width="1.8" viewBox="0 0 24 24" class="flex-none"><circle cx="9" cy="7" r="3"/><path d="M3 20c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="9" r="2.2"/><path d="M15 20c0-2.4 1.6-4 4-4"/></svg>
								<span class="font-medium truncate">{{ step.title }}</span>
								<span
									class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded flex-none"
									:class="step.status === 'done' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
								>{{ step.status === 'done' ? 'done' : 'running' }}</span>
							</div>
							<div v-if="!activitySubagents.length" class="text-[12px] text-gray-400 py-1">none</div>
						</div>
					</details>

					<!-- OUTPUTS THIS RUN -->
					<div class="rounded-xl border border-gray-200 p-3">
						<div class="flex items-center gap-2 mb-2">
							<span class="text-[10px] font-bold uppercase tracking-wide text-gray-400">Outputs this run</span>
							<span class="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#FBEFE4] text-[#C2541E]">{{ activityOutputs.length }}</span>
						</div>
						<button
							v-for="step in activityOutputs"
							:key="step.id"
							@click="setPanelView('artifact', true)"
							class="w-full flex items-center gap-2 rounded-lg border border-gray-100 hover:border-[#d9c4b6] hover:bg-[#FFF9F6] px-2.5 py-2 text-[12px] text-left transition-colors mb-1"
						>
							<svg width="15" height="15" fill="none" stroke="#3B6FE0" stroke-width="1.9" viewBox="0 0 24 24" class="flex-none"><rect x="3" y="11" width="4" height="9"/><rect x="10" y="6" width="4" height="14"/><rect x="17" y="3" width="4" height="17"/></svg>
							<span class="font-medium leading-tight truncate min-w-0">{{ step.title }}</span>
							<span class="ms-auto text-[10px] text-gray-300 flex-none">open &rsaquo;</span>
						</button>
						<div v-if="!activityOutputs.length" class="text-[12px] text-gray-400 py-1">none</div>
					</div>

				</div>
			</template>
			</div>
			<!-- Summary View -->
			<div v-else-if="rightPanelView === 'summary'" class="h-full flex flex-col">
				<div class="flex-1 overflow-y-auto">
					<ChatSummary
							:reportId="report_id"
						:latestAnswer="latestAnswer"
						:messages="messages"
						:scheduledPrompts="scheduledPrompts"
						:artifactList="reportArtifacts"
						:queryList="queryList"
						:queryExecutions="summaryQueries"
						:trainingInstructions="summaryInstructions"
						:reportInstructions="reportInstructions"
						:pendingBuildId="pendingTrainingBuild?.id || null"
						:pendingTrainingBuild="pendingTrainingBuild"
						:pendingTrainingBuildDiff="pendingTrainingBuildDiff"
						:sessionSummary="sessionSummary"
						:sessionSummaryStale="sessionSummaryStale"
						:sessionSummaryLoading="sessionSummaryLoading"
						:senseMaking="latestSenseMaking"
						:senseMakingPending="decisionForming"
						@refreshSessionSummary="onRefreshSessionSummary"
						@approveTrainingBuild="onApproveTrainingBuild"
						@discardTrainingBuild="onDiscardTrainingBuild"
						@discardTrainingInstruction="onDiscardTrainingInstruction"
						:showClose="true"
						@close="toggleSplitScreen"
						@editScheduledPrompt="editScheduledPrompt"
						@openArtifact="handleOpenArtifact"
						@scrollToMessage="scrollToMessage"
					/>
				</div>
			</div>

			<!-- Activity View (Claude-style live step tracking) -->
			<div v-else-if="rightPanelView === 'activity'" class="h-full overflow-y-auto p-4">
				<!-- FIX 3: Now / Next banner. "Now" = the model's narration for the
				     current/most-recent step (falls back to its label). "Next" is the
				     upcoming planned step's label when derivable — omitted otherwise
				     (never fabricated). -->
				<div
					v-if="activityNow"
					class="border border-[#E8C9B5] rounded-xl px-3.5 py-3 mb-4"
					style="background: linear-gradient(180deg,#fff,#FBF6F2);"
				>
					<div class="flex items-center gap-1.5 text-[10px] font-semibold tracking-wide uppercase text-[#8B4427]">
						<Icon name="heroicons:play" class="w-3 h-3 flex-none" />
						Now
					</div>
					<div class="mt-1 text-[13px] leading-snug text-[#33373c]">{{ activityNow }}</div>
					<template v-if="activityNext">
						<div class="mt-2 text-[10px] font-semibold tracking-wide uppercase text-[#9a958c]">Next</div>
						<div class="mt-0.5 text-[12px] leading-snug text-[#7A7066]">{{ activityNext }}</div>
					</template>
				</div>

				<!-- PROGRESS card -->
				<!-- FIX 2: reserve a fixed min-height (~4 steps) so streaming steps
				     fill reserved space instead of shoving the sections below
				     downward (the "panel jumps" bug). Sections below stay pinned. -->
				<div class="border border-[#ECE6DE] rounded-xl p-3.5 mb-4 min-h-[180px] max-h-[340px] flex flex-col">
					<div class="flex items-center justify-between mb-2.5">
						<span class="text-[11px] tracking-wide uppercase text-[#7A7066] font-medium">Progress</span>
						<span class="text-[11px] text-[#7A7066]">{{ activityDoneCount }} / {{ activityTotal }}</span>
					</div>
					<div v-if="activityTotal > 0" class="flex-1 min-h-0 overflow-y-auto no-scrollbar -mx-1 px-1">
						<div v-for="step in activeSteps" :key="step.id">
							<div class="flex items-center gap-2.5 py-1 text-[13px] text-[#2A2420]">
								<span
									class="w-2 h-2 rounded-full flex-none"
									:class="step.status === 'done' ? 'bg-[#3F7A4F]'
										: step.status === 'warn' ? 'bg-[#B5822F]'
										: step.status === 'err' ? 'bg-[#B3402F]'
										: step.status === 'run' ? 'bg-[#C2541E] animate-pulse'
										: 'bg-[#E8C9B5]'"
								></span>
								<span class="truncate">{{ step.title }}</span>
								<!-- recovered: amber "retried / self-fixed" pill -->
								<span
									v-if="step.recovered"
									class="text-[10px] font-semibold text-[#B07D2E] bg-[#F7EFE1] border border-[#E7D8B8] rounded-full px-1.5 py-0.5 flex-none"
								>{{ step.recoveredLabel || 'retried' }}</span>
								<span class="ms-auto text-[11px] text-[#7A7066]">
									<span v-if="step.status === 'done'" class="text-[#3F7A4F]">&#10003;</span>
									<span v-else-if="step.status === 'err'" class="text-[#B3402F]">&#9888;</span>
									<span v-else-if="step.status === 'warn'" class="text-[#B07D2E]">&#8635;</span>
								</span>
							</div>
							<!-- FIX 3: plain-language narration for this step (the model's own
							     reasoning, when present). Degrades to nothing when absent. -->
							<div v-if="step.why" class="ms-[18px] -mt-0.5 mb-1 text-[12px] leading-snug text-[#7A7066]">
								{{ step.why }}
							</div>
							<!-- recovered detail: amber summary + collapsible raw error -->
							<div v-if="step.recovered" class="ms-[18px] mb-1">
								<button
									class="text-[11px] text-[#7A7066] hover:text-[#2A2420] underline decoration-dotted"
									@click="toggleStepError(step.id)"
								>{{ isStepErrorOpen(step.id) ? 'hide detail' : 'show detail' }}</button>
								<pre
									v-if="isStepErrorOpen(step.id) && step.errorDetail"
									class="mt-1 whitespace-pre-wrap break-words text-[11px] font-mono text-[#B07D2E] bg-[#F7EFE1] border border-[#E7D8B8] rounded-md px-2 py-1.5 max-h-32 overflow-y-auto m-0"
								>{{ step.errorDetail }}</pre>
							</div>
							<!-- final failure: red, expanded -->
							<div
								v-else-if="step.status === 'err' && step.errorDetail"
								class="ms-[18px] mb-1"
							>
								<pre
									class="mt-0.5 whitespace-pre-wrap break-words text-[11px] font-mono text-[#B3402F] bg-[#F7E9E6] border border-[#E7C7C0] rounded-md px-2 py-1.5 max-h-32 overflow-y-auto m-0"
								>{{ step.errorDetail }}</pre>
							</div>
						</div>
					</div>
					<div v-else class="text-[13px] text-[#7A7066] py-1">No steps yet for this run.</div>
					<!-- progress bar (pinned to the bottom of the reserved card) -->
					<div class="h-[5px] bg-[#F4E5DA] rounded mt-auto overflow-hidden">
						<div class="h-full bg-[#C2541E] transition-all" :style="{ width: activityProgressPct + '%' }"></div>
					</div>
					<div class="text-[11px] text-[#7A7066] mt-1.5">
						{{ activityDoneCount }} of {{ activityTotal }} steps
						<span class="mx-1 text-[#ECE6DE]">|</span>
						<span class="text-[#7A7066]">context budget pending</span>
						<span class="text-[#7A7066]"> &mdash; / &mdash; tokens</span>
					</div>
				</div>

				<!-- DATA SOURCES -->
				<div class="text-[11px] tracking-wide uppercase text-[#7A7066] mt-4 mb-1.5">Data sources</div>
				<div
					v-for="ds in (report?.data_sources || [])"
					:key="ds?.id"
					class="flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[13px] text-[#2A2420] hover:bg-[#F6EFEA]"
				>
					<Icon name="heroicons:circle-stack" class="w-3.5 h-3.5 text-[#7A7066] flex-none" />
					<span class="truncate">{{ ds?.name || ds?.alias || 'source' }}</span>
					<span
						class="ms-auto text-[10px] px-1.5 py-0.5 rounded-full"
						:class="ds?.active === false ? 'bg-[#F6EFEA] text-[#7A7066]' : 'bg-[#E7F2EA] text-[#3F7A4F]'"
					>{{ ds?.active === false ? 'ref' : 'active' }}</span>
				</div>
				<div v-if="!(report?.data_sources || []).length" class="text-[13px] text-[#7A7066] px-2 py-1.5">none</div>

				<!-- SKILLS USED -->
				<div class="text-[11px] tracking-wide uppercase text-[#7A7066] mt-4 mb-1.5">Skills used</div>
				<div
					v-for="step in activitySkills"
					:key="step.id"
					class="flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[13px] text-[#2A2420] hover:bg-[#F6EFEA]"
				>
					<Icon name="heroicons:squares-2x2" class="w-3.5 h-3.5 text-[#7A7066] flex-none" />
					<span class="truncate">{{ step.title }}</span>
					<span class="ms-auto text-[10px] px-1.5 py-0.5 rounded-full bg-[#f3eefb] text-[#7c3aed]">used</span>
				</div>
				<div v-if="!activitySkills.length" class="text-[13px] text-[#7A7066] px-2 py-1.5">none this run</div>

				<!-- SUB-AGENTS -->
				<div class="text-[11px] tracking-wide uppercase text-[#7A7066] mt-4 mb-1.5">Sub-agents</div>
				<div
					v-for="step in activitySubagents"
					:key="step.id"
					class="flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[13px] text-[#2A2420] hover:bg-[#F6EFEA]"
				>
					<Icon name="heroicons:user-group" class="w-3.5 h-3.5 text-[#7A7066] flex-none" />
					<span class="truncate">{{ step.title }}</span>
					<span
						class="ms-auto text-[10px] px-1.5 py-0.5 rounded-full"
						:class="step.status === 'done' ? 'bg-[#E7F2EA] text-[#3F7A4F]' : 'bg-[#F6EFEA] text-[#7A7066]'"
					>{{ step.status === 'done' ? 'done' : 'running' }}</span>
				</div>
				<div v-if="!activitySubagents.length" class="text-[13px] text-[#7A7066] px-2 py-1.5">none</div>

				<!-- OUTPUTS -->
				<div class="text-[11px] tracking-wide uppercase text-[#7A7066] mt-4 mb-1.5">Outputs</div>
				<div
					v-for="step in activityOutputs"
					:key="step.id"
					class="flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[13px] text-[#2A2420] hover:bg-[#F6EFEA]"
				>
					<Icon name="heroicons:chart-bar-square" class="w-3.5 h-3.5 text-[#7A7066] flex-none" />
					<span class="truncate">{{ step.title }}</span>
				</div>
				<div v-if="!activityOutputs.length" class="text-[13px] text-[#7A7066] px-2 py-1.5">none</div>
			</div>

			<!-- Slides View -->
			<!-- Real presentation artifact (mode='slides') renders in the proven ArtifactFrame
			     (React artifact code + PPTX export). Falls back to the client-side SlidesPanel
			     deck only when no slides artifact exists ("build one from your charts"). -->
			<div v-else-if="rightPanelView === 'slides'" class="h-full flex flex-col min-h-0">
				<ArtifactFrame
					v-if="reportLoaded && report?.id && hasSlidesArtifact"
					:report-id="report.id"
					:report="report"
					mode-filter="slides"
					@close="toggleSplitScreen"
					class="h-full"
				/>
				<!-- Empty deck (no slides artifact AND nothing to build from, e.g. the
				     "Monthly EBITDA" report with 0 slides): a clear CTA instead of blank. -->
				<div
					v-else-if="!hasSlidesArtifact && !(visualizations || []).length"
					class="h-full flex flex-col items-center justify-center text-center gap-3 px-6"
				>
					<div class="w-12 h-12 rounded-xl bg-[#F6EFEA] flex items-center justify-center">
						<Icon name="heroicons:presentation-chart-bar" class="w-6 h-6 text-[#C2541E]" />
					</div>
					<div class="text-sm font-semibold text-[#1f2328]">No slides yet</div>
					<div class="text-[13px] text-[#7A7066] max-w-xs leading-relaxed">
						Generate a deck from this report — ask the chat to <span class="font-medium text-[#1f2328]">&ldquo;create a slide deck&rdquo;</span>.
					</div>
				</div>
				<!-- Flag ON: build a REAL slides artifact (python-pptx deck + chart
				     previews + .pptx) from the report's existing charts — no chat. On
				     success the artifacts refetch flips hasSlidesArtifact → the
				     ArtifactFrame branch above renders the real deck. -->
				<div
					v-else-if="oneClickEnabled"
					class="h-full flex flex-col items-center justify-center text-center gap-3 px-6"
				>
					<div class="w-12 h-12 rounded-xl bg-[#F6EFEA] flex items-center justify-center">
						<Icon name="heroicons:presentation-chart-bar" class="w-6 h-6 text-[#C2541E]" />
					</div>
					<div class="text-sm font-semibold text-[#1f2328]">Build a slide deck</div>
					<div class="text-[13px] text-[#7A7066] max-w-xs leading-relaxed">
						Turn this report's charts into a polished presentation with real charts, ready to export as PowerPoint.
					</div>
					<button
						class="mt-1 px-4 py-2 rounded-lg bg-[#C2541E] hover:bg-[#A8330F] text-white text-[13px] font-medium flex items-center gap-2 transition-colors disabled:opacity-60"
						:disabled="slideGenLoading"
						@click="generateSlideDeck"
					>
						<Icon
							:name="slideGenLoading ? 'heroicons:arrow-path' : 'heroicons:sparkles'"
							:class="['w-4 h-4', slideGenLoading ? 'animate-spin' : '']"
						/>
						{{ slideGenLoading ? 'Generating deck…' : 'Generate slide deck' }}
					</button>
					<p v-if="slideGenLoading" class="text-[11px] text-[#9a958c]">
						This takes ~15–30s — building slides and rendering chart previews.
					</p>
					<p v-if="slideGenError" class="text-[12px] text-[#C0362C] max-w-xs">{{ slideGenError }}</p>
				</div>
				<!-- Flag OFF: legacy lightweight client-side deck. -->
				<SlidesPanel v-else :visualizations="visualizations" :reportTitle="report?.title || 'Report'" />
			</div>

			<!-- Excel View (workbook — one sheet per query result) -->
			<div v-else-if="rightPanelView === 'excel'" class="h-full flex flex-col min-h-0">
				<ExcelPanel :sheets="excelSheets" :workbookTitle="report?.title || 'Workbook'" />
			</div>

			<!-- Agent View -->
			<div v-else-if="rightPanelView === 'agent'" class="h-full flex flex-col">
				<div class="flex-1 overflow-y-auto">
					<ReportAgentPanel ref="agentPanelRef" :agents="currentAgents" :showClose="true" @close="toggleSplitScreen" @starter-click="handleExampleClick" @connected="handleAgentConnected" />
				</div>
			</div>

			<!-- Grid View (DashboardComponent - Edit Mode) -->
			<DashboardComponent
				v-else-if="rightPanelView === 'grid' && reportLoaded && (visualizations || []).length >= 0"
				ref="dashboardRef"
				:report="report"
				:edit="true"
				:visualizations="visualizations"
				:textWidgetsIds="textWidgetsIds"
				:isStreaming="isStreaming"
				@toggleSplitScreen="toggleSplitScreen"
				@editVisualization="handleEditQuery"
				@toggleArtifactView="setPanelView('artifact', true)"
				class="h-full"
			/>

			<!-- Legacy Dashboard View (reports with dashboard_layout_versions but no artifacts) -->
			<DashboardComponent
				v-else-if="rightPanelView === 'artifact' && reportLoaded && hasLegacyLayout && !hasArtifacts"
				ref="dashboardRef"
				:report="report"
				:edit="true"
				:visualizations="visualizations"
				:textWidgetsIds="textWidgetsIds"
				:isStreaming="isStreaming"
				:hideArtifactSwitch="true"
				@toggleSplitScreen="toggleSplitScreen"
				@editVisualization="handleEditQuery"
				class="h-full"
			/>

			<!-- One-click Dashboard CTA (flag ON): no page artifact yet but the report
			     HAS charts → offer to build a real dashboard artifact, instead of the
			     ArtifactFrame "No artifacts yet" dead empty state. On success the
			     artifacts refetch flips hasPageArtifact → the ArtifactFrame below renders. -->
			<div
				v-else-if="rightPanelView === 'artifact' && reportLoaded && report?.id && !hasLegacyLayout && !hasPageArtifact && oneClickEnabled && (visualizations || []).length"
				class="h-full flex flex-col items-center justify-center text-center gap-3 px-6"
			>
				<div class="w-12 h-12 rounded-xl bg-[#F6EFEA] flex items-center justify-center">
					<Icon name="heroicons:squares-2x2" class="w-6 h-6 text-[#C2541E]" />
				</div>
				<div class="text-sm font-semibold text-[#1f2328]">Build a dashboard</div>
				<div class="text-[13px] text-[#7A7066] max-w-xs leading-relaxed">
					Turn this report's charts into an interactive dashboard with KPI cards and a responsive grid.
				</div>
				<button
					class="mt-1 px-4 py-2 rounded-lg bg-[#C2541E] hover:bg-[#A8330F] text-white text-[13px] font-medium flex items-center gap-2 transition-colors disabled:opacity-60"
					:disabled="dashGenLoading"
					@click="generateDashboard"
				>
					<Icon
						:name="dashGenLoading ? 'heroicons:arrow-path' : 'heroicons:sparkles'"
						:class="['w-4 h-4', dashGenLoading ? 'animate-spin' : '']"
					/>
					{{ dashGenLoading ? 'Generating dashboard…' : 'Generate dashboard' }}
				</button>
				<p v-if="dashGenLoading" class="text-[11px] text-[#9a958c]">
					This takes ~15–30s — building the dashboard from your charts.
				</p>
				<p v-if="dashGenError" class="text-[12px] text-[#C0362C] max-w-xs">{{ dashGenError }}</p>
			</div>

			<!-- Artifact View / Dash tab (handles all states: loading, empty, has artifacts).
			     mode-filter="page" → shows dashboards only; the slides deck lives in the Slides tab. -->
			<ArtifactFrame
				v-else-if="rightPanelView === 'artifact' && reportLoaded && report?.id && !hasLegacyLayout"
				:report-id="report.id"
				:report="report"
				mode-filter="page"
				@close="toggleSplitScreen"
				class="h-full"
			/>

			<!-- Empty state for grid view -->
			<div v-else-if="rightPanelView === 'grid' && reportLoaded && !(visualizations || []).length" class="p-4 text-center text-gray-500 h-full">
				No dashboard items yet.
			</div>
		</template>
	</SplitScreenLayout>

	<!-- Trace Modal -->
	<TraceModal
		v-model="showTraceModal"
		:report-id="report_id"
		:completion-id="selectedCompletionForTrace || ''"
		@openInstruction="openInstructionById"
	/>

	<!-- Query Code Editor Modal -->
	<QueryCodeEditorModal
		:visible="showQueryEditor"
		:query-id="queryEditorProps.queryId"
		:step-id="queryEditorProps.stepId"
		:initial-code="queryEditorProps.initialCode"
		:title="queryEditorProps.title"
		@close="closeQueryEditor"
		@stepCreated="onStepCreated"
	/>

	<!-- Image Preview Modal -->
	<ImagePreviewModal ref="imagePreviewModalRef" />

</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, onBeforeUnmount, watch, computed, type ComponentPublicInstance } from 'vue'
import PromptBoxV2 from '~/components/prompt/PromptBoxV2.vue'
import CreateWidgetTool from '~/components/tools/CreateWidgetTool.vue'
import CreateDataTool from '~/components/tools/CreateDataTool.vue'
import CreateDashboardTool from '~/components/tools/CreateDashboardTool.vue'
import CreateArtifactTool from '~/components/tools/CreateArtifactTool.vue'
import ReadArtifactTool from '~/components/tools/ReadArtifactTool.vue'
import ReadQueryTool from '~/components/tools/ReadQueryTool.vue'
import SearchReportsTool from '~/components/tools/SearchReportsTool.vue'
import ReadReportTool from '~/components/tools/ReadReportTool.vue'
import EditArtifactTool from '~/components/tools/EditArtifactTool.vue'
import DescribeTablesTool from '~/components/tools/DescribeTablesTool.vue'
import DescribeEntityTool from '~/components/tools/DescribeEntityTool.vue'
import ReadResourcesTool from '~/components/tools/ReadResourcesTool.vue'
import InspectDataTool from '~/components/tools/InspectDataTool.vue'
import MCPTool from '~/components/tools/MCPTool.vue'
import WriteCsvTool from '~/components/tools/WriteCsvTool.vue'
import WriteToExcelTool from '~/components/tools/WriteToExcelTool.vue'
import WriteOfficeJsCodeTool from '~/components/tools/WriteOfficeJsCodeTool.vue'
import ReadExcelRangeTool from '~/components/tools/ReadExcelRangeTool.vue'
import ReadExcelAsCsvTool from '~/components/tools/ReadExcelAsCsvTool.vue'
import SearchFilesTool from '~/components/tools/SearchFilesTool.vue'
import ListFilesTool from '~/components/tools/ListFilesTool.vue'
import ReadFileTool from '~/components/tools/ReadFileTool.vue'
import InstructionSuggestions from '@/components/InstructionSuggestions.vue'
import CreateInstructionTool from '~/components/tools/CreateInstructionTool.vue'
import EditInstructionTool from '~/components/tools/EditInstructionTool.vue'
import SendEmailTool from '~/components/tools/SendEmailTool.vue'
import CreateScheduledTaskTool from '~/components/tools/CreateScheduledTaskTool.vue'
import CancelScheduledTaskTool from '~/components/tools/CancelScheduledTaskTool.vue'
import ListAgentExecutionsTool from '~/components/tools/ListAgentExecutionsTool.vue'
import WebFetchTool from '~/components/tools/WebFetchTool.vue'
import WebSearchTool from '~/components/tools/WebSearchTool.vue'
import ClarifyTool from '~/components/tools/ClarifyTool.vue'
import SearchInstructionsTool from '~/components/tools/SearchInstructionsTool.vue'
import SearchEvalsTool from '~/components/tools/SearchEvalsTool.vue'
import CreateEvalTool from '~/components/tools/CreateEvalTool.vue'
import RunEvalTool from '~/components/tools/RunEvalTool.vue'
import InstructionModalComponent from '~/components/InstructionModalComponent.vue'
import DataSourceIcon from '~/components/DataSourceIcon.vue'
import ExecuteCodeTool from '~/components/tools/ExecuteCodeTool.vue'
import ToolWidgetPreview from '~/components/tools/ToolWidgetPreview.vue'
import SplitScreenLayout from '~/components/report/SplitScreenLayout.vue'
import ReportHeader from '~/components/report/ReportHeader.vue'
import ReportAgentPanel from '~/components/report/ReportAgentPanel.vue'
import ChatSummary from '~/components/report/ChatSummary.vue'
import DecisionCard from '~/components/DecisionCard.vue'
import SlidesPanel from '~/components/report/SlidesPanel.vue'
import ExcelPanel from '~/components/report/ExcelPanel.vue'
import ForkBanner from '~/components/ForkBanner.vue'
import ForkedQueriesPanel from '~/components/ForkedQueriesPanel.vue'
import DashboardComponent from '~/components/DashboardComponent.vue'
import ArtifactFrame from '~/components/dashboard/ArtifactFrame.vue'
import CompletionItemFeedback from '~/components/CompletionItemFeedback.vue'
import TraceModal from '~/components/console/TraceModal.vue'
import QueryCodeEditorModal from '~/components/tools/QueryCodeEditorModal.vue'
import ImagePreviewModal from '~/components/ImagePreviewModal.vue'
import Spinner from '~/components/Spinner.vue'
import InstructionText from '~/components/instructions/InstructionText.vue'
import { useCan } from '~/composables/usePermissions'
import { MarkdownRender } from 'markstream-vue'
import 'markstream-vue/index.css'

// Types
type ChatRole = 'user' | 'system'
type ChatStatus = 'in_progress' | 'success' | 'error' | 'stopped'

interface ToolCall {
	id: string
	tool_name: string
	tool_action?: string
	status: string
	result_summary?: string
	result_json?: any
	arguments_json?: any
	duration_ms?: number
	created_widget_id?: string
	created_step_id?: string
    created_widget?: any
    created_step?: any
    created_visualizations?: any[]
}

interface CompletionBlock {
	id: string
	seq?: number
	block_index: number
	phase?: string | null
	status: string
	content?: string
	reasoning?: string
	title?: string
	icon?: string
	started_at?: string
	completed_at?: string
	plan_decision?: {
		reasoning?: string
		assistant?: string
		final_answer?: string
		analysis_complete?: boolean
		plan_type?: string
	}
	tool_execution?: ToolCall
}

interface ChatMessage {
	id: string
	role: ChatRole
	status?: ChatStatus
	prompt?: { content: string; mentions?: Array<{ name: string; items: any[] }> }
	completion_blocks?: CompletionBlock[]
	tool_calls?: ToolCall[]
	created_at?: string
	// Backend system completion id used for sigkill
	system_completion_id?: string
	sigkill?: string | null
	feedback_score?: number
	// Transient streaming error message (set from SSE completion.error)
	error_message?: string
	// Optional structured error
	error?: any
	// Files attached to this completion (images, etc.)
	files?: { id: string; filename: string; content_type: string }[]
	// Instruction suggestions generated during this completion
	instruction_suggestions?: Array<{ text: string; category: string }>
	// Loading state for feedback-triggered suggestions
	instruction_suggestions_loading?: boolean
	// Scheduled prompt tag
	scheduled_prompt_id?: string | null
	// Suggested follow-up questions (fetched after the run finishes)
	followups?: string[]
	followups_loading?: boolean
}

const { t, locale: i18nLocale } = useI18n({ useScope: 'global' })
const RTL_LOCALES = new Set(['he', 'ar', 'fa', 'ur'])
const isRtl = computed(() => RTL_LOCALES.has(i18nLocale.value))
const route = useRoute()
const router = useRouter()
const report_id = (route.params.id as string) || ''

// Re-mount this page whenever the report id changes so client-side navigation
// between reports (e.g. clicking items in the ChatHistoryRail) reloads exactly
// like a full refresh — onMounted re-runs loadReport()/loadCompletions(). Without
// this key, Nuxt reuses the component across /reports/:id param changes and the
// content never reloads (blank chat on click, only fixed by a manual refresh).
// pageTransition:false — the global out-in page fade (nuxt.config) + this dynamic
// `key` remount race so the new page's enter never fires on report→report nav
// (old page leaves, new stays hidden → blank pane with NO console error; refresh
// works because a full load has no enter-transition). Opt this route out of the
// fade; the rest of the app keeps it. Keep the key so the page still remounts.
definePageMeta({
  key: (route) => route.params.id as string,
  pageTransition: false,
})

// Excel add-in mode detection (for compact UI)
const { isExcel, excelSelection } = useExcel()

// Permissions
const canViewConsole = computed(() => useCan('view_console'))

const messages = ref<ChatMessage[]>([])
const promptBoxRef = ref<InstanceType<typeof PromptBoxV2> | null>(null)

// List of queries for the summary pills — derived from created_steps in completions
const queryList = computed(() => {
	const list: { id: string; label: string; rowCount?: number; messageId: string; stepId: string }[] = []
	const seen = new Set<string>()
	for (const m of messages.value) {
		if (!m.completion_blocks) continue
		for (const b of m.completion_blocks) {
			const step = b.tool_execution?.created_step as any
			if (step && b.tool_execution?.status === 'success') {
				const stepId = step.id || step.query_id || ''
				if (stepId && seen.has(stepId)) continue
				if (stepId) seen.add(stepId)
				list.push({
					id: stepId,
					label: step.title || 'Query',
					rowCount: step.data?.info?.total_rows ?? undefined,
					messageId: m.id,
					stepId
				})
			}
		}
	}
	return list
})

const showContextIndicator = computed(() => {
	const completedSystem = messages.value.some(
		(m) => m.role === 'system' && ['success', 'error', 'stopped'].includes(m.status || '')
	)
	return completedSystem
})
// Pagination state
const pageLimit = 10
const hasMore = ref<boolean>(true)
const isLoadingMore = ref<boolean>(false)
const cursorBefore = ref<string | null>(null)
const promptText = ref<string>('')
const isStreaming = ref<boolean>(false)
// Tracks whether the main completion (analysis) is still running.
// Flips to false on completion.finished/error, even though isStreaming stays true
// for the knowledge harness tail. Used to unblock the prompt box early.
const isCompletionInProgress = ref<boolean>(false)
const copiedMessageId = ref<string | null>(null)
let currentController: AbortController | null = null

// Phase 3 — live elapsed timer for the in-progress "Working" header. A reactive
// clock that ticks once a second ONLY while streaming (interval cleared when the
// run ends), so the header can show "Working · 0:42" counting up. Cosmetic.
const nowTick = ref<number>(Date.now())
let nowTickHandle: ReturnType<typeof setInterval> | null = null
watch(isStreaming, (on) => {
	if (on) {
		nowTick.value = Date.now()
		if (nowTickHandle == null) nowTickHandle = setInterval(() => { nowTick.value = Date.now() }, 1000)
	} else if (nowTickHandle != null) {
		clearInterval(nowTickHandle); nowTickHandle = null
	}
})
function liveElapsed(m: any): string {
	const startMs = m?.created_at ? new Date(m.created_at).getTime() : nowTick.value
	let s = Math.max(0, Math.round((nowTick.value - startMs) / 1000))
	const mm = Math.floor(s / 60); s = s % 60
	return mm > 0 ? `${mm}:${String(s).padStart(2, '0')}` : `${s}s`
}
// Watchdog: if NO SSE event arrives for this long (or the stream closes without a
// terminal completion.finished/[DONE]/completion.error), force the run into an error
// state so the "Thinking…" spinner can never hang forever. Reset on every received
// event; cleared on any terminal path + on unmount.
const STREAM_WATCHDOG_MS = 150000
let streamWatchdog: ReturnType<typeof setTimeout> | null = null
function clearStreamWatchdog() {
	if (streamWatchdog) { clearTimeout(streamWatchdog); streamWatchdog = null }
}
// Mark a still-in_progress run as failed (stops the spinner via status flip) and
// surface a short inline error. Idempotent: no-op once the run has left in_progress.
function failRunUnexpectedly(sysId: string, message?: string) {
	const idx = messages.value.findIndex(m => m.id === sysId)
	if (idx === -1) return
	const m = messages.value[idx]
	if (m.status && m.status !== 'in_progress') return
	const errMsg = message || 'The run stopped unexpectedly. Please try again.'
	m.status = 'error' as any
	m.error_message = m.error_message || errMsg
	if (!m.completion_blocks?.some((b: any) => b.status === 'error')) {
		m.completion_blocks = m.completion_blocks || []
		m.completion_blocks.push({ id: `error-${Date.now()}`, block_index: 999, status: 'error', content: m.error_message })
	}
	isCompletionInProgress.value = false
}
function armStreamWatchdog(sysId: string) {
	clearStreamWatchdog()
	streamWatchdog = setTimeout(() => {
		failRunUnexpectedly(sysId)
		isStreaming.value = false
		try { currentController?.abort() } catch {}
		currentController = null
	}, STREAM_WATCHDOG_MS)
}
const scrollContainer = ref<HTMLElement | null>(null)
const scrollAnchor = ref<HTMLElement | null>(null)
// No absolute prompt box; no padding ref needed
// Scroll state tracking
const isUserAtBottom = ref<boolean>(true)
const suppressAutoScroll = ref<boolean>(false)
const lastScrollTop = ref<number>(0)
// Hysteresis thresholds
const NEAR_BOTTOM_PX = 96
const RETURN_TO_BOTTOM_PX = 12
// Debounced scroll scheduling during streaming
const pendingScroll = ref<boolean>(false)
let scrollRAF: number | null = null

// Trace modal state
const showTraceModal = ref(false)
const selectedCompletionForTrace = ref<string | null>(null)

// Report and Dashboard state
const reportLoaded = ref(false)
const reportNotFound = ref(false)
const completionsLoaded = ref(false)
const report = ref<any | null>(null)
const visualizations = ref<any[]>([])
const dashboardRef = ref<any | null>(null)

// Excel tab: derive workbook sheets from this report's query-result tables.
// Defensive — walks completion_blocks for any tool_execution.result_json that
// carries a tabular result (data_model.columns + rows, in either array-of-arrays
// or array-of-objects shape). Never throws; empty -> Excel shows its empty state.
// Server-sourced workbook (one sheet per query's latest success step). The
// /api/queries list strips step rows, so the Excel tab can't be built from
// loaded charts client-side — this endpoint returns the real grids. Auto-filled
// on report load (flag-gated). Falls back to message-scraped sheets below.
const serverSheets = ref<{ name: string; columns: string[]; rows: any[][] }[]>([])

async function loadWorkbook() {
	if (!oneClickEnabled.value) return
	try {
		const { data } = await useMyFetch<any>(`/reports/${report_id}/workbook`)
		const s = (data.value as any)?.sheets
		serverSheets.value = Array.isArray(s) ? s : []
	} catch {
		serverSheets.value = []  // fail-soft → message-scraped sheets
	}
}

// Sheets scraped from the loaded chat messages (the original source).
const messageSheets = computed(() => {
	const out: { name: string; columns: string[]; rows: any[][] }[] = []
	try {
		for (const m of (messages.value || [])) {
			for (const b of ((m as any)?.completion_blocks || [])) {
				const rj: any = b?.tool_execution?.result_json
				if (!rj) continue
				const dm: any = rj.data_model || rj
				let cols: string[] = []
				if (Array.isArray(dm.columns)) {
					cols = dm.columns.map((c: any) =>
						typeof c === 'string' ? c
						: (c?.generated_column_name || c?.name || c?.title || String(c)))
				}
				let rows: any[] = rj.rows || dm.rows || rj.data || dm.data
				if (!Array.isArray(rows) || rows.length === 0) continue
				// normalize array-of-objects -> array-of-arrays
				if (!Array.isArray(rows[0]) && typeof rows[0] === 'object') {
					if (!cols.length) cols = Object.keys(rows[0])
					rows = rows.map((r: any) => cols.map((c) => r?.[c]))
				}
				if (!cols.length && Array.isArray(rows[0])) {
					cols = rows[0].map((_: any, i: number) => `C${i + 1}`)
				}
				if (!cols.length) continue
				const name = String(
					b?.tool_execution?.result_summary || rj.title || `Sheet ${out.length + 1}`
				).slice(0, 28)
				out.push({ name, columns: cols, rows })
			}
		}
	} catch (e) { /* fail-soft -> empty workbook */ }
	return out
})

// The Excel tab prefers the server workbook (real grids for every chart);
// falls back to message-scraped sheets when the flag is off / fetch fails.
const excelSheets = computed(() =>
	serverSheets.value.length ? serverSheets.value : messageSheets.value
)
const textWidgetsIds = ref<string[]>([])

// Report summary (queries + instructions independent of message pagination)
const summaryQueries = ref<any[]>([])
const summaryInstructions = ref<any[]>([])
// Historical list of instructions created during this report's agent runs.
// Separate from summaryInstructions (which is pending-only) so the Summary
// tab can keep showing accepted instructions after the build is approved.
const reportInstructions = ref<any[]>([])
const pendingTrainingBuild = ref<{ id: string; status: string; total_instructions: number } | null>(null)
const pendingTrainingBuildDiff = ref<{ added_lines: number; removed_lines: number } | null>(null)
const isPublishingBuild = ref(false)

async function loadPendingBuildDiff() {
    const build = pendingTrainingBuild.value
    if (!build) { pendingTrainingBuildDiff.value = null; return }
    try {
        const mainRes = await useMyFetch<any>('/builds/main')
        const mainId = mainRes?.data?.value?.id
        if (!mainId || mainId === build.id) {
            pendingTrainingBuildDiff.value = { added_lines: 0, removed_lines: 0 }
            return
        }
        const { data } = await useMyFetch<any>(`/builds/${build.id}/diff/details?compare_to=${mainId}`)
        const items = (data?.value?.items || []) as any[]
        let added = 0, removed = 0
        for (const it of items) {
            const prev = (it.previous_text || '').split('\n')
            const next = (it.text || '').split('\n')
            const prevSet = new Set(prev)
            const nextSet = new Set(next)
            if (it.change_type === 'added') { for (const l of next) if (!prevSet.has(l)) added++ }
            else if (it.change_type === 'removed') { for (const l of prev) if (!nextSet.has(l)) removed++ }
            else {
                for (const l of next) if (!prevSet.has(l)) added++
                for (const l of prev) if (!nextSet.has(l)) removed++
            }
        }
        pendingTrainingBuildDiff.value = { added_lines: added, removed_lines: removed }
    } catch {
        pendingTrainingBuildDiff.value = null
    }
}

async function onApproveTrainingBuild(payload: { buildId: string; instructionIds: string[] } | string) {
    const buildId = typeof payload === 'string' ? payload : payload?.buildId
    const instructionIds = typeof payload === 'string' ? undefined : payload?.instructionIds
    if (!buildId || isPublishingBuild.value) return
    isPublishingBuild.value = true
    try {
        const body: any = {}
        if (instructionIds && instructionIds.length > 0) body.instruction_ids = instructionIds
        const { error } = await useMyFetch(`/builds/${buildId}/publish`, { method: 'POST', body })
        if (error.value) throw error.value
        pendingTrainingBuild.value = null
        pendingTrainingBuildDiff.value = null
        await loadReportSummary()
        agentPanelRef.value?.refreshInstructions?.()
        mobileAgentPanelRef.value?.refreshInstructions?.()
        // Notify any open tracked-changes views / tool cards for these instructions.
        if (typeof window !== 'undefined') {
            for (const id of (instructionIds || [])) {
                window.dispatchEvent(new CustomEvent('instruction:resolved', {
                    detail: { instructionId: id, buildId, action: 'accept' },
                }))
            }
        }
    } catch (e) {
        console.error('Failed to approve training build', e)
    } finally {
        isPublishingBuild.value = false
    }
}

async function onDiscardTrainingBuild(buildId: string) {
    if (!buildId) return
    if (!confirm('Discard all staged instruction changes from this session?')) return
    try {
        const { error } = await useMyFetch(`/builds/${buildId}/reject`, {
            method: 'POST',
            body: { reason: 'discarded from training session pill' },
        })
        if (error.value) throw error.value
        pendingTrainingBuild.value = null
        await loadReportSummary()
        // No specific instructionId — listeners that filter by id will ignore;
        // generic listeners (report page itself) just refresh.
        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('instruction:resolved', {
                detail: { instructionId: null, buildId, action: 'reject' },
            }))
        }
    } catch (e) {
        console.error('Failed to discard training build', e)
    }
}

async function onDiscardTrainingInstruction(payload: { buildId: string; instructionId: string }) {
    const { buildId, instructionId } = payload || ({} as any)
    if (!buildId || !instructionId) return
    try {
        const { error } = await useMyFetch(
            `/builds/${buildId}/contents/${instructionId}`,
            { method: 'DELETE' },
        )
        if (error.value) throw error.value
        await loadReportSummary()
        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('instruction:resolved', {
                detail: { instructionId, buildId, action: 'reject' },
            }))
        }
    } catch (e) {
        console.error('Failed to remove instruction from training build', e)
    }
}

// Listen for resolutions originating elsewhere (modal tracked-changes panel,
// tool cards) so the pill state stays in sync without prop drilling.
function onInstructionResolved(_e: Event) {
    // Re-fetch both: summary drives the pending pill; reportInstructions
    // drives the historical "Instructions" section in ChatSummary.
    loadReportSummary().catch(() => {})
    loadReportInstructions().catch(() => {})
}
onMounted(() => {
    if (typeof window !== 'undefined') {
        window.addEventListener('instruction:resolved', onInstructionResolved)
    }
})
onBeforeUnmount(() => {
    if (typeof window !== 'undefined') {
        window.removeEventListener('instruction:resolved', onInstructionResolved)
    }
})

// Scheduled prompts state
const scheduledPrompts = ref<any[]>([])
const editingScheduledPrompt = ref<any>(null)
const showEditScheduledPromptModal = ref(false)
const expandedScheduledIds = ref<Set<string>>(new Set())

function toggleScheduledExpand(messageId: string) {
	if (expandedScheduledIds.value.has(messageId)) {
		expandedScheduledIds.value.delete(messageId)
	} else {
		expandedScheduledIds.value.add(messageId)
	}
}

function isScheduledExpanded(messageId: string): boolean {
	return expandedScheduledIds.value.has(messageId)
}

const showTrainingInstructionModal = ref(false)
const editingTrainingInstruction = ref<any>(null)

// Agent panel refs
const agentPanelRef = ref<InstanceType<typeof ReportAgentPanel> | null>(null)
const mobileAgentPanelRef = ref<InstanceType<typeof ReportAgentPanel> | null>(null)

// Live list of agents (data sources) selected in the prompt box — used to drive ReportAgentPanel
const currentAgents = ref<any[]>([])

// --- Knowledge grounding scope (bounded-context visibility, arXiv:2605.22502) ---
// IMPORTANT: declared BEFORE the data_sources watcher below. That watcher is
// { immediate: true }, so its callback runs synchronously during setup and calls
// loadGroundingScope(), which reads/writes groundingScope (even on the early-return,
// no-data-sources path). If this ref were declared after the watcher, the immediate
// run would throw a TDZ ("Cannot access 'groundingScope' before initialization") and
// blank the entire report page. Do not move this below the watch.
const groundingScope = ref({ tables_total: 0, tables_injected: 0, metrics_total: 0, metrics_injected: 0 })

watch(() => report.value?.data_sources, (val) => {
    if (val && currentAgents.value.length === 0) currentAgents.value = [...val]
    loadGroundingScope()
}, { immediate: true })
async function loadGroundingScope() {
    const ids = (report.value?.data_sources || []).map((d: any) => d?.id).filter(Boolean)
    if (!ids.length) { groundingScope.value = { tables_total: 0, tables_injected: 0, metrics_total: 0, metrics_injected: 0 }; return }
    try {
        const { data } = await useMyFetch(`/knowledge/context-scope?data_source_ids=${encodeURIComponent(ids.join(','))}`, { method: 'GET' })
        if (data.value) groundingScope.value = data.value as any
    } catch { /* non-fatal */ }
}

// An agent was connected from ReportAgentPanel's credentials modal — refetch
// the report so updated per-user auth status flows back and the Connect prompt
// clears. (The OAuth redirect path reloads the page on return and refreshes on
// its own.)
async function handleAgentConnected() {
    await loadReport()
    if (report.value?.data_sources) currentAgents.value = [...report.value.data_sources]
}

// Flat, deduplicated conversation starters from all selected agents (max 3)
// Each stored starter is "Title\nDetailed prompt" — split into { title, prompt }
const agentConversationStarters = computed(() =>
    [...new Set<string>(currentAgents.value.flatMap((a: any) => a.conversation_starters || []))]
        .slice(0, 3)
        .map((s: string) => {
            const nl = s.indexOf('\n')
            return nl === -1
                ? { title: s, prompt: s }
                : { title: s.slice(0, nl).trim(), prompt: s.slice(nl + 1).trim() }
        })
)

async function openInstructionById(instructionId: string, opts?: { initialVersionNumber?: number | null }) {
	// Immediately switch to agent panel with loading state
	const panelRef = isMobile.value ? mobileAgentPanelRef : agentPanelRef
	if (isMobile.value) {
		mobileView.value = 'agent'
	} else {
		if (!isSplitScreen.value) isSplitScreen.value = true
		rightPanelView.value = 'agent'
	}
	await nextTick()
	panelRef.value?.setInstructionLoading(true)

	try {
		const { data, error } = await useMyFetch(`/instructions/${instructionId}`)
		if (!error.value && data.value) {
			panelRef.value?.openInstruction(data.value, { initialVersionNumber: opts?.initialVersionNumber ?? null })
			return
		}
	} catch {}
	panelRef.value?.setInstructionLoading(false)
	// Fallback: open in modal if fetch failed
	editingTrainingInstruction.value = { id: instructionId }
	showTrainingInstructionModal.value = true
}

async function editTrainingInstruction(inst: { instructionId: string }) {
	try {
		const { data, error } = await useMyFetch(`/instructions/${inst.instructionId}`)
		if (!error.value && data.value) {
			editingTrainingInstruction.value = data.value
		} else {
			editingTrainingInstruction.value = { id: inst.instructionId }
		}
	} catch {
		editingTrainingInstruction.value = { id: inst.instructionId }
	}
	showTrainingInstructionModal.value = true
}

function visibleInstructions(m: ChatMessage) {
	// Show every loaded instruction (including system-category ones) so the
	// count and popover match the agent trace modal, which lists all of them.
	return m._loaded_instructions || []
}

function isScheduledSystemExpanded(msg: ChatMessage): boolean {
	// Find the preceding user message with the same scheduled_prompt_id
	const idx = messages.value.indexOf(msg)
	if (idx > 0) {
		const prev = messages.value[idx - 1]
		if (prev.scheduled_prompt_id === msg.scheduled_prompt_id && prev.role === 'user') {
			return expandedScheduledIds.value.has(prev.id)
		}
	}
	return true
}

function formatScheduledDate(date?: string) {
	if (!date) return ''
	return new Date(date).toLocaleString()
}

function formatMessageDate(date?: string) {
	if (!date) return ''
	return new Date(date).toLocaleString(undefined, {
		month: 'short', day: 'numeric',
		hour: 'numeric', minute: '2-digit'
	})
}

// ---- Inbound webhook event-entry helpers ----
function webhookSourceIcon(source?: string): string {
	switch ((source || '').toLowerCase()) {
		case 'github': return 'heroicons-code-bracket-square'
		case 'jira': return 'heroicons-bug-ant'
		default: return 'heroicons-bolt'
	}
}
function webhookDecision(m: any): any {
	return m?.completion?.decision || null
}
function webhookActed(m: any): boolean {
	const d = webhookDecision(m)
	return !!(d && d.act)
}

function copyToClipboard(text?: string, messageId?: string) {
	if (!text) return
	navigator.clipboard.writeText(text)
	if (messageId) {
		copiedMessageId.value = messageId
		setTimeout(() => { copiedMessageId.value = null }, 1500)
	}
}

function getScheduledStats(userMsg: ChatMessage): string | null {
	// Find the paired system message
	const idx = messages.value.indexOf(userMsg)
	if (idx < 0 || idx >= messages.value.length - 1) return null
	const sysMsg = messages.value[idx + 1]
	if (!sysMsg || sysMsg.scheduled_prompt_id !== userMsg.scheduled_prompt_id || sysMsg.role !== 'system') return null
	const blocks = sysMsg.completion_blocks || []
	if (!blocks.length) return null

	let queries = 0
	let artifacts = 0
	for (const b of blocks) {
		const te = b.tool_execution
		if (!te || te.status !== 'success') continue
		if (te.tool_name === 'create_data' && te.created_step_id) queries++
		if (te.tool_name === 'create_artifact' || te.tool_name === 'edit_artifact') artifacts++
	}

	const parts: string[] = []
	parts.push(`${blocks.length} step${blocks.length !== 1 ? 's' : ''}`)
	if (queries) parts.push(`${queries} quer${queries !== 1 ? 'ies' : 'y'}`)
	if (artifacts) parts.push(`${artifacts} artifact${artifacts !== 1 ? 's' : ''}`)
	return parts.join(', ')
}

async function loadScheduledPrompts() {
    try {
        const { data } = await useMyFetch(`/reports/${report_id}/scheduled-prompts`)
        scheduledPrompts.value = (data.value as any[]) || []
    } catch {
        scheduledPrompts.value = []
    }
    // Start/stop the background poll based on whether this report has scheduled prompts
    if (scheduledPrompts.value.length > 0) {
        startScheduledCompletionsPoll()
    } else {
        stopScheduledCompletionsPoll()
    }
}

async function loadReportSummary() {
    try {
        const { data } = await useMyFetch(`/reports/${report_id}/summary`)
        const res = data.value as any
        summaryQueries.value = res?.queries || []
        summaryInstructions.value = (res?.instructions || []).map((i: any) => ({
            instructionId: i.instruction_id,
            title: i.title,
            category: i.category,
            isEdit: i.is_edit,
            lineCount: i.line_count,
            messageId: i.message_id,
            buildId: i.build_id,
        }))
        pendingTrainingBuild.value = res?.pending_training_build || null
        await loadPendingBuildDiff()
    } catch {
        summaryQueries.value = []
        summaryInstructions.value = []
        pendingTrainingBuild.value = null
        pendingTrainingBuildDiff.value = null
    }
}

async function loadReportInstructions() {
    try {
        const { data, error } = await useMyFetch(`/reports/${report_id}/instructions`)
        if (error.value) {
            console.warn('[reportInstructions] fetch error:', error.value)
        }
        const res = data.value as any
        reportInstructions.value = Array.isArray(res) ? res : []
        console.debug('[reportInstructions] loaded', reportInstructions.value.length, 'items')
    } catch (e) {
        console.warn('[reportInstructions] threw:', e)
        reportInstructions.value = []
    }
}

async function deleteScheduledPrompt(sp: any) {
    try {
        await useMyFetch(`/reports/${report_id}/scheduled-prompts/${sp.id}`, { method: 'DELETE' })
        await loadScheduledPrompts()
    } catch {}
}

async function toggleScheduledPromptActive(sp: any) {
    try {
        await useMyFetch(`/reports/${report_id}/scheduled-prompts/${sp.id}`, {
            method: 'PUT',
            body: { is_active: !sp.is_active },
        })
        await loadScheduledPrompts()
    } catch {}
}

function editScheduledPrompt(sp: any) {
    editingScheduledPrompt.value = sp
    showEditScheduledPromptModal.value = true
}

// Open the edit modal for a task created/cancelled from a chat tool result.
// The task may not be in the loaded list yet (just created), so refresh first.
async function openScheduledTaskById(taskId: string) {
    if (!taskId) return
    let sp = scheduledPrompts.value.find((s: any) => s.id === taskId)
    if (!sp) {
        await loadScheduledPrompts()
        sp = scheduledPrompts.value.find((s: any) => s.id === taskId)
    }
    if (sp) editScheduledPrompt(sp)
}

// Fork state — extract forked queries and artifact ref from the fork summary completion
const forkedQueries = ref<any[]>([])

async function enrichForkedQueries() {
    const forkSummary = messages.value.find((m: any) => m.is_fork_summary)
    if (!forkSummary?.fork_asset_refs) {
        forkedQueries.value = []
        return
    }
    const queryRefs = (forkSummary.fork_asset_refs as any[]).filter((r: any) => r.type === 'query')
    const enriched = await Promise.all(queryRefs.map(async (qRef: any) => {
        try {
            const { data } = await useMyFetch(`/api/queries/${qRef.id}/default_step`)
            const step = (data.value as any)?.step || null
            const toolExecution = step ? {
                id: `fork-${qRef.id}`,
                tool_name: 'query',
                status: 'success',
                created_step: step,
            } : null
            return {
                id: qRef.id,
                title: qRef.title || 'Untitled Query',
                description: qRef.description || '',
                toolExecution,
            }
        } catch {
            return {
                id: qRef.id,
                title: qRef.title || 'Untitled Query',
                description: qRef.description || '',
                toolExecution: null,
            }
        }
    }))
    forkedQueries.value = enriched
}

const forkedArtifactRef = computed(() => {
    const forkSummary = messages.value.find((m: any) => m.is_fork_summary)
    if (!forkSummary?.fork_asset_refs) return null
    const artifactRef = (forkSummary.fork_asset_refs as any[]).find((ref: any) => ref.type === 'artifact')
    return artifactRef || null
})

const nonSeedMessages = computed(() => {
    return messages.value.filter((m: any) => !m.is_fork_summary)
})

// Split screen state
const isSplitScreen = ref(false)
const leftPanelWidth = ref(450)
const isResizing = ref(false)

// ===== Dashboard-first layout (URL ?focus=dashboard) =====
// When on, the DASHBOARD fills the main area and the CHAT becomes a narrow dock
// on the right (collapsible). Triggered on mount; absent param = exactly today.
// Implementation is pure re-arrange/resize of the EXISTING panes (SplitScreenLayout
// flex-row-reverse + dock width) — no chat/composer/dashboard component is duplicated.
const dashboardFirst = ref(false)
// Slide-workspace mode (URL ?focus=slides). A specialisation of dashboardFirst:
// the deck owns the big main panel and the right dock is re-framed as a slide
// assistant (deck-only tabs hidden, "Edit & analyze slides" header, slide-scoped
// composer hint). Defaults false so the normal report view is byte-for-byte the
// same; only the focus=slides entry flips it on, exitDashboardFirst() resets it.
const slidesFocus = ref(false)
const dockCollapsed = ref(false)
const DOCK_WIDTH_OPEN = 360
const DOCK_WIDTH_COLLAPSED = 46
const DOCK_WIDTH_MIN = 300
const DOCK_WIDTH_MAX = 560
// User-resizable dock width (dashboard-first only). Persisted to localStorage.
const dockWidthPx = ref(DOCK_WIDTH_OPEN)
if (import.meta.client) {
	try {
		const saved = parseInt(localStorage.getItem('dash.dockWidth') || '', 10)
		if (!Number.isNaN(saved)) {
			dockWidthPx.value = Math.min(DOCK_WIDTH_MAX, Math.max(DOCK_WIDTH_MIN, saved))
		}
	} catch (e) { /* ignore */ }
}
function setDockWidth(w: number) {
	const clamped = Math.min(DOCK_WIDTH_MAX, Math.max(DOCK_WIDTH_MIN, Math.round(w)))
	dockWidthPx.value = clamped
	try { localStorage.setItem('dash.dockWidth', String(clamped)) } catch (e) { /* ignore */ }
}
const dockWidth = computed(() => dockCollapsed.value ? DOCK_WIDTH_COLLAPSED : dockWidthPx.value)
const initialMouseX = ref(0)
const initialPanelWidth = ref(0)

// Live prompt mode (mirrors PromptBoxV2 selection; initialised from report once loaded)
const currentPromptMode = ref<'chat' | 'deep' | 'training'>('chat')
// Draft text pushed into the prompt box without auto-submitting (e.g. training session).
const prefillText = ref('')
watch(() => report.value?.mode, (m) => { if (m) currentPromptMode.value = m as any }, { immediate: true })

// Right panel view mode — default Studio (the compact launcher home). Studio is
// the landing view on a fresh/empty chat and is NOT clobbered on load; the
// auto-pilot watchers still flip to Activity on run-start and Dashboard when a
// REAL artifact lands.
const rightPanelView = ref<'studio' | 'grid' | 'artifact' | 'agent' | 'summary' | 'activity' | 'slides' | 'excel'>('studio')

// ===== Auto-pilot panel state =====
// Open the panel + show Activity while a run is in progress, then auto-flip to
// Dashboard when a chart/artifact lands. Manual action pins the view for the run.
const autoPilotPanel = ref(true)
const userPinnedView = ref(false)   // user clicked a tab this run -> stop auto-switching
const userClosedPanel = ref(false)  // user closed the panel this run -> don't auto-reopen
if (import.meta.client) {
	try {
		const saved = localStorage.getItem('dash_autopanel')
		if (saved !== null) autoPilotPanel.value = saved === '1'
	} catch (e) { /* ignore */ }
}
function toggleAutoPilot() {
	autoPilotPanel.value = !autoPilotPanel.value
	try { localStorage.setItem('dash_autopanel', autoPilotPanel.value ? '1' : '0') } catch (e) { /* ignore */ }
}
// Per-tab panel width (left/chat px). Activity = narrow sidebar (wide chat);
// Dashboard = wide panel for charts. Mirrors the toggleSplitScreen widths.
function panelLeftWidthFor(view: string): number {
	const w = window.innerWidth
	if (view === 'studio') return Math.round(w * 0.55)     // launcher = wide right like Outputs
	if (view === 'activity') return Math.round(w * 0.55)   // match Outputs width
	if (view === 'summary') return Math.round(w * 0.55)
	if (view === 'agent') return Math.round(w * 0.48)
	return Math.round(w * 0.40)                            // artifact/grid = wide right
}
// Single entry point to switch the panel view (auto or manual). manual=true pins it.
function setPanelView(view: 'studio' | 'grid' | 'artifact' | 'agent' | 'summary' | 'activity' | 'slides' | 'excel', manual = false) {
	rightPanelView.value = view
	if (manual) userPinnedView.value = true
	if (!isMobile.value && isSplitScreen.value) {
		leftPanelWidth.value = panelLeftWidthFor(view)
	}
}

// Enable the dashboard-first layout: dashboard on main/left, chat dock on right.
// Reuses the EXISTING split + dashboard view (just flips arrangement via dashboardFirst).
function enterDashboardFirst() {
	if (isMobile.value) {
		mobileView.value = 'dashboard'
		return
	}
	dashboardFirst.value = true
	dockCollapsed.value = false
	userPinnedView.value = true                 // stop auto-pilot flipping away from the dashboard
	if (!isSplitScreen.value) toggleSplitScreen()
	rightPanelView.value = 'artifact'           // the dashboard (artifact/grid)
}

// Switch back to the normal chat-first layout + clean the ?focus query from the URL.
function exitDashboardFirst() {
	dashboardFirst.value = false
	slidesFocus.value = false
	dockCollapsed.value = false
	userPinnedView.value = false
	// Restore a normal panel width for the current view.
	if (!isMobile.value && isSplitScreen.value) {
		leftPanelWidth.value = panelLeftWidthFor(rightPanelView.value)
	}
	try {
		const q = { ...route.query }
		delete (q as any).focus
		router.replace({ query: q })
	} catch { /* non-fatal */ }
}

function toggleDockCollapsed() {
	dockCollapsed.value = !dockCollapsed.value
}

// ===== Studio launcher (compact) state =====
// Bottom live panel of the Studio pane: which slim feed is shown.
const studioFeed = ref<'activity' | 'agents' | 'skills'>('activity')
// Text of the most recent USER message — used to seed the generate prompts on
// the output cards. Falls back to the report title.
const lastUserQuestion = computed<string>(() => {
	try {
		for (let i = messages.value.length - 1; i >= 0; i--) {
			const m: any = messages.value[i]
			if (m?.role === 'user' && m?.prompt?.content && String(m.prompt.content).trim()) {
				return String(m.prompt.content).trim()
			}
		}
	} catch { /* ignore */ }
	return (report.value as any)?.title || ''
})

// Mobile view mode (full-screen single section on narrow screens)
const mobileView = ref<'chat' | 'summary' | 'dashboard' | 'agent'>('chat')
const isMobile = ref(false)

function checkMobile() {
	isMobile.value = window.innerWidth < 768
}

if (import.meta.client) {
	checkMobile()
	window.addEventListener('resize', checkMobile)
}

// Completion id currently wired up to forward Office.js results back to the backend.
const currentOfficeJsCompletionId = ref<string | null>(null)

// Legacy report detection: has artifacts vs legacy dashboard_layout_versions
const hasArtifacts = ref(false)
const reportArtifacts = ref<any[]>([])
const hasLegacyLayout = ref(false)

// Per-mode artifact presence, derived from the loaded artifacts list (no extra fetch).
// mode==='slides' = presentation deck; mode==='page' (or unset) = dashboard.
const hasSlidesArtifact = computed(() =>
	(reportArtifacts.value || []).some((a: any) => a?.mode === 'slides')
)
const hasPageArtifact = computed(() =>
	(reportArtifacts.value || []).some((a: any) => a?.mode !== 'slides')
)

// Toggle states
const collapsedReasoning = ref<Set<string>>(new Set())
const expandedToolDetails = ref<Set<string>>(new Set())
// Track blocks where user has manually toggled reasoning (so we don't auto-collapse them)
const manuallyToggledReasoning = ref<Set<string>>(new Set())



// Refs for reasoning content elements (used for dynamic ref binding)
const reasoningRefs = ref<Map<string, HTMLElement | null>>(new Map())

function setReasoningRef(blockId: string, el: HTMLElement | null) {
	if (el) {
		reasoningRefs.value.set(blockId, el)
	} else {
		reasoningRefs.value.delete(blockId)
	}
}

function scrollReasoningToBottom(blockId: string) {
	const el = reasoningRefs.value.get(blockId)
	if (el) {
		el.scrollTop = el.scrollHeight
	}
}


function isRealCompletion(m: ChatMessage): boolean {
    // During streaming we use a temporary client id like "system-<ts>".
    // Only allow feedback UI when we have a real backend id (UUID) either in
    // system_completion_id or in id.
    const cid = (m.system_completion_id || m.id) || ''
    // UUID v4 pattern (loose): 8-4-4-4-12 hex
    const uuidRe = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/
    return uuidRe.test(cid)
}

function getMessageError(m: any): string | null {
  if (typeof m?.error_message === 'string' && m.error_message.trim()) return m.error_message.trim()
  try {
    const content = m?.completion?.content
    if (typeof content === 'string' && content.trim()) return content.trim()
  } catch {}
  const blocks = m?.completion_blocks || []
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (b?.status === 'error' && typeof b?.content === 'string' && b.content.trim()) {
      return b.content.trim()
    }
  }
  return null
}


// Helper functions for block types
function isBlockFinalized(block: CompletionBlock): boolean {
	return !!(block.plan_decision?.analysis_complete || block.completed_at || block.status === 'stopped')
}

function hasCompletedContent(block: CompletionBlock): boolean {
	return !!(block.content || block.tool_execution || block.status === 'completed' || block.status === 'stopped' || block.plan_decision?.analysis_complete || block.plan_decision?.final_answer)
}

function hasClarifyBlock(m: ChatMessage): boolean {
	return (m.completion_blocks || []).some(b => b.tool_execution?.tool_name === 'clarify')
}

function getToolComponent(toolName: string) {
	switch (toolName) {
    // 'create_data_model' removed
		case 'create_widget':
			return CreateWidgetTool
    case 'create_data':
      return CreateDataTool
			case 'describe_tables':
				return DescribeTablesTool
		case 'describe_entity':
			return DescribeEntityTool
		case 'create_and_execute_code':
			return ExecuteCodeTool
		case 'create_dashboard':
			return CreateDashboardTool
		case 'create_artifact':
			return CreateArtifactTool
		case 'read_artifact':
			return ReadArtifactTool
		case 'read_query':
			return ReadQueryTool
		case 'search_reports':
			return SearchReportsTool
		case 'read_report':
			return ReadReportTool
		case 'edit_artifact':
			return EditArtifactTool
		case 'read_resources':
			return ReadResourcesTool
		case 'inspect_data':
			return InspectDataTool
		case 'search_mcps':
		case 'execute_mcp':
			return MCPTool
		case 'write_csv':
			return WriteCsvTool
		case 'write_to_excel':
			return WriteToExcelTool
		case 'write_officejs_code':
			return WriteOfficeJsCodeTool
		case 'read_excel_range':
			return ReadExcelRangeTool
		case 'read_excel_as_csv':
			return ReadExcelAsCsvTool
		case 'search_files':
			return SearchFilesTool
		case 'list_files':
			return ListFilesTool
		case 'read_file':
			return ReadFileTool
		case 'suggest_instructions':
			return InstructionSuggestions
		case 'create_instruction':
			return CreateInstructionTool
		case 'edit_instruction':
			return EditInstructionTool
		case 'send_email':
			return SendEmailTool
		case 'create_scheduled_task':
			return CreateScheduledTaskTool
		case 'cancel_scheduled_task':
			return CancelScheduledTaskTool
		case 'list_agent_executions':
			return ListAgentExecutionsTool
		case 'search_instructions':
			return SearchInstructionsTool
		case 'search_evals':
			return SearchEvalsTool
		case 'create_eval':
			return CreateEvalTool
		case 'run_eval':
			return RunEvalTool
		case 'execute_code':
		case 'execute_sql':
			return ExecuteCodeTool
		case 'web_fetch':
			return WebFetchTool
		case 'web_search':
			return WebSearchTool
		case 'clarify':
			return ClarifyTool
		default:
			return null
	}
}

function shouldUseToolComponent(toolExecution: ToolCall): boolean {
	return getToolComponent(toolExecution.tool_name) !== null
}

function shouldShowToolWidgetPreview(toolExecution: ToolCall | undefined): boolean {
	if (!toolExecution) return false
	
  // Only show for generic code-execution tools with success status.
  // Tools with a specialized component (e.g., create_widget, create_data) handle their own preview.
  const showForTools = ['create_and_execute_code', 'execute_code', 'execute_sql']
	return showForTools.includes(toolExecution.tool_name) && 
	       toolExecution.status === 'success' &&
	       (toolExecution.created_widget || toolExecution.created_step)
}

function shouldShowWorkingDots(message: ChatMessage): boolean {
	// Only show for system messages that are in progress
	if (message.role !== 'system' || message.status !== 'in_progress') {
		return false
	}
	
	// Don't show dots if the message was killed (sigkill timestamp exists)
	if (message.sigkill) {
		return false
	}
	
	// CASE 1: No blocks yet - show dots (initial startup phase)
	if (!message.completion_blocks || message.completion_blocks.length === 0) {
		return true
	}
	
	// CASE 2: Blocks exist but no meaningful content yet (early startup)
	const hasAnyMeaningfulContent = message.completion_blocks.some(block => 
		block.plan_decision?.reasoning || 
		block.reasoning || 
		block.content ||
		block.tool_execution
	)
	
	// If no meaningful content yet, show dots
	if (!hasAnyMeaningfulContent) {
		return true
	}
	
	// CASE 3: Check if we're in a "gap" between blocks during streaming
	const lastBlock = message.completion_blocks[message.completion_blocks.length - 1]
	
	// If the last block has final_answer and analysis_complete, we're truly done
	if (lastBlock?.plan_decision?.analysis_complete === true) {
		return false
	}
	
	// Check if the last block has finished its main content but no tools are running
	const lastBlockHasContent = lastBlock && (
		lastBlock.content ||
		lastBlock.plan_decision?.final_answer
	)
	
	// Check if tools are actively running
	const hasActiveTools = message.completion_blocks.some(block => 
		block.tool_execution?.status === 'running' || 
		block.status === 'in_progress'
	)
	
	// Check if any block is actively streaming text (has reasoning but no assistant yet)
	const hasStreamingContent = message.completion_blocks.some(block => 
		(block.plan_decision?.reasoning && !block.content) ||
		(block.reasoning && !block.content)
	)
	
	// Show dots when:
	// 1. System is in progress AND
	// 2. No active tools/streaming AND
	// 3. Last block has content but system continues (preparing next block)
	return !hasActiveTools && !hasStreamingContent && (!!lastBlockHasContent && message.status === 'in_progress')
}

function getThoughtProcessLabel(block: CompletionBlock): string {
	// Handle stopped blocks
	if (block.status === 'stopped') {
		return t('reportView.thoughtProcess')
	}

	// Prefer planner-provided reasoning duration when available
	const metricsAny: any = (block.plan_decision as any)?.metrics || (block.plan_decision as any)?.metrics_json
	const thinkingMs: number | undefined = metricsAny?.thinking_ms
	if (typeof thinkingMs === 'number' && isFinite(thinkingMs) && thinkingMs >= 0) {
		const secs = Math.max(0, Math.round(thinkingMs / 1000))
		return t('reportView.thoughtForSeconds', { seconds: secs })
	}

	// Calculate duration from started_at to completed_at if available
	if (block.started_at && block.completed_at) {
		const startTime = new Date(block.started_at).getTime()
		const endTime = new Date(block.completed_at).getTime()
		const durationMs = endTime - startTime
		const durationSeconds = Math.round(durationMs / 1000)

		// Sanity check for unreasonable durations (over 30 minutes)
		if (durationSeconds > 1800) {
			return t('reportView.stopped')
		}

		return t('reportView.thoughtForSeconds', { seconds: durationSeconds })
	}

	// Fallback to duration from tool execution if available
	if (block.tool_execution?.duration_ms) {
		const durationSeconds = (block.tool_execution.duration_ms / 1000).toFixed(1)
		return t('reportView.thoughtForSeconds', { seconds: durationSeconds })
	}

	// Default fallback
	return t('reportView.thoughtProcess')
}



// Auto-collapse reasoning when content becomes available (but respect user's manual toggle)
// Only watch the last system message to avoid iterating ALL messages on every token
const lastSystemMessage = computed(() =>
	[...messages.value].reverse().find(m => m.role === 'system')
)

// On initial load (or after a run), fetch suggested follow-ups for the last
// finished system message so reopening a report shows them. fetchFollowups is
// self-guarding (skips if loading/loaded/in-progress/not success).
watch(lastSystemMessage, (m: any) => {
	if (m && m.status === 'success' && m.followups === undefined && !m.followups_loading) {
		setTimeout(() => { fetchFollowups(m) }, 0)
	}
}, { immediate: false })

// Latest agent text answer — same text the chat renders as the answer, so the
// Outputs panel's Answer card is identical. Prefer the final answer block,
// fall back to cache-served completion.content. Empty when no text answer.
const latestAnswer = computed<string>(() => {
	try {
		const msg = lastSystemMessage.value as any
		if (!msg) return ''
		const blocks = (msg.completion_blocks || []).filter(
			(b: any) => b && b.phase !== 'knowledge_harness'
		)
		// Walk from the end to pick the final answer text the chat shows.
		for (let i = blocks.length - 1; i >= 0; i--) {
			const b = blocks[i]
			if (String(b?.status || '').toLowerCase() === 'error') continue
			if (b?.tool_execution?.tool_name === 'clarify') continue
			const text = b?.content || b?.plan_decision?.final_answer || b?.plan_decision?.assistant
			if (text && String(text).trim()) return String(text)
		}
		// Cache-served / blockless answers carry content on the completion itself.
		if (msg?.completion?.content && String(msg.completion.content).trim()) {
			return String(msg.completion.content)
		}
		return ''
	} catch {
		return ''
	}
})

// ===== Activity tab (Claude-style step tracking) =====
// Steps of the most-recent system completion = the current/most-recent run.
const activeSteps = computed<any[]>(() => {
	try {
		const msg = lastSystemMessage.value as any
		// Derive from the REAL agent activity: completion_blocks (tool runs,
		// reasoning, answer). Not the parallel `steps` array.
		const steps = blocksToSteps(msg?.completion_blocks || [])
		// Cache/instant serve: no blocks but an answer exists on the completion.
		if (steps.length === 0 && msg?.completion?.content && msg?.status === 'success') {
			const cached = msg?.served_by === 'answer_cache' || msg?.served_by === 'reasoning_cache'
			return [{
				id: 'instant', kind: 'think', icon: 'heroicons:bolt',
				title: cached ? 'Answered instantly (cached)' : 'Answered',
				badge: cached ? 'cache' : 'answer', status: 'done', ts: 0,
			}]
		}
		return steps
	} catch (e) {
		return []
	}
})

// Per-step "show detail" toggle for recovered (amber) error rows.
// Live "what's happening" label for the running wave indicator: the current
// running step's title, else the last step's title, else a friendly verb.
function runningStageText(m: any): string {
	try {
		const steps = blocksToSteps(m?.completion_blocks || [])
		if (steps.length) {
			const live = [...steps].reverse().find((s: any) => s.status === 'run') || steps[steps.length - 1]
			if (live?.title) return live.title
		}
	} catch (_) {}
	return 'Working on it…'
}

const expandedStepErrors = ref<Set<string>>(new Set())
function toggleStepError(id: string) {
	const s = new Set(expandedStepErrors.value)
	if (s.has(id)) s.delete(id); else s.add(id)
	expandedStepErrors.value = s
}
function isStepErrorOpen(id: string): boolean {
	return expandedStepErrors.value.has(id)
}

// Done = terminal-OK steps. Recovered (warn) attempts are NOT counted as
// failures; a final 'err' is the only red.
const activityDoneCount = computed(() =>
	(activeSteps.value || []).filter((s: any) => s?.status === 'done').length
)
const activityTotal = computed(() => (activeSteps.value || []).length)
const activityProgressPct = computed(() =>
	activityTotal.value > 0 ? Math.round((activityDoneCount.value / activityTotal.value) * 100) : 0
)

// Steps across EVERY system message in this report. A task that includes a
// clarify is split across multiple system messages (the skill calls land in the
// pre-clarify message, the answer in the post-clarify one). Reading only the
// last message hid skills/sub-agents that genuinely ran. Aggregate them all.
const allReportSteps = computed<any[]>(() => {
	try {
		const out: any[] = []
		for (const m of messages.value as any[]) {
			if (m?.role !== 'system') continue
			const steps = blocksToSteps(m?.completion_blocks || [])
			if (steps && steps.length) out.push(...steps)
		}
		return out
	} catch (e) {
		return []
	}
})
// Skills used in this report: steps whose badge is a skill load/run, deduped by
// skill (title) so a 37x retry loop collapses to one row per skill+action.
const activitySkills = computed(() => {
	const seen = new Set<string>()
	const rows: any[] = []
	for (const s of allReportSteps.value) {
		if (s?.badge !== 'load_skill' && s?.badge !== 'run_skill_file') continue
		const key = `${s.badge}:${s.title || ''}`
		if (seen.has(key)) continue
		seen.add(key)
		rows.push(s)
	}
	return rows
})
// Sub-agents spawned in this report (deduped by title).
const activitySubagents = computed(() => {
	const seen = new Set<string>()
	const rows: any[] = []
	for (const s of allReportSteps.value) {
		if (s?.kind !== 'subagent') continue
		const key = String(s.title || s.id || '')
		if (seen.has(key)) continue
		seen.add(key)
		rows.push(s)
	}
	return rows
})
// Outputs produced this run: tool steps that built a viz/dataset/artifact.
const activityOutputs = computed(() =>
	(activeSteps.value || []).filter((s: any) =>
		s?.kind === 'tool' &&
		(s?.badge === 'create_viz' || s?.badge === 'create_data' || s?.badge === 'create_artifact')
	)
)

// ===== FIX 3: Now / Next narration banner =====
// "Now" = the narration (or label) of the current/most-recent step: the last
// in-progress step if any, else the most recent step. Falls back to the step
// title when no reasoning was emitted — never fabricated.
const activityNow = computed<string>(() => {
	const steps = activeSteps.value || []
	if (!steps.length) return ''
	const running = [...steps].reverse().find((s: any) => s?.status === 'run')
	const cur = running || steps[steps.length - 1]
	if (!cur) return ''
	return cur.why || cur.title || ''
})
// "Next" = the planned/upcoming step. The stream only exposes steps that have
// already started, so we can honestly surface a "next" only when there's a
// pending step AFTER the current in-progress one (rare). Otherwise omit.
const activityNext = computed<string>(() => {
	const steps = activeSteps.value || []
	if (!steps.length) return ''
	const runIdx = steps.findIndex((s: any) => s?.status === 'run')
	if (runIdx === -1 || runIdx >= steps.length - 1) return ''
	const nxt = steps[runIdx + 1]
	if (!nxt) return ''
	return nxt.why || nxt.title || ''
})

// ===== Cowork panel (HYBRID_COWORK_PANEL) =====
// Claude-Cowork redesign of the right activity/outputs panel: a Create/Activity
// segmented toggle, NOW banner, numbered PROGRESS plan (the agent's up-front task
// list) with live sub-steps grouped under the current task + auto-scroll, a
// Working-folders tree of data sources, and a Context section (Skills/Sub-agents).
// FLAG-GATED (default OFF → the legacy panel renders unchanged). Mirrors the
// oneClickEnabled flag-read pattern exactly.
const coworkEnabled = ref(false)
const coworkTab = ref<'activity' | 'create'>('activity')

async function loadCoworkFlag() {
	try {
		const { data } = await useMyFetch<any[]>('/organization/hybrid-flags')
		const rows = (data.value as any[]) || []
		const row = rows.find(r => r?.env_name === 'HYBRID_COWORK_PANEL')
		coworkEnabled.value = !!row?.effective
	} catch {
		coworkEnabled.value = false  // fail-soft: keep the legacy panel
	}
}

// PLAN = the agent's up-front numbered task list (source_type:'plan' block).
// Empty for old/flag-off runs → Progress falls back to activeSteps (below).
const activityPlan = computed<any[]>(() => {
	try {
		const msg = lastSystemMessage.value as any
		return extractPlanTasks(msg?.completion_blocks || [])
	} catch {
		return []
	}
})
// Current plan task = first task not yet 'done' (where live sub-steps nest).
// -1 when the plan is empty OR every task is done (run finished).
const coworkActiveTaskIndex = computed<number>(() => {
	const tasks = activityPlan.value || []
	return tasks.findIndex((t: any) => String(t?.status || '').toLowerCase() !== 'done')
})
const coworkPlanDone = computed<number>(() =>
	(activityPlan.value || []).filter((t: any) => String(t?.status || '').toLowerCase() === 'done').length
)
// Progress meta — plan-aware when a plan exists, else mirrors the step counters.
const coworkProgressPct = computed<number>(() => {
	const total = (activityPlan.value || []).length
	if (total > 0) return Math.round((coworkPlanDone.value / total) * 100)
	return activityProgressPct.value
})
const coworkProgressLabel = computed<string>(() => {
	const total = (activityPlan.value || []).length
	if (total > 0) return `${coworkPlanDone.value} / ${total}`
	return `${activityDoneCount.value} / ${activityTotal.value}`
})
const coworkProgressMeta = computed<string>(() => {
	const total = (activityPlan.value || []).length
	if (total > 0) {
		const cur = coworkActiveTaskIndex.value === -1 ? total : coworkActiveTaskIndex.value + 1
		return `task ${cur} of ${total}`
	}
	return `${activityDoneCount.value} of ${activityTotal.value} steps`
})

// Per-task visual state: done | run (the active task) | pending.
function coworkTaskState(task: any, idx: number): 'done' | 'run' | 'pending' {
	if (String(task?.status || '').toLowerCase() === 'done') return 'done'
	if (idx === coworkActiveTaskIndex.value) return 'run'
	return 'pending'
}
function coworkTaskNumClass(task: any, idx: number): string {
	const st = coworkTaskState(task, idx)
	if (st === 'done') return 'bg-[#C2541E] border-[#C2541E] text-white'
	if (st === 'run') return 'border-[#C2541E] text-[#C2541E]'
	return 'border-gray-200 text-gray-400 bg-white'
}
// Live sub-step dot colour (mirrors the legacy Progress dot palette).
function coworkSubDotClass(s: any): string {
	if (s?.status === 'done') return 'bg-[#15803d]'
	if (s?.recovered || s?.status === 'warn') return 'bg-[#f0c674]'
	if (s?.status === 'err') return 'bg-red-500'
	if (s?.status === 'run') return 'bg-[#C2541E] animate-pulse'
	return 'bg-gray-300'
}

// ---- Working-folders tree helpers (degrade gracefully) ----
// report.data_sources[] reliably carries name/alias/active. type + tables are
// NOT guaranteed on that payload (see report below) — read defensively and fall
// back to a generic db icon / no table rows when absent. No new endpoints here.
function coworkDsType(ds: any): string {
	return String(ds?.type || ds?.connection_type || ds?.subtype || ds?.connection?.type || '').toLowerCase()
}
function coworkDsIcon(ds: any): string {
	const t = coworkDsType(ds)
	if (/spreadsheet|csv|excel|file|upload/.test(t)) return '📄'
	if (/snowflake/.test(t)) return '❄️'
	return '🗄️'
}
function coworkDsTables(ds: any): string[] {
	try {
		const raw = ds?.tables || ds?.active_tables || []
		if (!Array.isArray(raw)) return []
		return raw
			.map((t: any) => String(t?.name || t?.table || t || '').trim())
			.filter((n: string) => !!n)
			.slice(0, 8)
	} catch {
		return []
	}
}

// ---- AUTO-SCROLL: sticky-bottom for the streaming sub-steps ----
// Scroll the Progress container to the newest sub-step as steps stream, but
// ONLY when the user is already near the bottom (so reading older steps isn't
// yanked away). `atBottom` is recomputed on every manual scroll.
const coworkStepWrap = ref<HTMLElement | null>(null)
const coworkAtBottom = ref(true)
function onCoworkScroll() {
	const el = coworkStepWrap.value
	if (!el) return
	coworkAtBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 28
}
watch(
	() => [activeSteps.value.length, activityPlan.value.length, coworkActiveTaskIndex.value],
	() => {
		if (!coworkEnabled.value || !coworkAtBottom.value) return
		nextTick(() => {
			const el = coworkStepWrap.value
			if (el) el.scrollTop = el.scrollHeight
		})
	},
)

// ===== Auto-pilot watchers =====
const runStatus = computed(() => (lastSystemMessage.value as any)?.status)

// Single source of truth for "a run is still active". isStreaming alone is not
// enough: isCompletionInProgress is flipped false on completion.finished while the
// knowledge harness keeps streaming (isStreaming stays true), and the system
// message stays in_progress for the whole ~2min run. The composer must show Stop
// for the entire active window and only return to Send when the run is truly done.
const runActive = computed<boolean>(
	() => isStreaming.value || runStatus.value === 'in_progress'
)

// SESSION SUMMARY (Outputs card) — loaded from reports/{id}/session-summary and
// rebuilt on demand via the refresh button forwarded by ChatSummary.
const sessionSummary = ref<Record<string, any> | null>(null)
const sessionSummaryStale = ref(false)
const sessionSummaryLoading = ref(false)
async function loadSessionSummary() {
	try {
		const { data, error } = await useMyFetch(`reports/${report_id}/session-summary`, { method: 'GET' })
		if (error.value) return
		if (data.value) {
			sessionSummary.value = (data.value as any).summary ?? null
			sessionSummaryStale.value = !!(data.value as any).stale
		}
	} catch { /* fail-soft */ }
}
async function onRefreshSessionSummary() {
	sessionSummaryLoading.value = true
	try {
		const { data, error } = await useMyFetch(`reports/${report_id}/session-summary`, { method: 'POST' })
		if (error.value) return
		if (data.value) {
			sessionSummary.value = (data.value as any).summary ?? null
			sessionSummaryStale.value = !!(data.value as any).stale
		}
	} catch { /* fail-soft */ } finally {
		sessionSummaryLoading.value = false
	}
}

// DECISION FORMING — the backend emits SSE `sense_making.pending` right before it
// runs sense-making (post-answer), and clears at completion.finished/error. Drives
// the dock strip "forming the decision" state + the Outputs DECISION skeleton.
const decisionForming = ref(false)

// The most recent answer's sense_making object (walk messages from the end), so the
// Outputs panel can render the live DECISION card.
const latestSenseMaking = computed<Record<string, any> | null>(() => {
	const msgs = messages.value || []
	for (let i = msgs.length - 1; i >= 0; i--) {
		const m: any = msgs[i]
		if (m && m.role === 'system' && m.sense_making) return m.sense_making
	}
	return null
})

// AUTO-ARTIFACT (HYBRID_AUTO_ARTIFACT): when a chat turn produced a dataset but
// no artifact, the backend auto-builds a dashboard in the background (~2min).
// Poll the artifacts list so it appears without a manual refresh + surface a
// "building" state on the dock strip. Fail-soft — gives up after ~3min, and if
// the flag is off (no build comes) the poll simply times out quietly.
const autoBuilding = ref(false)
let _autoPollTimer: ReturnType<typeof setTimeout> | null = null
function stopAutoPoll() {
	if (_autoPollTimer) { clearTimeout(_autoPollTimer); _autoPollTimer = null }
	autoBuilding.value = false
}
async function pollAutoArtifact(triesLeft: number) {
	if (triesLeft <= 0) { stopAutoPoll(); return }
	try { await checkHasArtifacts() } catch (_) {}
	if (hasPageArtifact.value || hasSlidesArtifact.value) { stopAutoPoll(); return }
	_autoPollTimer = setTimeout(() => pollAutoArtifact(triesLeft - 1), 6000)
}
watch(runActive, (now, prev) => {
	if (prev && !now) {
		nextTick(() => {
			const producedData = (summaryQueries.value || []).length > 0
			if (producedData && !hasPageArtifact.value && !hasSlidesArtifact.value) {
				autoBuilding.value = true
				pollAutoArtifact(30)
			}
		})
	}
})
onBeforeUnmount(() => stopAutoPoll())

// RUN STARTS -> open panel + show Activity; reset per-run pins.
watch(runStatus, (now, prev) => {
	if (now === 'in_progress' && prev !== 'in_progress') {
		userPinnedView.value = false
		userClosedPanel.value = false
		if (!autoPilotPanel.value || isMobile.value) return
		nextTick(() => {
			if (!isSplitScreen.value && !userClosedPanel.value) {
				isSplitScreen.value = true
				collapseSidebar()
			}
			if (!userPinnedView.value) setPanelView('studio')
		})
	}
})

// REAL ARTIFACT lands -> flip the panel to the tab matching its mode (unless
// user pinned). A mode='slides' artifact opens the Slides tab; a mode='page'
// dashboard opens the Dash ('artifact') tab. Trigger ONLY on hasArtifacts (set
// by the create_artifact tool / Generate Dashboard), NOT on inline charts
// (create_data/create_viz) — an inline chart lives in the chat and does NOT
// populate either tab.
watch(hasArtifacts, async (has, prev) => {
	if (!has || has === prev || !autoPilotPanel.value || isMobile.value) return
	if (userPinnedView.value) return
	// Refresh the artifacts list so the per-mode computeds reflect the just-landed
	// artifact, then route on its mode. Fail-soft: default to the Dash tab.
	try { await checkHasArtifacts() } catch (e) { /* ignore */ }
	if (userPinnedView.value) return
	if (!isSplitScreen.value && !userClosedPanel.value) { isSplitScreen.value = true; collapseSidebar() }
	// Prefer Slides only when a slides deck exists and no page dashboard does,
	// so a report with both still defaults to the Dash tab.
	if (hasSlidesArtifact.value && !hasPageArtifact.value) {
		setPanelView('slides')
	} else {
		setPanelView('artifact')
	}
})

// RUN ENDS text-only -> Summary if it has content, else stay on Activity.
watch(runStatus, (now, prev) => {
	if (prev === 'in_progress' && now && now !== 'in_progress') {
		if (!autoPilotPanel.value || isMobile.value || userPinnedView.value) return
		// Outputs present (inline chart or real artifact) -> stay where we are
		// (Activity for charts, Dashboard if a real artifact flipped us there).
		// Only a pure-text answer falls through to Summary.
		if (activityOutputs.value.length > 0) return
		const hasSummary = (lastSystemMessage.value as any)?.completion_blocks?.some(
			(b: any) => b?.content || b?.plan_decision?.final_answer
		)
		if (hasSummary) setPanelView('summary')
	}
})

// ===== Global activity store mirror (floating robot) =====
// Reflect the live run into the shared useActivity() store WITHOUT disturbing the
// page's own streaming state. The store drives the always-on floating robot HUD.
// Read-only consumer of the existing run state (runActive/runStatus/activeSteps).
const _act = useActivity()
// De-dupe set: step ids already logged for the current run. Cleared on each new
// run start so a fresh run logs its steps again (ids are per-completion stable).
const _actLoggedSteps = new Set<string>()
let _actRunOpen = false

// RUN STARTS streaming -> open panel, start a session, go to "thinking".
watch(runActive, (now, prev) => {
	if (now && !prev) {
		_actLoggedSteps.clear()
		_actRunOpen = true
		_act.openPanel()
		_act.start('Agent working')
		_act.setState('thinking')
	} else if (!now && prev && _actRunOpen) {
		// RUN ENDS -> success/fail based on the terminal status of the last message.
		_actRunOpen = false
		const st = runStatus.value
		if (st === 'error' || st === 'stopped') {
			_act.fail(st === 'stopped' ? 'Run stopped' : 'Run failed')
		} else {
			_act.done('Done')
		}
	}
})

// STEPS ARRIVE -> log each NEW step once (de-duped by step id). Map a thinking
// step to setState('thinking'); a tool/build step to setState('processing').
watch(activeSteps, (steps) => {
	if (!_actRunOpen || !Array.isArray(steps)) return
	for (const s of steps) {
		const id = String(s?.id ?? '')
		if (!id || _actLoggedSteps.has(id)) continue
		_actLoggedSteps.add(id)
		// 'think' steps = planning/reasoning/answer; everything else = tool/build.
		const thinking = s?.kind === 'think'
		_act.setState(thinking ? 'thinking' : 'processing')
		const label = s?.title || (thinking ? 'Thinking…' : 'Working…')
		// Errored-but-recovered steps surface as warnings; final errors as errors.
		const level = s?.status === 'err' ? 'err' : (s?.status === 'warn' ? 'warn' : 'info')
		_act.log(label, level)
	}
}, { deep: false })

watch(
	// Watch only block IDs and their completion status, not deep content
	() => lastSystemMessage.value?.completion_blocks?.map(b => ({
		id: b.id,
		hasContent: hasCompletedContent(b),
		hasTool: !!b.tool_execution
	})),
	(blocks) => {
		if (!blocks) return
		for (const b of blocks) {
			// Auto-collapse when content exists OR when tool execution exists
			if ((b.hasContent || b.hasTool) && !collapsedReasoning.value.has(b.id) && !manuallyToggledReasoning.value.has(b.id)) {
				collapsedReasoning.value.add(b.id)
			}
		}
	},
	{ deep: true }
)

// Watch for split screen changes and scroll to bottom to maintain position
watch(() => isSplitScreen.value, () => {
    nextTick(() => setTimeout(safeScrollToBottom, 80))
})

// Adjust left panel width based on active right panel tab
watch(rightPanelView, (view) => {
    if (!isSplitScreen.value || isResizing.value) return
    const windowWidth = window.innerWidth
    if (view === 'summary' || view === 'activity' || view === 'studio') {
        leftPanelWidth.value = Math.round(windowWidth * 0.55)
    } else if (view === 'agent') {
        leftPanelWidth.value = Math.round(windowWidth * 0.45)
        collapseSidebar()
    } else {
        leftPanelWidth.value = Math.round(windowWidth * 0.37)
        collapseSidebar()
    }
})

function goBack() {
	if (history.length > 1) history.back()
}

function toggleReasoning(messageId: string) {
	// Mark as manually toggled so auto-collapse won't override user's choice
	manuallyToggledReasoning.value.add(messageId)
	if (collapsedReasoning.value.has(messageId)) {
		collapsedReasoning.value.delete(messageId)
	} else {
		collapsedReasoning.value.add(messageId)
	}
}

function isReasoningCollapsed(messageId: string) {
	return collapsedReasoning.value.has(messageId)
}

function toggleToolDetails(toolId: string) {
	if (expandedToolDetails.value.has(toolId)) {
		expandedToolDetails.value.delete(toolId)
	} else {
		expandedToolDetails.value.add(toolId)
	}
}

function isToolDetailsExpanded(toolId: string) {
	return expandedToolDetails.value.has(toolId)
}

// For skill tools, show the actual skill name + a friendly verb instead of the
// bare generic tool_name (load_skill / run_skill_file / read_skill_file).
function toolDisplayLabel(toolExecution: any): string {
	const name = toolExecution?.tool_name
	const verbs: Record<string, string> = {
		load_skill: 'loaded skill',
		run_skill_file: 'ran script',
		read_skill_file: 'read file',
	}
	if (verbs[name]) {
		const args = toolExecution?.arguments_json || {}
		// load_skill uses `name`; run/read_skill_file use `skill`.
		const skill = args.skill || args.name
		if (skill) return `${skill} · ${verbs[name]}`
	}
	const action = toolExecution?.tool_action ? ` → ${toolExecution.tool_action}` : ''
	return `${name}${action}`
}

// Claude-Code style detail for the expandable tool row: a short "what it did"
// line + one or more code segments (file-path header + body). Pulls SQL from
// the tool arguments and the executed source from the created step (which now
// carries the skill's SQL + script, or create_data's generated code).
function toolDetail(te: any): { what: string; code: Array<{ path: string; body: string }> } {
	const out: { what: string; code: Array<{ path: string; body: string }> } = { what: '', code: [] }
	try {
		const name = te?.tool_name || 'tool'
		const args = te?.arguments_json || {}
		const skill = args.skill || args.name
		// "What it did" line.
		if (name === 'run_skill_file') out.what = `Ran skill script${skill ? ` from “${skill}”` : ''}${args.path ? ` (${args.path})` : ''}.`
		else if (name === 'load_skill') out.what = `Loaded skill${skill ? ` “${skill}”` : ''} — injected its instructions.`
		else if (name === 'read_skill_file') out.what = `Read skill file${args.path ? ` ${args.path}` : ''}.`
		// SQL passed to the tool (skills, create_data).
		const sql = args.sql || args.query
		if (sql && typeof sql === 'string') out.code.push({ path: 'query.sql', body: sql.trim() })
		// Executed source from the created step (SQL + skill script / generated code).
		const stepCode = te?.created_step?.code
		if (stepCode && typeof stepCode === 'string' && stepCode.trim() && stepCode.trim() !== (sql || '').trim()) {
			out.code.push({ path: skill ? `${skill}/${args.path || 'script'}` : (args.path || 'code'), body: stepCode.trim() })
		}
		// Fallback: surface raw args when nothing else (so the row is never empty).
		if (!out.code.length && args && Object.keys(args).length) {
			out.code.push({ path: `${name} · arguments`, body: JSON.stringify(args, null, 2) })
		}
	} catch (e) { /* non-fatal */ }
	return out
}

function copyText(text: string) {
	try { navigator?.clipboard?.writeText(String(text || '')) } catch (e) { /* ignore */ }
}

// Get attached images from a message's files
function getAttachedImages(message: ChatMessage) {
	const files = message.files || []
	return files.filter((f: any) => (f.content_type || '').startsWith('image/'))
}

const GROUP_TYPE_MAP: Record<string, string> = {
	'DATA SOURCES': 'data_source',
	'TABLES': 'datasource_table',
	'FILES': 'file',
	'ENTITIES': 'entity',
	'CONNECTION TOOLS': 'connection_tool',
}

function promptMentionsToRefs(mentions?: Array<{ name: string; items: any[] }>) {
	if (!mentions?.length) return []
	const refs: Array<{ id: string; type: string; name: string; data_source_type?: string }> = []
	for (const group of mentions) {
		const type = GROUP_TYPE_MAP[(group.name || '').toUpperCase()] || 'entity'
		for (const item of group.items || []) {
			let name = item.name || item.title || item.filename || ''
			// Data-source tables are serialized into the prompt text with their
			// source prefix (e.g. "@Microsoft Fabric / dbo.sales"), so the ref
			// name must include it to match and render as a single mention chip.
			if (type === 'datasource_table') {
				const prefix = item.connection_name || item.data_source_name
				if (prefix) name = `${prefix} / ${name}`
			}
			refs.push({
				id: item.id,
				type,
				name,
				data_source_type: item.connection_type || item.data_source_type || undefined,
			})
		}
	}
	return refs
}

// Image preview modal
const imagePreviewModalRef = ref<InstanceType<typeof ImagePreviewModal> | null>(null)

function openImagePreview(file: any) {
	imagePreviewModalRef.value?.open(file)
}

function scrollToMessage(messageId: string, stepId?: string) {
	const container = scrollContainer.value
	if (!container) return
	// If a stepId is provided, try to scroll to the specific tool execution block first
	if (stepId) {
		const stepEl = container.querySelector(`[data-step-id="${stepId}"]`) as HTMLElement
		if (stepEl) {
			stepEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
			return
		}
	}
	const el = container.querySelector(`[data-message-id="${messageId}"]`) as HTMLElement
	if (el) {
		el.scrollIntoView({ behavior: 'smooth', block: 'center' })
	}
}

function scrollToBottom() {
  // Single-pass scroll: go to max scroll position
  nextTick(() => {
    setTimeout(() => {
      const container = scrollContainer.value
      if (!container) return
      container.offsetHeight // force reflow
      container.scrollTop = container.scrollHeight
    }, 40)
  })
}

// Guarded scroll that respects user upward scrolling during streaming
function safeScrollToBottom() {
  if (isStreaming.value && suppressAutoScroll.value) return
  scrollToBottom()
}

// Only auto-scroll when the user is already near the bottom to avoid jumpiness
function autoScrollIfNearBottom() {
  const container = scrollContainer.value
  if (!container) return
  const threshold = NEAR_BOTTOM_PX
  const distanceFromBottom = container.scrollHeight - (container.scrollTop + container.clientHeight)
  if (suppressAutoScroll.value && isStreaming.value) return
  if (distanceFromBottom <= threshold) {
    scrollToBottom()
  }
}

function scheduleInitialScroll() {
    const delays = [0, 80, 160, 320, 640]
    for (const delay of delays) setTimeout(safeScrollToBottom, delay)
}

// Keep scrolling to bottom across successive layout passes until height stabilizes
function settleScrollToBottom(maxFrames = 24) {
    const container = scrollContainer.value
    if (!container) return
    let frames = 0
    let lastHeight = -1
    const tick = () => {
        if (!scrollContainer.value) return
        const h = scrollContainer.value.scrollHeight
        if (h !== lastHeight) {
            lastHeight = h
            scrollContainer.value.scrollTop = h
            frames = 0
        } else {
            frames++
        }
        if (frames < 3 && maxFrames-- > 0) {
            requestAnimationFrame(tick)
        }
    }
    requestAnimationFrame(tick)
}

async function handleStreamingEvent(eventType: string | null, payload: any, sysMessageIndex: number) {
	if (!eventType || sysMessageIndex === -1) return
	
	if (!messages.value[sysMessageIndex]) return

	const sysMessage = messages.value[sysMessageIndex]

	// ADDITIVE: feed EVERY event through the step reducer for the Activity tab.
	// reduceStepEvent is auto-imported (utils/stepMap.ts) and try/catch-safe;
	// wrap the assignment too so it can never break the existing painting below.
	try {
		;(sysMessage as any).steps = reduceStepEvent((sysMessage as any).steps || [], eventType, payload)
	} catch (e) {
		// never let step tracking interfere with the live stream
	}

	switch (eventType) {
		case 'completion.started':
			// Update system message status
			sysMessage.status = 'in_progress'
			// Stash backend system completion id for stop-generation (sigkill)
			if (payload && payload.system_completion_id) {
				sysMessage.system_completion_id = payload.system_completion_id
				currentOfficeJsCompletionId.value = payload.system_completion_id
			}
			break

		case 'instructions.context':
			// Track which instructions were loaded (context build or tool calls)
			if (!sysMessage._loaded_instructions) sysMessage._loaded_instructions = []
			for (const inst of (payload?.instructions || [])) {
				if (inst?.id && !sysMessage._loaded_instructions.some((i: any) => i.id === inst.id)) {
					sysMessage._loaded_instructions.push({ ...inst, source: payload.source || 'context_build' })
				}
			}
			break

		case 'instructions.suggest.started':
			// Flip a flag so <KnowledgeGroup> renders immediately in a loading
			// state, even before the first harness block arrives.
			;(sysMessage as any)._harness_running = true
			break

		case 'instructions.suggest.partial':
			break
		case 'instructions.suggest.finished':
			;(sysMessage as any)._harness_running = false
			break

		case 'block.upsert':
			// Add or update a completion block
			if (payload.block) {
				const block = payload.block
				if (!sysMessage.completion_blocks) {
					sysMessage.completion_blocks = []
				}

				// Find existing block or insert in-order by block_index (avoid resorting array)
				const existingIndex = sysMessage.completion_blocks.findIndex(b => b.id === block.id)
				if (existingIndex >= 0) {
					// Update existing block in place. Preserve any locally-populated
					// tool_execution placeholder (from the kickoff stream's decision.partial
					// handler) when the incoming payload doesn't carry a real one yet —
					// the early sync upsert after decision.final serializes tool_execution
					// as null because the bg INSERT hasn't landed, and a blind
					// Object.assign would wipe the args/name we already painted.
					const existing = sysMessage.completion_blocks[existingIndex]
					const incomingHasTE = block.tool_execution && (block.tool_execution as any).id
					const merged = { ...block }
					if (!incomingHasTE && existing.tool_execution) {
						delete (merged as any).tool_execution
					}
					Object.assign(existing, merged)
				} else {
					let insertPos = sysMessage.completion_blocks.length
					for (let i = 0; i < sysMessage.completion_blocks.length; i++) {
						const bi = sysMessage.completion_blocks[i]
						if ((bi?.block_index ?? Number.MAX_SAFE_INTEGER) > (block?.block_index ?? Number.MAX_SAFE_INTEGER)) {
							insertPos = i
							break
						}
					}
					sysMessage.completion_blocks.splice(insertPos, 0, block)
				}
			}
			break

		case 'block.delta.text':
			// Update text snapshot for a specific block (full overwrite)
			// Mutate in-place to avoid triggering full array reactivity
			if (payload.block_id && payload.field && payload.text) {
				const block = sysMessage.completion_blocks?.find(b => b.id === payload.block_id)
				if (block) {
					if (payload.field === 'content') {
						block.content = payload.text
					} else if (payload.field === 'reasoning') {
						block.reasoning = payload.text
						if (!block.plan_decision) block.plan_decision = {}
						block.plan_decision.reasoning = payload.text
						// Auto-scroll reasoning box
						nextTick(() => scrollReasoningToBottom(payload.block_id))
					}
				}
			}
			break

		case 'block.delta.token':
			// Handle individual token streaming for real-time typing effect
			// Mutate in-place to avoid triggering full array reactivity on every token
			if (payload.block_id && payload.field && payload.token) {
				const block = sysMessage.completion_blocks?.find(b => b.id === payload.block_id)
				if (block) {
					const t = String(payload.token || '')
					if (payload.field === 'content') {
						block.content = (block.content || '') + t
					} else if (payload.field === 'reasoning') {
						block.reasoning = (block.reasoning || '') + t
						if (!block.plan_decision) block.plan_decision = {}
						block.plan_decision.reasoning = (block.plan_decision.reasoning || '') + t
						// Auto-scroll reasoning box
						nextTick(() => scrollReasoningToBottom(payload.block_id))
					}
				}
			}
			break

		case 'block.delta.text.complete':
			// Field finalization marker — no action needed, MarkdownRender handles it via :final
			break

		case 'block.delta.artifact':
			// Handle artifact changes (for progressive updates)
			if (payload.change && payload.change.type === 'step') {
				const block = sysMessage.completion_blocks?.find(b => b.tool_execution?.created_step_id === payload.change.step_id)
				if (block && block.tool_execution) {
					block.status = 'in_progress'
					// Merge streamed data_model fields into tool_execution.result_json for live UI updates
					const fields = payload.change.fields || {}
					if (fields.data_model) {
						block.tool_execution.result_json = block.tool_execution.result_json || {}
						const rj: any = block.tool_execution.result_json
						rj.data_model = { ...(rj.data_model || {}), ...fields.data_model }
						if (Array.isArray(fields.data_model.columns)) {
							const existing = new Map<string, any>((rj.data_model.columns || []).map((c: any) => [c.generated_column_name, c]))
							for (const col of fields.data_model.columns) existing.set(col.generated_column_name, col)
							rj.data_model.columns = Array.from(existing.values())
						}
					}
				}
			}
			break

		case 'tool.started':
			// Update block to show tool execution started
			if (payload.tool_name) {
				// Find the most recent block and update it
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock) {
					if (!lastBlock.tool_execution) {
						lastBlock.tool_execution = {
							id: `temp-${Date.now()}`,
							tool_name: payload.tool_name,
							status: 'running'
						}
					}
					// Reset result_json for fresh run to avoid stale shared references
					lastBlock.tool_execution.result_json = {}
					// For describe_tables, stash the query so the UI can show it
					try {
						if (payload.tool_name === 'describe_tables' && payload.arguments) {
							const q = payload.arguments.query
							const qStr = Array.isArray(q) ? q.join(', ') : (typeof q === 'string' ? q : (q ? JSON.stringify(q) : 'tables'))
							;(lastBlock.tool_execution.result_json as any).search_query = q
							lastBlock.tool_execution.result_summary = `Searching ${qStr}…`
						}
						if (payload.tool_name === 'read_resources' && payload.arguments) {
							const q = payload.arguments.query
							const qStr = Array.isArray(q) ? q.join(', ') : (typeof q === 'string' ? q : (q ? JSON.stringify(q) : 'resources'))
							;(lastBlock.tool_execution.result_json as any).search_query = q
							lastBlock.tool_execution.result_summary = `Searching ${qStr}…`
						}
						if (payload.tool_name === 'describe_entity' && payload.arguments) {
							const nameOrId = payload.arguments.name_or_id || 'entity'
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
							lastBlock.tool_execution.result_summary = `Loading from catalog: "${nameOrId}"…`
						}
						if (payload.tool_name === 'create_artifact' && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
							;(lastBlock.tool_execution as any).report_id = report_id
							const modeLabel = payload.arguments.mode === 'slides' ? 'presentation' : 'dashboard'
							lastBlock.tool_execution.result_summary = `Creating ${modeLabel}: "${payload.arguments.title || 'Untitled'}"…`
						}
						if (payload.tool_name === 'edit_artifact' && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
						}
						if (payload.tool_name === 'inspect_data' && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
						}
						if ((payload.tool_name === 'execute_mcp' || payload.tool_name === 'search_mcps') && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
						}
						if ((payload.tool_name === 'create_instruction' || payload.tool_name === 'edit_instruction') && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
						}
						if (payload.tool_name === 'search_instructions' && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
							const q = payload.arguments.query
							const qStr = Array.isArray(q) ? q.join(', ') : (typeof q === 'string' ? q : (q ? JSON.stringify(q) : 'instructions'))
							;(lastBlock.tool_execution.result_json as any).search_query = q
							lastBlock.tool_execution.result_summary = `Searching instructions for ${qStr}…`
						}
						if (payload.tool_name === 'clarify' && payload.arguments) {
							;(lastBlock.tool_execution as any).arguments_json = payload.arguments
						}
					} catch {}
					lastBlock.status = 'in_progress'
				}
			}
			break

		case 'tool.progress':
			// Update tool execution progress on the latest block (best-effort) and stream data model deltas
			if (payload.tool_name) {
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock) {
					if (!lastBlock.tool_execution) {
						lastBlock.tool_execution = {
							id: `temp-${Date.now()}`,
							tool_name: payload.tool_name,
							status: 'running'
						}
					} else {
						lastBlock.tool_execution.status = 'running'
					}

					// Best-effort cancel of a running Office.js execution in the taskpane
					// (sigkill or timeout path from the backend tool).
					const cancelAction = payload.payload?.excel_action
					if (cancelAction && cancelAction.type === 'cancelOfficeJs' && isExcel.value) {
						try {
							window.parent.postMessage({
								type: 'cancelOfficeJs',
								data: JSON.stringify(cancelAction)
							}, window.location.origin)
						} catch (e) {
							console.warn('Failed to forward cancelOfficeJs to Excel taskpane:', e)
						}
					}

					// Record progress stage for tool-specific UIs
					if (payload.payload && lastBlock.tool_execution) {
						;(lastBlock.tool_execution as any).progress_stage = payload.payload.stage || null
						// Capture icon for read_resources submit_search stage if provided
						if (payload.tool_name === 'read_resources' && payload.payload.stage === 'submit_search' && payload.payload.icon) {
							lastBlock.tool_execution.result_json = lastBlock.tool_execution.result_json || {}
							;(lastBlock.tool_execution.result_json as any).icon = payload.payload.icon
						}
						// Capture connection_name for execute_mcp when resolved
						if (payload.tool_name === 'execute_mcp' && payload.payload.stage === 'connection_resolved' && payload.payload.connection_name) {
							lastBlock.tool_execution.result_json = lastBlock.tool_execution.result_json || {}
							;(lastBlock.tool_execution.result_json as any).connection_name = payload.payload.connection_name
						}

						// Capture code, attempt, and errors for create_data / inspect_data
						if ((payload.tool_name === 'create_data' || payload.tool_name === 'inspect_data') && payload.payload) {
							const p = payload.payload
							const te = lastBlock.tool_execution as any
							// Stream generated code from code_generated stage
							if (p.stage === 'generated_code' && p.code) {
								te.progress_code = p.code
							}
							// Track current attempt number
							if (typeof p.attempt === 'number') {
								te.progress_attempt = p.attempt
							}
							// On retry, capture the error that triggered it
							if (p.stage === 'retry') {
								te.progress_errors = te.progress_errors || []
								// The error was already emitted via stdout before the retry event
							}
						}
					}

          // Progressive data model updates for create_widget tool
          if ((payload.tool_name === 'create_widget') && payload.payload) {
						const p = payload.payload
						// Ensure result_json.data_model structure exists
						lastBlock.tool_execution.result_json = lastBlock.tool_execution.result_json || {}
						const rj = lastBlock.tool_execution.result_json as any
						rj.data_model = rj.data_model || { type: null, columns: [], series: [] }

						if (p.stage === 'data_model_type_determined' && p.data_model_type) {
							rj.data_model.type = p.data_model_type
						}
						if (p.stage === 'column_added' && p.column) {
							const exists = (rj.data_model.columns || []).some((c: any) => c.generated_column_name === p.column.generated_column_name)
							if (!exists) {
								rj.data_model.columns.push(p.column)
							}
						}
						if (p.stage === 'series_configured' && Array.isArray(p.series)) {
							rj.data_model.series = p.series
						}
						if (p.stage === 'widget_creation_needed' && p.data_model) {
							rj.data_model = { ...rj.data_model, ...p.data_model }
						}
					}

					// Progressive visualization updates for create_data tool
					if (payload.tool_name === 'create_data' && payload.payload?.stage === 'visualization_inferred') {
						const p = payload.payload
						;(lastBlock.tool_execution as any).progress_visualization = {
							chart_type: p.chart_type,
							series: p.series || [],
							group_by: p.group_by
						}
					}
					// Visualization error for create_data tool
					if (payload.tool_name === 'create_data' && payload.payload?.stage === 'visualization_error') {
						;(lastBlock.tool_execution as any).progress_visualization_error = payload.payload.error
					}

					// Live progress for run_eval — case-by-case status updates
					if (payload.tool_name === 'run_eval' && payload.payload && typeof payload.payload.kind === 'string' && payload.payload.kind.indexOf('eval.') === 0) {
						const te: any = lastBlock.tool_execution
						te.eval_progress = te.eval_progress || {
							run_id: null,
							total: 0,
							finished: 0,
							passed: 0,
							failed: 0,
							status: '',
							cases: [],
						}
						const ep = te.eval_progress
						const p = payload.payload
						if (p.kind === 'eval.run_started') {
							ep.run_id = p.run_id || null
							ep.total = typeof p.total === 'number' ? p.total : (Array.isArray(p.case_ids) ? p.case_ids.length : 0)
							ep.status = 'in_progress'
							// Seed per-case rows so the list renders before any case finishes.
							const ids: string[] = Array.isArray(p.case_ids) ? p.case_ids : []
							const names: string[] = Array.isArray(p.case_names) ? p.case_names : []
							ep.cases = ids.map((cid: string, i: number) => ({
								case_id: cid,
								case_name: names[i] || '',
								status: 'init',
							}))
						} else if (p.kind === 'eval.case_started') {
							const row = ep.cases.find((c: any) => c.case_id === p.case_id)
							if (row) row.status = 'in_progress'
							else ep.cases.push({ case_id: p.case_id, case_name: p.case_name || '', status: 'in_progress' })
						} else if (p.kind === 'eval.case_finished') {
							const row = ep.cases.find((c: any) => c.case_id === p.case_id)
							if (row) {
								row.status = p.status
								row.failure_reason = p.failure_reason || null
							} else {
								ep.cases.push({ case_id: p.case_id, case_name: p.case_name || '', status: p.status, failure_reason: p.failure_reason || null })
							}
							if (typeof p.passed_so_far === 'number') ep.passed = p.passed_so_far
							if (typeof p.failed_so_far === 'number') ep.failed = p.failed_so_far
							if (typeof p.finished_so_far === 'number') ep.finished = p.finished_so_far
						} else if (p.kind === 'eval.run_finished') {
							ep.status = p.status || 'success'
							if (typeof p.passed === 'number') ep.passed = p.passed
							if (typeof p.failed === 'number') ep.failed = p.failed
							if (typeof p.finished === 'number') ep.finished = p.finished
						}
					}

					// Progressive instruction drafts for suggest_instructions tool
					if (payload.tool_name === 'suggest_instructions' && payload.payload) {
						const p = payload.payload
						if (p.stage === 'instruction_added' && p.instruction) {
							lastBlock.tool_execution.result_json = lastBlock.tool_execution.result_json || {}
							const rj: any = lastBlock.tool_execution.result_json
							rj.drafts = Array.isArray(rj.drafts) ? rj.drafts : []
							const draft = { text: String(p.instruction.text || ''), category: p.instruction.category || null }
							if (draft.text) {
								rj.drafts.push(draft)
								lastBlock.status = 'in_progress'
							}
						}
					}

					// When create_dashboard streams a completed block, broadcast layout change so previews refresh membership
					if (payload.tool_name === 'create_dashboard' && payload.payload && payload.payload.stage === 'block.completed') {
						try {
							window.dispatchEvent(new CustomEvent('dashboard:layout_changed', { detail: { report_id: report_id, action: 'added' } }))
						} catch {}
					}

					// Visualizations resolved for create_artifact / edit_artifact
					if ((payload.tool_name === 'create_artifact' || payload.tool_name === 'edit_artifact') && payload.payload) {
						if (payload.payload.stage === 'visualizations_resolved' && Array.isArray(payload.payload.visualizations)) {
							;(lastBlock.tool_execution as any).progress_visualizations = payload.payload.visualizations
						}
					}

					// Progressive slide tracking for create_artifact tool
					if (payload.tool_name === 'create_artifact' && payload.payload) {
						const p = payload.payload
						// Artifact created with pending status - notify frontend
						if (p.stage === 'artifact_created' && p.artifact_id) {
							;(lastBlock.tool_execution as any).pending_artifact_id = p.artifact_id
							// Dispatch event so ArtifactFrame can show the pending artifact
							hasArtifacts.value = true
							try {
								window.dispatchEvent(new CustomEvent('artifact:created', {
									detail: {
										report_id: report_id,
										artifact_id: p.artifact_id,
										status: 'pending'
									}
								}))
							} catch {}
						}
						// Track generating progress
						if (p.stage === 'generating') {
							;(lastBlock.tool_execution as any).progress_stage = 'generating'
							;(lastBlock.tool_execution as any).progress_payload = { chars: p.chars }
						}
						// Track slides as they're generated
						if (p.stage === 'slide_generated') {
							;(lastBlock.tool_execution as any).progress_stage = 'generating_slides'
							const slides = (lastBlock.tool_execution as any).progress_slides || []
							// Mark previous slides as done
							for (let i = 0; i < slides.length; i++) {
								slides[i].status = 'done'
							}
							// Add new slide as generating
							while (slides.length <= p.slide_index) {
								slides.push({ status: slides.length === p.slide_index ? 'generating' : 'done' })
							}
							;(lastBlock.tool_execution as any).progress_slides = slides
						}
						// Store artifact info from arguments
						if (p.title) {
							lastBlock.tool_execution.arguments_json = lastBlock.tool_execution.arguments_json || {}
							;(lastBlock.tool_execution.arguments_json as any).title = p.title
						}
					}

					lastBlock.status = 'in_progress'
				}
			}
			break

		case 'tool.stdout':
			// Capture stdout messages (errors, execution logs) for create_data / inspect_data
			if (payload.tool_name) {
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock?.tool_execution) {
					const te = lastBlock.tool_execution as any
					te.progress_stdout = te.progress_stdout || []
					const msg = typeof payload.payload === 'string' ? payload.payload : (payload.payload?.message || '')
					if (msg) {
						te.progress_stdout.push(msg)
					}
				}
			}
			break

		case 'tool.confirmation':
			// Confirmation request from create_artifact / edit_artifact
			if (payload.tool_name) {
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock?.tool_execution) {
					;(lastBlock.tool_execution as any).confirmation = payload.payload
					;(lastBlock.tool_execution as any).progress_stage = 'awaiting_confirmation'
				}
			}
			break

		case 'tool.partial':
			// Streamed partial output for tools
			if (payload.tool_name) {
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock) {
					if (!lastBlock.tool_execution) {
						lastBlock.tool_execution = {
							id: `temp-${Date.now()}`,
							tool_name: payload.tool_name,
							status: 'running'
						}
					}
					const fullAnswer = (payload.payload && typeof payload.payload.answer === 'string') ? payload.payload.answer : null
					const delta = (payload.payload && typeof payload.payload.delta === 'string') ? payload.payload.delta : null
					lastBlock.tool_execution.result_json = lastBlock.tool_execution.result_json || {}
					const rj: any = lastBlock.tool_execution.result_json
					if (fullAnswer !== null) {
						// Replace with accumulated answer (preferred)
						rj.answer = fullAnswer
						lastBlock.status = 'in_progress'
					} else if (delta) {
						// Backward-compatibility: append streaming delta
						rj.answer = (rj.answer || '') + delta
						lastBlock.status = 'in_progress'
					}
					// Forward Office.js code execution to the Excel taskpane.
					const excelAction = payload.payload?.excel_action
					if (excelAction && excelAction.type === 'runOfficeJs' && isExcel.value) {
						try {
							window.parent.postMessage({
								type: 'runOfficeJs',
								data: JSON.stringify(excelAction)
							}, window.location.origin)
						} catch (e) {
							console.warn('Failed to forward runOfficeJs to Excel taskpane:', e)
						}
						if (lastBlock.tool_execution) {
							lastBlock.tool_execution.arguments_json = lastBlock.tool_execution.arguments_json || {}
							const aj: any = lastBlock.tool_execution.arguments_json
							if (excelAction.code && !aj.code) aj.code = excelAction.code
							if (excelAction.description && !aj.description) aj.description = excelAction.description
						}
					}
				}
			}
			break

		case 'widget.created':
			// No-op for now; this is displayed in the report UI elsewhere
			break

		case 'data_model.completed':
			// No-op; step/widget UIs will reflect final data model. Avoid logging unknown.
			break

		case 'tool.finished':
			// Update tool execution status
			if (payload.tool_name && payload.status) {
				// Prefer precise targeting when identifiers are available
				const blocks = sysMessage.completion_blocks || []
				let blockWithTool = blocks.find(b => (payload.block_id && b.id === payload.block_id)) 
					|| blocks.find(b => (payload.tool_execution_id && b.tool_execution?.id === payload.tool_execution_id))
					// Fallback: choose the most recent running/in-progress block for this tool
					|| [...blocks].reverse().find(b => 
						b.tool_execution?.tool_name === payload.tool_name && 
						(b.tool_execution?.status === 'running' || b.status === 'in_progress')
					)
					// Last fallback: most recent block with matching tool name
					|| [...blocks].reverse().find(b => b.tool_execution?.tool_name === payload.tool_name)

				if (blockWithTool?.tool_execution) {
					// Replace the synthetic kickoff-/temp- id with the real DB UUID once
					// the backend reports it — the form submit endpoint needs the real id.
					const realId = payload.tool_execution_id
					const looksLikeUuid = typeof realId === 'string' && /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(realId)
					if (looksLikeUuid && typeof blockWithTool.tool_execution.id === 'string' &&
						(blockWithTool.tool_execution.id.startsWith('kickoff-') || blockWithTool.tool_execution.id.startsWith('temp-'))) {
						blockWithTool.tool_execution.id = realId
					}
					blockWithTool.tool_execution.status = payload.status
					blockWithTool.status = payload.status === 'success' ? 'success' : payload.status === 'stopped' ? 'stopped' : 'error'
					if (payload.result_summary) {
						blockWithTool.tool_execution.result_summary = payload.result_summary
					}
					if (payload.result_json) {
						blockWithTool.tool_execution.result_json = payload.result_json
					}
					if (payload.duration_ms !== undefined) {
						blockWithTool.tool_execution.duration_ms = payload.duration_ms
					}
					if (payload.created_widget_id) {
						blockWithTool.tool_execution.created_widget_id = payload.created_widget_id
					}
					if (payload.created_step_id) {
						blockWithTool.tool_execution.created_step_id = payload.created_step_id
					}
					// Populate created_visualizations from the IDs sent by backend
					if (payload.created_visualization_ids && Array.isArray(payload.created_visualization_ids) && payload.created_visualization_ids.length > 0) {
						blockWithTool.tool_execution.created_visualizations = payload.created_visualization_ids.map((id: string) => ({ id }))
					}
					// If the dashboard was created successfully, refresh widgets and open the dashboard pane
					if (payload.tool_name === 'create_dashboard' && payload.status === 'success') {
						try { await loadVisualizations() } catch (e) { /* noop */ }
						if (!isSplitScreen.value) toggleSplitScreen()
						try {
							window.dispatchEvent(new CustomEvent('dashboard:version_snapshot', { detail: { report_id: report_id, change_summary: 'Built dashboard from chat', source: 'chat' } }))
						} catch {}
					}
					// If the artifact was created successfully, mark all slides as done and dispatch event
					if (payload.tool_name === 'create_artifact' && payload.status === 'success') {
						// Mark all slides as done
						const slides = (blockWithTool.tool_execution as any).progress_slides || []
						for (const slide of slides) {
							slide.status = 'done'
						}
						// Update hasArtifacts state and dispatch event to notify ArtifactFrame
						hasArtifacts.value = true
						try {
							window.dispatchEvent(new CustomEvent('artifact:created', {
								detail: {
									report_id: report_id,
									artifact_id: payload.result_json?.artifact_id
								}
							}))
						} catch {}
						try {
							window.dispatchEvent(new CustomEvent('dashboard:version_snapshot', { detail: { report_id: report_id, change_summary: 'Added chart from chat', source: 'chat' } }))
						} catch {}
					}
					// If artifact was edited successfully, refresh ArtifactFrame with the new version
					if (payload.tool_name === 'edit_artifact' && payload.status === 'success') {
						hasArtifacts.value = true
						try {
							window.dispatchEvent(new CustomEvent('artifact:created', {
								detail: {
									report_id: report_id,
									artifact_id: payload.result_json?.artifact_id
								}
							}))
						} catch {}
						try {
							window.dispatchEvent(new CustomEvent('dashboard:version_snapshot', { detail: { report_id: report_id, change_summary: 'Edited chart from chat', source: 'chat' } }))
						} catch {}
					}
					// If write_to_excel completed, forward data to Excel taskpane via postMessage
					if (payload.tool_name === 'write_to_excel' && payload.status === 'success' && payload.result_json?.excel_action && isExcel.value) {
						try {
							const action = payload.result_json.excel_action
							window.parent.postMessage({
								type: action.type,
								data: JSON.stringify(action.data)
							}, window.location.origin)
						} catch (e) {
							console.warn('Failed to forward write_to_excel data to Excel taskpane:', e)
						}
					}
				}
			}
			break

		case 'sense_making.pending':
			// Backend is about to run post-answer sense-making — show the
			// "forming the decision" strip + Outputs DECISION skeleton.
			decisionForming.value = true
			break

		case 'sense_making.ready':
			// The finished Decision card arrived live — attach it to the
			// streaming system message so DecisionCard renders WITHOUT a reload,
			// and clear the "forming the decision" shimmer. (Before this event
			// existed, the payload was only in the DB and the card showed only
			// after a full page reload.)
			if (sysMessage && payload && payload.sense_making) {
				sysMessage.sense_making = payload.sense_making
			}
			decisionForming.value = false
			break

		case 'decision.partial':
		case 'decision.final':
			// Update plan decision information
			// Note: decision.final events may only contain analysis_complete/final_answer without reasoning/assistant
			if (payload.reasoning || payload.assistant || payload.final_answer !== undefined || payload.analysis_complete !== undefined) {
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock) {
					if (!lastBlock.plan_decision) {
						lastBlock.plan_decision = {}
					}
					if (payload.reasoning) {
						lastBlock.plan_decision.reasoning = payload.reasoning
					}
					if (payload.assistant) {
						lastBlock.plan_decision.assistant = payload.assistant
					}
					if (payload.final_answer) {
						lastBlock.plan_decision.final_answer = payload.final_answer
					}
					if (eventType === 'decision.final') {
						lastBlock.plan_decision.analysis_complete = payload.analysis_complete ?? true
					}
				}
			}
			// Tool kickoff: the planner emits action.name on ToolUseStart (~1s before
			// tool.started fires). Paint a placeholder tool_execution so the widget
			// renders immediately; the second decision.partial after ToolUseComplete
			// brings full args, and tool.started later flips status to running.
			if (payload.action?.name) {
				const lastBlock = sysMessage.completion_blocks?.[sysMessage.completion_blocks.length - 1]
				if (lastBlock) {
					const args = payload.action.arguments || {}
					const hasArgs = args && Object.keys(args).length > 0
					if (!lastBlock.tool_execution) {
						lastBlock.tool_execution = {
							id: `kickoff-${lastBlock.id}`,
							tool_name: payload.action.name,
							status: 'running',
							arguments_json: hasArgs ? args : undefined,
						} as any
					} else if (hasArgs) {
						;(lastBlock.tool_execution as any).arguments_json = args
					}
				}
			}
			break

		case 'completion.finished':
			// completion.finished (and the backend's agent_execution_done / queue_finished)
			// is a real terminal signal. Always leave the run in a terminal status so the
			// "Thinking…" dots (gated on status==='in_progress') clear here even if the
			// payload omits an explicit status — don't wait on [DONE]/watchdog for the spinner.
			// Turn is fully done — clear the "forming the decision" strip.
			decisionForming.value = false
			const completionStatus = (payload && typeof payload.status === 'string') ? payload.status : 'success'
			if (completionStatus) {
				if (sysMessage.status !== 'error' && sysMessage.status !== 'stopped') {
					sysMessage.status = completionStatus as any
				} else if (completionStatus === 'error') {
					sysMessage.status = 'error' as any
				}
				if (completionStatus === 'error') {
					const errPayload = payload?.error || {}
					const errMsg: string = (typeof errPayload === 'string' ? errPayload : null)
						|| errPayload.message
						|| (errPayload.summary && errPayload.provider_message ? `${errPayload.summary}: ${errPayload.provider_message}` : (errPayload.summary || errPayload.provider_message))
						|| sysMessage.error_message
						|| ''
					if (errMsg) sysMessage.error_message = errMsg
					if (!sysMessage.completion_blocks?.some((b: any) => b.status === 'error')) {
						sysMessage.completion_blocks = sysMessage.completion_blocks || []
						sysMessage.completion_blocks.push({ id: `error-${Date.now()}`, block_index: 999, status: 'error', content: sysMessage.error_message || '' })
					}
				}
				// NOTE: do NOT flip isStreaming here. The knowledge harness continues
				// streaming SSE events (block.upsert/tool.*) after completion.finished
				// fires. Flipping isStreaming=false early opens a race window where
				// polling/refetch paths can wipe messages.value mid-stream. [DONE] is
				// the single source of truth for end-of-stream. Thumbs-up and
				// stop→submit UI should gate on sysMessage.status, not isStreaming.
			}
			// Unblock the prompt box so the user can submit new prompts while
			// the knowledge harness continues in the background.
			isCompletionInProgress.value = false
			// Suggested follow-up questions (fire-and-forget, after blocks settle).
			setTimeout(() => { fetchFollowups(sysMessage) }, 0)
			// Note: loadReport and refreshContextEstimate are called after [DONE] to avoid blocking
			break

		case 'completion.error':
			// Dedicated error event; ensure UI flips to error state and capture the message
			decisionForming.value = false
			sysMessage.status = 'error'
			isCompletionInProgress.value = false
			if (payload?.error) {
				const msg = typeof payload.error === 'string' ? payload.error : (payload.error.message || '')
				if (msg) sysMessage.error_message = String(msg)
				if (!sysMessage.completion_blocks?.some((b: any) => b.status === 'error')) {
					sysMessage.completion_blocks = sysMessage.completion_blocks || []
					sysMessage.completion_blocks.push({ id: `error-${Date.now()}`, block_index: 999, status: 'error', content: sysMessage.error_message })
				}
			}
			break

		case 'llm.error':
			try {
				const err = payload || {}
				const summary = String(err.summary || `${err.provider || 'LLM provider'} call failed`)
				const providerMessage = String(err.provider_message || '')
				if (!sysMessage.error_message) {
					sysMessage.error_message = providerMessage
						? (summary && summary !== providerMessage ? `${summary}: ${providerMessage}` : providerMessage)
						: summary
				}
			} catch (e) {
				console.warn('llm.error handler failed', e)
			}
			break

		default:
			// Handle unknown events gracefully
			break
	}
}

// Live refresh for inbound webhook events: when a webhook-tagged completion is
// inserted/updated server-side (event entry created, 👀 → ✅), refresh the
// timeline. Guarded on `webhook_id` so a user's own messages never trigger it.
const _rtConfig = useRuntimeConfig()
let _webhookWs: WebSocket | null = null
let _webhookReloadTimer: any = null
function connectWebhookSocket() {
	try {
		const wsURL = (_rtConfig.public as any)?.wsURL
		if (!wsURL || !report_id) return
		_webhookWs = new WebSocket(`${wsURL}/reports/${report_id}`)
		_webhookWs.onmessage = (event: MessageEvent) => {
			try {
				const data = JSON.parse(event.data)
				if ((data.event === 'insert_completion' || data.event === 'update_completion') && data.webhook_id) {
					if (_webhookReloadTimer) clearTimeout(_webhookReloadTimer)
					_webhookReloadTimer = setTimeout(() => loadCompletions({ skipEstimate: true }), 400)
				}
			} catch {}
		}
	} catch {}
}

async function loadCompletions({ skipEstimate = false } = {}) {
	try {
		const { data } = await useMyFetch(`/reports/${report_id}/completions?limit=${pageLimit}`)
		const response = data.value as any
		const list = response?.completions || []
		messages.value = list.map((c: any) => {
			// Override status if sigkill timestamp exists - this means it was stopped
			let status = c.status as ChatStatus
			if (c.sigkill && status === 'in_progress') {
				status = 'stopped'
			}
			
			const blocks = c.completion_blocks?.map((b: any) => ({
				id: b.id,
				seq: b.seq,
				block_index: b.block_index,
				loop_index: b.loop_index,
				phase: b.phase,
				title: b.title,
				icon: b.icon,
				status: b.status,
				content: b.content,
				reasoning: b.reasoning,
				plan_decision: b.plan_decision,
				tool_execution: b.tool_execution ? {
					id: b.tool_execution.id,
					tool_name: b.tool_execution.tool_name,
					tool_action: b.tool_execution.tool_action,
					status: (status === 'stopped' && b.tool_execution.status === 'running') ? 'stopped' : b.tool_execution.status,
					result_summary: b.tool_execution.result_summary,
					result_json: b.tool_execution.result_json,
					arguments_json: b.tool_execution.arguments_json,
					duration_ms: b.tool_execution.duration_ms,
					created_widget_id: b.tool_execution.created_widget_id,
					created_step_id: b.tool_execution.created_step_id,
					created_widget: b.tool_execution.created_widget,
					created_step: b.tool_execution.created_step
				} : undefined
			})) || []

			// Auto-collapse reasoning for blocks that have content or tool execution
			for (const b of blocks) {
				if ((b.content || b.tool_execution) && !manuallyToggledReasoning.value.has(b.id)) {
					collapsedReasoning.value.add(b.id)
				}
			}
			
			return {
				id: c.id,
				role: c.role as ChatRole,
				status: status,
				prompt: c.prompt,
				completion: c.completion,
				// sense_making + auto_model are promoted to TOP-LEVEL API fields
				// (completion JSON itself comes back null) — carry them or the
				// DECISION card + auto-model chip can never render.
				sense_making: (c as any).sense_making || null,
				auto_model: (c as any).auto_model || null,
				served_by: c.served_by || null,
				completion_blocks: blocks,
				created_at: c.created_at,
				sigkill: c.sigkill,
				feedback_score: c.feedback_score,
				instruction_suggestions: c.instruction_suggestions,
				knowledge_harness_build: c.knowledge_harness_build || null,
				_loaded_instructions: c.loaded_instructions || undefined,
				files: c.files || [],
				// Fork summary fields
				is_fork_summary: c.is_fork_summary,
				source_report_id: c.source_report_id,
				fork_asset_refs: c.fork_asset_refs,
				// Scheduled prompt tag
				scheduled_prompt_id: c.scheduled_prompt_id || null,
				// Webhook event entry fields
				external_platform: c.external_platform || null,
				webhook_id: c.webhook_id || null,
			}
		})
		// Update cursors
		hasMore.value = !!response?.has_more
		cursorBefore.value = response?.next_before || null
        await nextTick()
        safeScrollToBottom()
		if (!skipEstimate) {
			await promptBoxRef.value?.refreshContextEstimate?.()
		}
		await enrichForkedQueries()
		// Auto-expand the latest scheduled completion
		const lastScheduledUser = [...messages.value].reverse().find(m => m.scheduled_prompt_id && m.role === 'user')
		if (lastScheduledUser) {
			expandedScheduledIds.value.add(lastScheduledUser.id)
		}
	} catch (e) {
		console.error('Error loading completions:', e)
	} finally {
		completionsLoaded.value = true
	}
}

// Load previous page (older completions) and prepend while preserving scroll anchor
async function loadPreviousCompletions() {
    if (isLoadingMore.value || !hasMore.value) return
    const container = scrollContainer.value
    if (!container) return
    isLoadingMore.value = true
    const prevHeight = container.scrollHeight
    try {
        const qs = cursorBefore.value ? `&before=${encodeURIComponent(cursorBefore.value)}` : ''
        const { data } = await useMyFetch(`/reports/${report_id}/completions?limit=${pageLimit}${qs}`)
        const response = data.value as any
        const list: any[] = response?.completions || []
        const newItems: ChatMessage[] = list.map((c: any) => {
            let status = c.status as ChatStatus
            if (c.sigkill && status === 'in_progress') status = 'stopped'
            
            const blocks = c.completion_blocks?.map((b: any) => ({
                id: b.id,
                seq: b.seq,
                block_index: b.block_index,
                loop_index: b.loop_index,
                phase: b.phase,
                title: b.title,
                icon: b.icon,
                status: b.status,
                content: b.content,
                reasoning: b.reasoning,
                plan_decision: b.plan_decision,
                tool_execution: b.tool_execution ? {
                    id: b.tool_execution.id,
                    tool_name: b.tool_execution.tool_name,
                    tool_action: b.tool_execution.tool_action,
                    status: (status === 'stopped' && b.tool_execution.status === 'running') ? 'stopped' : b.tool_execution.status,
                    result_summary: b.tool_execution.result_summary,
                    result_json: b.tool_execution.result_json,
                    arguments_json: b.tool_execution.arguments_json,
                    duration_ms: b.tool_execution.duration_ms,
                    created_widget_id: b.tool_execution.created_widget_id,
                    created_step_id: b.tool_execution.created_step_id,
                    created_widget: b.tool_execution.created_widget,
                    created_step: b.tool_execution.created_step
                } : undefined
            })) || []

            // Auto-collapse reasoning for blocks that have content or tool execution
            for (const b of blocks) {
                if ((b.content || b.tool_execution) && !manuallyToggledReasoning.value.has(b.id)) {
                    collapsedReasoning.value.add(b.id)
                }
            }
            
            return {
                id: c.id,
                role: c.role as ChatRole,
                status,
                prompt: c.prompt,
                completion: c.completion,
                sense_making: (c as any).sense_making || null,
                auto_model: (c as any).auto_model || null,
                served_by: c.served_by || null,
                completion_blocks: blocks,
                created_at: c.created_at,
                sigkill: c.sigkill,
                feedback_score: c.feedback_score,
                instruction_suggestions: c.instruction_suggestions,
                files: c.files || [],
                scheduled_prompt_id: c.scheduled_prompt_id || null,
            }
        })
        // Dedupe by id and prepend
        const existingIds = new Set(messages.value.map(m => m.id))
        const toPrepend = newItems.filter(m => !existingIds.has(m.id))
        if (toPrepend.length > 0) {
            messages.value = [...toPrepend, ...messages.value]
            await nextTick()
            // Keep viewport anchored to previous items
            const newHeight = container.scrollHeight
            container.scrollTop = newHeight - prevHeight
        }
        hasMore.value = !!response?.has_more
        cursorBefore.value = response?.next_before || null
    } catch (e) {
        // keep hasMore as-is on error
    } finally {
        isLoadingMore.value = false
    }
}

function onScroll() {
    const container = scrollContainer.value
    if (!container) return
    // Infinite scroll trigger near top
    if (!isLoadingMore.value && hasMore.value) {
        const thresholdTop = 64
        if (container.scrollTop <= thresholdTop) {
            loadPreviousCompletions()
        }
    }

    // Update bottom proximity and user intent
    const distanceFromBottom = container.scrollHeight - (container.scrollTop + container.clientHeight)
    isUserAtBottom.value = distanceFromBottom <= RETURN_TO_BOTTOM_PX

    const isScrollingUp = container.scrollTop < lastScrollTop.value
    // Suppress auto-scroll on any upward scroll, regardless of proximity
    if (isScrollingUp) {
        suppressAutoScroll.value = true
    }
    // Re-enable only when the user returns to within tight bottom threshold
    if (!isScrollingUp && distanceFromBottom <= RETURN_TO_BOTTOM_PX) {
        suppressAutoScroll.value = false
    }
    lastScrollTop.value = container.scrollTop
}

async function loadReport() {
	const { data, error } = await useMyFetch(`/api/reports/${report_id}`)
	if (error.value || !data.value) {
		reportNotFound.value = true
		reportLoaded.value = true
		return
	}
	report.value = data.value
	reportLoaded.value = true
}

async function loadVisualizations() {
	try {
		const { data, error } = await useMyFetch(`/api/queries?report_id=${report_id}`, { method: 'GET' })
		if (error.value) throw error.value
		const queries = Array.isArray(data.value) ? data.value : []
		const list: any[] = []
		for (const q of queries) {
			for (const v of (q?.visualizations || [])) {
				if (v && v.id) list.push(v)
			}
		}
		visualizations.value = list
	} catch (e) {
		visualizations.value = []
	}
}

// Fast dashboard refresh triggered by editor save
async function refreshDashboardFast() {
    try {
        const dash = dashboardRef.value
        if (dash && typeof dash.refreshLayout === 'function') {
            await dash.refreshLayout()
        }
    } catch (e) {
        // noop
    }
}

// Ensure dashboard pane opens only when currently closed
const handleOfficeJsResult = async (event: MessageEvent) => {
    // Only accept messages from the hosting taskpane (same-origin parent).
    // The Excel taskpane is served from the same Dash instance as the report,
    // so cross-origin or same-tab-script posts must be rejected.
    if (event.source !== window.parent) return
    if (event.origin !== window.location.origin) return
    const data = event.data
    if (!data || data.type !== 'officeJsResult') return
    let parsed: any = data.data
    try { if (typeof parsed === 'string') parsed = JSON.parse(parsed) } catch { return }
    if (!parsed || !parsed.id) return
    const { id, completion_id: echoedCompletionId, ...body } = parsed
    // Prefer the echoed completion_id (embedded in the runOfficeJs action by
    // the backend). Falling back to the ref covers older tool calls that
    // dispatched before the echo was added. If both are missing we silently
    // drop — which was the silent-drop bug; warn loudly so it's debuggable.
    const completionId = echoedCompletionId || currentOfficeJsCompletionId.value
    if (!completionId) {
        console.warn('[dash-officejs] dropping result — no completion_id (echoed or ref). tool_call_id=', id)
        return
    }
    try {
        await useMyFetch(`/api/completions/${completionId}/tool-results/${id}`, {
            method: 'POST',
            body,
        })
    } catch (e) {
        console.warn('[dash-officejs] POST officeJsResult failed', { tool_call_id: id, completion_id: completionId, error: e })
    }
}

const markdownAutoDir = ref<{ stop: () => void } | null>(null)

onMounted(() => {
    window.addEventListener('dashboard:ensure_open', () => {
        if (!isSplitScreen.value) toggleSplitScreen()
    })
    window.addEventListener('artifact:open', ((ev: CustomEvent) => {
        handleOpenArtifact({ artifactId: ev.detail?.artifact_id })
    }) as EventListener)
    window.addEventListener('message', handleOfficeJsResult)
    markdownAutoDir.value = useMarkdownAutoDir()
    loadOneClickFlag().then(loadWorkbook)
    loadCoworkFlag()
})

// When a tool finishes saving a new step, broadcast the default step change if we have enough info
// Track last dispatched step to avoid duplicate events during streaming
const lastDispatchedStepId = ref<string | null>(null)

watch(
    // Only watch the created step ID, not deep message content
    () => {
        const last = [...messages.value].reverse().find(m => m.role === 'system')
        const lastBlock = last?.completion_blocks?.slice(-1)[0]
        return lastBlock?.tool_execution?.created_step?.id || null
    },
    (stepId) => {
        if (!stepId || stepId === lastDispatchedStepId.value) return
        lastDispatchedStepId.value = stepId
        
        try {
            const last = [...messages.value].reverse().find(m => m.role === 'system')
            const te = last?.completion_blocks?.slice(-1)[0]?.tool_execution as any
            if (te?.created_step?.query_id) {
                window.dispatchEvent(new CustomEvent('query:default_step_changed', {
                    detail: { query_id: te.created_step.query_id, step: te.created_step }
                }))
            }
        } catch {}
    }
)

async function loadActiveLayoutHasBlocks(): Promise<boolean> {
    try {
        const { data } = await useMyFetch(`/api/reports/${report_id}/layouts`)
        const layouts = Array.isArray(data.value) ? (data.value as any[]) : []
        const active = layouts.find((l: any) => l.is_active)
        const result = !!(active && Array.isArray(active.blocks) && active.blocks.length > 0)
        hasLegacyLayout.value = result
        return result
    } catch (e) {
        hasLegacyLayout.value = false
        return false
    }
}

// ── One-click artifacts (HYBRID_ONECLICK_ARTIFACTS) ─────────────────────────
// When the flag is ON, the empty Dashboard / Slides views offer a one-click
// builder that creates a REAL artifact (page dashboard or slides deck) from the
// report's existing charts, instead of a dead empty state / placeholder.
const oneClickEnabled = ref(false)
const slideGenLoading = ref(false)
const slideGenError = ref<string | null>(null)
const dashGenLoading = ref(false)
const dashGenError = ref<string | null>(null)

async function loadOneClickFlag() {
	try {
		const { data } = await useMyFetch<any[]>('/organization/hybrid-flags')
		const rows = (data.value as any[]) || []
		const row = rows.find(r => r?.env_name === 'HYBRID_ONECLICK_ARTIFACTS')
		oneClickEnabled.value = !!row?.effective
	} catch {
		oneClickEnabled.value = false  // fail-soft: fall back to placeholders
	}
}

async function generateSlideDeck() {
	if (slideGenLoading.value) return
	slideGenLoading.value = true
	slideGenError.value = null
	try {
		const { data, error } = await useMyFetch(`/reports/${report_id}/slides/generate`, { method: 'POST' })
		if (error.value) {
			throw new Error((error.value as any)?.data?.detail || 'Could not generate the deck.')
		}
		const res: any = data.value || {}
		if (res?.error && !res?.artifact_id) {
			throw new Error(res.error)
		}
		// Refetch artifacts → hasSlidesArtifact flips true → ArtifactFrame renders.
		await checkHasArtifacts()
	} catch (e: any) {
		slideGenError.value = e?.message || 'Slide generation failed. Please try again.'
	} finally {
		slideGenLoading.value = false
	}
}

async function generateDashboard() {
	if (dashGenLoading.value) return
	dashGenLoading.value = true
	dashGenError.value = null
	try {
		const { data, error } = await useMyFetch(`/reports/${report_id}/dashboard/generate`, { method: 'POST' })
		if (error.value) {
			throw new Error((error.value as any)?.data?.detail || 'Could not generate the dashboard.')
		}
		const res: any = data.value || {}
		if (res?.error && !res?.artifact_id) {
			throw new Error(res.error)
		}
		// Refetch artifacts → hasPageArtifact flips true → ArtifactFrame renders.
		await checkHasArtifacts()
	} catch (e: any) {
		dashGenError.value = e?.message || 'Dashboard generation failed. Please try again.'
	} finally {
		dashGenLoading.value = false
	}
}

// Check if the report has any artifacts
async function checkHasArtifacts(): Promise<boolean> {
    try {
        const { data } = await useMyFetch(`/artifacts/report/${report_id}`)
        const artifacts = Array.isArray(data.value) ? data.value : []
        reportArtifacts.value = artifacts
        hasArtifacts.value = artifacts.length > 0
        return hasArtifacts.value
    } catch (e) {
        reportArtifacts.value = []
        hasArtifacts.value = false
        return false
    }
}

// Sidebar control (for collapsing when entering split screen)
const { collapse: collapseSidebar } = useSidebar()

function toggleSplitScreen() {
	// On mobile there is no split layout — surface the dashboard as a
	// full-screen tab instead of opening the side panel.
	if (isMobile.value) {
		mobileView.value = mobileView.value === 'dashboard' ? 'chat' : 'dashboard'
		return
	}
	nextTick(() => {
		isSplitScreen.value = !isSplitScreen.value
		if (isSplitScreen.value) {
			const windowWidth = window.innerWidth
			leftPanelWidth.value = (rightPanelView.value === 'summary' || rightPanelView.value === 'activity' || rightPanelView.value === 'studio')
				? Math.round(windowWidth * 0.55)
				: rightPanelView.value === 'agent'
				? Math.round(windowWidth * 0.45)
				: Math.round(windowWidth * 0.37)
			collapseSidebar()
		}
        safeScrollToBottom()
	})
}

function startResize(e: MouseEvent) {
	isResizing.value = true
	initialMouseX.value = e.clientX
	initialPanelWidth.value = leftPanelWidth.value
		document.addEventListener('mousemove', handleResize)
	document.addEventListener('mouseup', stopResize)
	document.body.style.userSelect = 'none'
}

function handleResize(e: MouseEvent) {
	if (!isResizing.value) return
	const minWidth = 280
	const maxWidth = window.innerWidth * 0.8
	const dx = e.clientX - initialMouseX.value
	// Under RTL the chat panel is visually on the right and the resizer sits
	// on its right edge, so a rightward drag shrinks it.
	const newWidth = initialPanelWidth.value + (isRtl.value ? -dx : dx)
	leftPanelWidth.value = Math.min(Math.max(newWidth, minWidth), maxWidth)
	// Trigger scroll to bottom during live resize to maintain scroll position
    safeScrollToBottom()
}

function stopResize() {
	isResizing.value = false
	document.removeEventListener('mousemove', handleResize)
	document.removeEventListener('mouseup', stopResize)
	document.body.style.userSelect = 'auto'
}

onUnmounted(() => {
	try { _webhookWs?.close() } catch {}
	if (_webhookReloadTimer) clearTimeout(_webhookReloadTimer)
	if (nowTickHandle != null) { clearInterval(nowTickHandle); nowTickHandle = null }
	if (import.meta.client) {
		window.removeEventListener('resize', checkMobile)
	}
	window.removeEventListener('message', handleOfficeJsResult)
	document.removeEventListener('mousemove', handleResize)
	document.removeEventListener('mouseup', stopResize)
	document.body.style.userSelect = 'auto'
    window.removeEventListener('resize', safeScrollToBottom)
	try { scrollContainer.value?.removeEventListener('scroll', onScroll) } catch {}
	// Cancel any pending animation frame for scroll
	if (scrollRAF !== null && typeof window !== 'undefined') {
		window.cancelAnimationFrame(scrollRAF)
	}
	// Stop any polling timers
	clearStreamWatchdog()
	stopPollingInProgressCompletion()
	stopScheduledCompletionsPoll()
	markdownAutoDir.value?.stop()
	// Clear reasoning refs
	reasoningRefs.value.clear()
})


// Handle Add to dashboard from ToolWidgetPreview
async function handleAddWidgetFromPreview(payload: { widget?: any, step?: any, visualization?: any }) {
    try {
        const viz = payload?.visualization
        const widget = payload?.widget
        if (viz?.id) {
            const block = { type: 'visualization', visualization_id: viz.id, x: 0, y: 0, width: 6, height: 7 }
            await useMyFetch(`/api/reports/${report_id}/layouts/active/blocks`, { method: 'PATCH', body: { blocks: [block] } })
        } else if (widget?.id) {
            const block = { type: 'widget', widget_id: widget.id, x: 0, y: 0, width: 6, height: 7 }
            await useMyFetch(`/api/reports/${report_id}/layouts/active/blocks`, { method: 'PATCH', body: { blocks: [block] } })
        } else {
            return
        }
        
        // Update the local widget status immediately to reflect the change in UI
        // Find the tool execution that contains this widget and update its status
        messages.value.forEach(message => {
            if (message.completion_blocks) {
                message.completion_blocks.forEach(block => {
                    if (viz?.id && (block.tool_execution as any)?.created_visualizations) {
                        const list = (block.tool_execution as any).created_visualizations as any[]
                        const found = list.find(v => v?.id === viz.id)
                        if (found) found.status = 'published'
                    }
                    if (widget?.id && block.tool_execution?.created_widget?.id === widget.id && block.tool_execution) {
                        block.tool_execution.created_widget.status = 'published'
                    }
                })
            }
        })
        
        		if (!isSplitScreen.value) toggleSplitScreen()
		await loadVisualizations()
        // Ask dashboard to refresh layout immediately so item appears
        try {
            const dash = dashboardRef.value
            if (dash && typeof dash.refreshLayout === 'function') await dash.refreshLayout()
        } catch {}
		// Scroll to bottom when dashboard opens after adding widget
		await nextTick()
        safeScrollToBottom()
    } catch (e) {
        console.error('Failed to add widget from preview:', e)
    }
}

// Handle opening an artifact from CreateArtifactTool
function handleOpenArtifact(payload: { artifactId?: string; loading?: boolean }) {
	// Switch to artifact view and ensure split screen is open
	if (!isSplitScreen.value) toggleSplitScreen()
	// Switch to artifact panel
	rightPanelView.value = 'artifact'
	// If artifactId provided, dispatch event to ArtifactFrame to select this artifact
	// If loading is true, just open the pane - ArtifactFrame will show loading state
	// and artifact:created event will trigger selection when ready
	if (payload.artifactId) {
		try {
			window.dispatchEvent(new CustomEvent('artifact:select', {
				detail: { artifact_id: payload.artifactId }
			}))
		} catch {}
	}
}

function abortStream() {
	clearStreamWatchdog()
	if (currentController) {
		currentController.abort()
		currentController = null
	}
	// Signal backend to stop the running agent loop if we know the server-side id
	try {
					const sysMsg = [...messages.value].reverse().find(m => m.role === 'system' && m.status === 'in_progress')
		const systemId = (sysMsg as any)?.system_completion_id
		if (systemId) {
			useMyFetch(`/api/completions/${systemId}/sigkill`, { method: 'POST' })
			// Mark locally as stopped for immediate UI feedback
			const msgIndex = messages.value.findIndex(m => m.id === sysMsg?.id)
			if (msgIndex !== -1) {
				// Force Vue reactivity by replacing the entire array
				const newMessages = [...messages.value]
				const updatedMessage = { ...newMessages[msgIndex], status: 'stopped' as ChatStatus }
				
				// Also update all completion blocks and their tool executions to stopped status
				if (updatedMessage.completion_blocks) {
					updatedMessage.completion_blocks = updatedMessage.completion_blocks.map(block => ({
						...block,
						status: block.status === 'in_progress' ? 'stopped' as ChatStatus : block.status,
						completed_at: block.completed_at || new Date().toISOString(),
						tool_execution: block.tool_execution?.status === 'running' ? { ...block.tool_execution, status: 'stopped' } : block.tool_execution
					}))
				}
				
				newMessages[msgIndex] = updatedMessage
				messages.value = newMessages
				
				// Force a nextTick update
				nextTick(() => {
				})
			}
		}
	} catch (e) {
		console.error('Failed to send sigkill:', e)
	}
	isStreaming.value = false
	isCompletionInProgress.value = false
}

function openTraceModal(completionId: string) {
	selectedCompletionForTrace.value = completionId
	showTraceModal.value = true
}

function handleExampleClick(starter: string) {
	if (starter) {
		onSubmitCompletion({ text: starter, mentions: [], mode: currentPromptMode.value });
	}
}

// Fetch 3-4 suggested follow-up questions for a finished system message.
// Fail-soft: any error/flag-off just clears loading and shows nothing.
async function fetchFollowups(m: any) {
	try {
		if (!m || m.role !== 'system') return
		if (m.status !== 'success') return
		if ((report.value as any)?.mode === 'training') return
		// Already loaded or in-flight → skip.
		if (Array.isArray(m.followups) || m.followups_loading) return
		if (!report.value?.id) return

		// Derive the rendered answer text: walk completion_blocks from the end,
		// fall back to cache-served completion.content (0-block answers).
		let answer_text = ''
		const blocks = (m.completion_blocks || []).filter(
			(b: any) => b && b.phase !== 'knowledge_harness'
		)
		for (let i = blocks.length - 1; i >= 0; i--) {
			const b = blocks[i]
			if (String(b?.status || '').toLowerCase() === 'error') continue
			if (b?.tool_execution?.tool_name === 'clarify') continue
			const text = b?.content || b?.plan_decision?.final_answer || b?.plan_decision?.assistant
			if (text && String(text).trim()) { answer_text = String(text); break }
		}
		if (!answer_text && m?.completion?.content && String(m.completion.content).trim()) {
			answer_text = String(m.completion.content)
		}

		// Best-effort question text from the preceding user message (optional).
		let question_text = ''
		try {
			const idx = messages.value.findIndex((x: any) => x.id === m.id)
			for (let i = idx - 1; i >= 0; i--) {
				const um: any = messages.value[i]
				if (um?.role === 'user' && um?.prompt?.content) { question_text = String(um.prompt.content); break }
			}
		} catch { /* optional */ }

		m.followups_loading = true
		const { data, error } = await useMyFetch(`/reports/${report.value.id}/followups`, {
			method: 'POST',
			body: { answer_text, question_text }
		})
		const res: any = data.value
		if (error.value) {
			m.followups = []
		} else if (res?.disabled) {
			m.followups = []
		} else {
			m.followups = Array.isArray(res?.followups) ? res.followups : []
		}
	} catch {
		m.followups = []
	} finally {
		if (m) m.followups_loading = false
	}
}

// Handlers for feedback-triggered instruction suggestions
function handleSuggestionsLoading(message: ChatMessage) {
	message.instruction_suggestions_loading = true
}

function handleSuggestionsReceived(message: ChatMessage, suggestions: any[]) {
	message.instruction_suggestions_loading = false
	if (suggestions && suggestions.length > 0) {
		// Append new suggestions to existing ones (if any)
		if (!message.instruction_suggestions) {
			message.instruction_suggestions = []
		}
		message.instruction_suggestions.push(...suggestions)
	}
}

// State for QueryCodeEditorModal
const showQueryEditor = ref(false)
const queryEditorProps = ref<{
	queryId: string | null
	stepId: string | null
	initialCode: string
	title: string
}>({
	queryId: null,
	stepId: null,
	initialCode: '',
	title: ''
})

function handleEditQuery(payload: { queryId: string; stepId: string | null; initialCode: string; title: string }) {
	queryEditorProps.value = {
		queryId: payload.queryId,
		stepId: payload.stepId,
		initialCode: payload.initialCode,
		title: payload.title
	}
	showQueryEditor.value = true
}

function closeQueryEditor() {
	showQueryEditor.value = false
}

function onStepCreated(step: any) {
	// Handle step creation - could refresh the current view or update state
	console.log('Step created:', step)
	// Optionally refresh the completion or update the UI
}

function onSubmitCompletion(data: { text: string, mentions: any[]; mode?: string; model_id?: string; files?: { id: string; filename: string; content_type: string }[] }) {
	const text = data.text.trim()
	if (!text) return

	// Append user message with attached files (for immediate display)
	const userMsg: ChatMessage = {
		id: `user-${Date.now()}`,
		role: 'user',
		prompt: { content: text },
		files: data.files || [],
		created_at: new Date().toISOString()
	}
	messages.value.push(userMsg)

	// Optimistic auto-title (mirrors the backend stream hook): on the FIRST question,
	// set the header title + notify the rail so it updates instantly instead of after
	// a refresh. Backend persists the same value.
	try {
		if (messages.value.length === 1 && report.value) {
			const _ph = ['', 'untitled report', 'untitled_report', 'new report', 'untitled']
			if (_ph.includes(((report.value.title || '') as string).trim().toLowerCase())) {
				const _t = text.replace(/\s+/g, ' ').trim()
				report.value.title = _t.length > 60 ? _t.slice(0, 60) + '…' : _t
				window.dispatchEvent(new CustomEvent('report:titled', { detail: { id: report.value.id, title: report.value.title } }))
			}
		}
	} catch {}

	// Append placeholder system message for streaming
	const sysId = `system-${Date.now()}`
	const sysMsg: ChatMessage = {
		id: sysId,
		role: 'system',
		status: 'in_progress',
		completion_blocks: [],
		// Activity-tab step timeline (Claude-style). Populated additively by
		// reduceStepEvent() in handleStreamingEvent for every SSE event.
		steps: []
	} as any
	messages.value.push(sysMsg)
	scrollToBottom()

	// Stop any background polling and start streaming
	stopPollingInProgressCompletion()

	// Start streaming
	if (isStreaming.value) abortStream()
	currentController = new AbortController()
	isStreaming.value = true
	isCompletionInProgress.value = true

	const requestBody = {
		prompt: {
			content: text,
			mentions: data.mentions || [],
			mode: data.mode || 'chat',
			model_id: data.model_id || null,
			platform: isExcel.value ? 'excel' : null,
			platform_context: isExcel.value && excelSelection.value ? {
				address: excelSelection.value.address,
				sheetName: excelSelection.value.sheetName,
				selectionValues: excelSelection.value.selectionValues,
				cellCount: excelSelection.value.cellCount,
				totalCellCount: excelSelection.value.totalCellCount,
				truncated: excelSelection.value.truncated,
				rowCount: excelSelection.value.rowCount,
				columnCount: excelSelection.value.columnCount,
			} : null,
		},
		stream: true
	}

	startStreaming(requestBody, sysId)
}

async function startStreaming(requestBody: any, sysId: string) {

	try {
		const options: any = {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(requestBody),
			signal: currentController?.signal,
			stream: true
		}
		const raw: any = await useMyFetch(`/reports/${report_id}/completions`, options as any)
		const res: Response = (raw?.data?.value ?? raw?.data) as unknown as Response

		if (!res?.ok || !res?.body) throw new Error(`Stream HTTP error: ${res?.status}`)

		const reader = res.body!.getReader()
		const decoder = new TextDecoder()
		let buffer = ''
		let currentEvent: string | null = null

		const ensureSys = () => messages.value.findIndex(m => m.id === sysId)

		// Watchdog: arm now; reset on every received chunk. Fires if the stream stalls.
		armStreamWatchdog(sysId)
		// Tracks whether a terminal SSE event ([DONE]/completion.finished/completion.error)
		// was seen, so a silent stream close (done with no terminal) can be flagged.
		let sawTerminal = false

		while (true) {
			const { done, value } = await reader.read()
			if (done) {
				break
			}
			// Reset the stall watchdog on every chunk received from the stream.
			armStreamWatchdog(sysId)
			
			// Check if stream was aborted
			if (currentController?.signal.aborted) {
				break
			}
			
			buffer += decoder.decode(value, { stream: true })

			let nlIndex: number
			while ((nlIndex = buffer.indexOf('\n')) >= 0) {
				const line = buffer.slice(0, nlIndex).trimEnd()
				buffer = buffer.slice(nlIndex + 1)

				if (line.startsWith('event:')) {
					currentEvent = line.slice(6).trim()
				} else if (line.startsWith('data:')) {
					const dataStr = line.slice(5).trim()
					if (dataStr === '[DONE]') {
						sawTerminal = true
						clearStreamWatchdog()
						isStreaming.value = false
						currentController = null
						// Refresh report data and context estimate after stream fully ends
						loadReport()
						loadReportSummary()
						promptBoxRef.value?.refreshContextEstimate?.()
						return
					}
					try {
						const parsed = JSON.parse(dataStr)
						const payload = parsed.data ?? parsed
						if (currentEvent === 'completion.finished' || currentEvent === 'completion.error') {
							sawTerminal = true
						}
						const idx = ensureSys()
						if (idx !== -1) {
							await handleStreamingEvent(currentEvent, payload, idx)
							// Debounced scroll: batch multiple token events into a single frame
							if (!pendingScroll.value) {
								pendingScroll.value = true
								if (typeof window !== 'undefined') {
									scrollRAF = window.requestAnimationFrame(() => {
										autoScrollIfNearBottom()
										pendingScroll.value = false
									})
								} else {
									autoScrollIfNearBottom()
									pendingScroll.value = false
								}
							}
						}
					} catch (e) {
						// ignore non-JSON data lines
					}
				}
			}
		}
		// Stream closed (done) without a terminal event ([DONE]/completion.finished/
		// completion.error) — the run died silently mid-stream. Flag it so the spinner
		// can't hang. (User aborts set status away from in_progress, so they're no-ops.)
		if (!sawTerminal && !currentController?.signal.aborted) {
			failRunUnexpectedly(sysId)
		}
	} catch (err) {
		console.error('Streaming error:', err)
		const idx = messages.value.findIndex(m => m.id === sysId)
		if (idx !== -1) {
			let errorMessage = 'An error occurred during streaming.'
			
			if (err instanceof Error) {
				if (err.name === 'AbortError') {
					// Check if this was a user-initiated stop (sigkill) vs connection abort
					const sysMsg = messages.value[idx]
					// If the main analysis already left 'in_progress', the SSE stream was
					// only still open for the knowledge-harness tail. Aborting it on a new
					// user submit should not downgrade the result to "Generation stopped" —
					// preserve whatever status the user has already seen (success with
					// thumbs up, error, or an existing 'stopped').
					if (sysMsg && sysMsg.status && sysMsg.status !== 'in_progress') {
						return
					}
					if (sysMsg && sysMsg.system_completion_id) {
						// This was likely a user stop, mark as stopped without error
						messages.value[idx] = { ...messages.value[idx], status: 'stopped' }
						return // Don't add error block for user stops
					} else {
						// Connection was aborted for other reasons
						errorMessage = 'Stream was cancelled.'
						messages.value[idx] = { ...messages.value[idx], status: 'stopped' }
					}
				} else if (err.message.includes('Stream HTTP error')) {
					errorMessage = `Connection error: ${err.message}`
					messages.value[idx] = { ...messages.value[idx], status: 'error' }
				} else {
					errorMessage = `Error: ${err.message}`
					messages.value[idx] = { ...messages.value[idx], status: 'error' }
				}
			} else {
				messages.value[idx] = { ...messages.value[idx], status: 'error' }
			}
			
			// Add error block if not already present
			if (!messages.value[idx].completion_blocks?.some(b => b.status === 'error')) {
				if (!messages.value[idx].completion_blocks) {
					messages.value[idx].completion_blocks = []
				}
				messages.value[idx].completion_blocks!.push({
					id: `error-${Date.now()}`,
					block_index: 999,
					status: 'error',
					content: errorMessage,
					title: 'Error',
					icon: '❌'
				})
			}
		}
	} finally {
		clearStreamWatchdog()
		isStreaming.value = false
		isCompletionInProgress.value = false
		currentController = null
	}
}

// Run is paused waiting for the user to answer a clarify question: the LAST
// message carries an (unanswered) clarify block and nothing is streaming.
// Used to swap the fake "Loading…/follow-ups" spinners for a calm paused chip.
const awaitingClarify = computed<boolean>(() => {
	const last = messages.value[messages.value.length - 1]
	return !!last && !isStreaming.value && hasClarifyBlock(last)
})

// === Minimal polling for refresh resume (no SSE resume) ===
const isPolling = ref<boolean>(false)
const pollIntervalMs = 1200
let pollHandle: number | null = null

function getLastInProgressSystem(): ChatMessage | undefined {
	return [...messages.value].reverse().find(m => m.role === 'system' && m.status === 'in_progress')
}

function stopPollingInProgressCompletion() {
	if (pollHandle !== null) {
		clearTimeout(pollHandle)
		pollHandle = null
	}
	isPolling.value = false
}

async function startPollingInProgressCompletion() {
	if (isStreaming.value || isPolling.value) return
	const sys = getLastInProgressSystem()
	if (!sys) return

	isPolling.value = true
	const startTs = Date.now()
	const maxDurationMs = 2 * 60 * 1000

	const tick = async () => {
		// If SSE streaming has (re)started, stop polling — SSE is the source of truth
		// and loadCompletions would wipe in-memory stream state.
		if (isStreaming.value) {
			stopPollingInProgressCompletion()
			return
		}
		try {
			await loadCompletions({ skipEstimate: true })
			autoScrollIfNearBottom()
			const still = getLastInProgressSystem()
			if (!still) {
				stopPollingInProgressCompletion()
				promptBoxRef.value?.refreshContextEstimate?.()
				return
			}
			if (Date.now() - startTs > maxDurationMs) {
				stopPollingInProgressCompletion()
				return
			}
			// Schedule next tick only if we should continue polling
			pollHandle = window.setTimeout(tick, pollIntervalMs)
		} catch (e) {
			// keep polling on transient errors
			pollHandle = window.setTimeout(tick, pollIntervalMs)
		}
	}

	pollHandle = window.setTimeout(tick, pollIntervalMs)
}

// === Background poll to detect new scheduled completions ===
let scheduledPollHandle: number | null = null
const scheduledPollIntervalMs = 15_000

function startScheduledCompletionsPoll() {
	if (scheduledPollHandle !== null) return
	// Only poll if this report actually has scheduled prompts that can fire in the background
	if (!scheduledPrompts.value || scheduledPrompts.value.length === 0) return
	const tick = async () => {
		// Skip while streaming (SSE is authoritative) or while tab is hidden
		if (isStreaming.value || (typeof document !== 'undefined' && document.hidden)) {
			scheduledPollHandle = window.setTimeout(tick, scheduledPollIntervalMs)
			return
		}
		try {
			const lastId = messages.value.length > 0 ? messages.value[messages.value.length - 1].id : null
			const { data } = await useMyFetch(`/reports/${report_id}/completions?limit=${pageLimit}`)
			const response = data.value as any
			const list: any[] = response?.completions || []
			const newLastId = list.length > 0 ? list[list.length - 1].id : null
			if (newLastId && newLastId !== lastId) {
				await loadCompletions()
				autoScrollIfNearBottom()
			}
		} catch {}
		scheduledPollHandle = window.setTimeout(tick, scheduledPollIntervalMs)
	}
	scheduledPollHandle = window.setTimeout(tick, scheduledPollIntervalMs)
}

function stopScheduledCompletionsPoll() {
	if (scheduledPollHandle !== null) {
		clearTimeout(scheduledPollHandle)
		scheduledPollHandle = null
	}
}

onMounted(async () => {
	// Load report metadata first (fast), then open sidebar based on counts
	// loadCompletions is slow (~30s) so don't block sidebar on it
	const fastLoads = Promise.all([
		loadReport(),
		loadVisualizations(),
		checkHasArtifacts(),
		loadActiveLayoutHasBlocks(),
		loadScheduledPrompts(),
		loadReportSummary(),
		loadReportInstructions(),
		loadSessionSummary()
	])
	const slowLoads = loadCompletions()
	connectWebhookSocket()

	await fastLoads

	// Auto-open right pane based on report metadata (available immediately from loadReport)
	// Skip auto-open in Excel mode — the taskpane is too narrow for split screen
	if (!isExcel.value) {
		if (hasArtifacts.value || hasLegacyLayout.value || (report.value as any)?.artifact_count > 0) {
			isSplitScreen.value = true
			rightPanelView.value = 'artifact'
			leftPanelWidth.value = Math.round(window.innerWidth * 0.37)
			collapseSidebar()
		} else if ((report.value as any)?.query_count > 0 || (report.value as any)?.instruction_count > 0 || (report.value as any)?.has_scheduled_prompts) {
			isSplitScreen.value = true
			rightPanelView.value = 'summary'
			leftPanelWidth.value = Math.round(window.innerWidth * 0.55)
		}
	}

	// Dashboard-first layout entry point (URL ?focus=dashboard). Runs AFTER the
	// auto-open block so it owns the final layout. Sets userPinnedView so the
	// auto-pilot watchers don't flip away from the dashboard. Falls back to the
	// existing full-screen dashboard tab on mobile.
	if (route.query.focus === 'dashboard' && !isExcel.value) {
		if (isMobile.value) {
			mobileView.value = 'dashboard'
		} else {
			dashboardFirst.value = true
			userPinnedView.value = true
			if (!isSplitScreen.value) toggleSplitScreen()
			setPanelView('artifact', true)
		}
	}

	// Slides-first layout (URL ?focus=slides) — presentation on the big main
	// panel with the chat docked on the right. Reuses the dashboard-first flip,
	// just pointing the main panel at the slides view instead of the dashboard.
	if (route.query.focus === 'slides' && !isExcel.value) {
		if (isMobile.value) {
			mobileView.value = 'dashboard'
		} else {
			dashboardFirst.value = true
			slidesFocus.value = true
			dockCollapsed.value = false
			userPinnedView.value = true
			if (!isSplitScreen.value) toggleSplitScreen()
			setPanelView('slides', true)
		}
	}

	await slowLoads

	// Handle new_message query parameter after everything is loaded
	if (route.query.new_message && messages.value.length == 0) {
		let mentions: any[] = []
		try {
			const raw = typeof route.query.mentions === 'string' ? decodeURIComponent(route.query.mentions) : ''
			if (raw) mentions = JSON.parse(raw)
		} catch {}
		const mode = typeof route.query.mode === 'string' ? route.query.mode : 'chat'
		const model_id = typeof route.query.model_id === 'string' ? route.query.model_id : null
		onSubmitCompletion({ text: route.query.new_message as string, mentions, mode, model_id: model_id || undefined })
	} else if (route.query.prompt && messages.value.length == 0) {
		// Pre-fill the prompt box without submitting (e.g. a training session draft).
		prefillText.value = route.query.prompt as string
	}

	// If a system message is still in progress (after refresh), begin polling until it finishes
	if (!isStreaming.value && getLastInProgressSystem()) {
		startPollingInProgressCompletion()
	}

	// Start background poll for new scheduled completions
	startScheduledCompletionsPoll()
	
    // Aggressive initial scroll to handle async content mounting
	scheduleInitialScroll()
    window.addEventListener('resize', safeScrollToBottom)
	// Attach scroll listener for infinite scroll up
	try { scrollContainer.value?.addEventListener('scroll', onScroll) } catch {}
    // Initialize scroll position state
    try {
        const c = scrollContainer.value
        if (c) {
            lastScrollTop.value = c.scrollTop
            const dist = c.scrollHeight - (c.scrollTop + c.clientHeight)
            isUserAtBottom.value = dist <= RETURN_TO_BOTTOM_PX
            suppressAutoScroll.value = false
        }
    } catch {}
})

</script>

<style scoped>
.overflow-y-auto {
	overflow-y: auto !important;
}

/* Phase 2 — Claude-style step thread: a status dot + connector rail on each
   tool step so the thought process reads as a threaded activity log. Cosmetic
   only; applied to tool_execution blocks via :class in the template. */
.cc-step {
	position: relative;
	padding-inline-start: 20px;
	margin-top: 2px;
}
.cc-step::before {            /* connector rail */
	content: "";
	position: absolute;
	inset-inline-start: 5px;
	top: 15px;
	bottom: -2px;
	width: 1.5px;
	background: #E9E0D3;
}
.cc-step::after {             /* status dot (pending) */
	content: "";
	position: absolute;
	inset-inline-start: 0;
	top: 3px;
	width: 11px;
	height: 11px;
	border-radius: 9999px;
	background: #FBFAF6;
	border: 1.5px solid #E0DACD;
	box-sizing: border-box;
}
.cc-step--done::after {      /* success = green */
	background: #3F7A4F;
	border-color: #3F7A4F;
}
.cc-step--err::after {       /* error/recovered = amber */
	background: #C08A2D;
	border-color: #C08A2D;
}

/* Running "wave · what's happening · wave" indicator (Claude-style). */
.cai-wave { width: 42px; height: 20px; display: inline-block; flex: none; }
.cai-wave svg { width: 100%; height: 100%; display: block; overflow: visible; }
.cai-wave.cai-flip { transform: scaleX(-1); }
.cai-wave .wv { fill: none; stroke-width: 2.6; stroke-linecap: round; transform-origin: center; }
.cai-wave .wv1 { animation: caiWob 1.3s ease-in-out infinite; }
.cai-wave .wv2 { animation: caiWob 1.3s ease-in-out infinite 0.32s; }
/* taller pulse so it reads as a live wave, not a flat dash */
@keyframes caiWob { 0%, 100% { transform: scaleY(0.35); } 50% { transform: scaleY(1.15); } }
@media (prefers-reduced-motion: reduce) { .cai-wave .wv { animation: none; transform: scaleY(0.85); } }

/* Phase 3 — shimmer the "Working · 0:42" header text while the run streams. */
@keyframes ccShimmer { 0% { background-position: -120% 0; } 100% { background-position: 120% 0; } }
.cc-shimmer {
	background: linear-gradient(90deg, #9a948a 0%, #9a948a 35%, #d8d0c4 50%, #9a948a 65%, #9a948a 100%);
	background-size: 200% 100%;
	-webkit-background-clip: text;
	background-clip: text;
	color: transparent;
	animation: ccShimmer 1.8s linear infinite;
}

/* Phase 4 — tables + dividers in the hero answer (e.g. the Key Metrics table in
   the financial summary). Clean hairline grid, warm header. */
.markdown-wrapper :deep(.markdown-content) table {
	width: 100%;
	border-collapse: collapse;
	margin: 8px 0 16px;
	font-size: 13.5px;
}
.markdown-wrapper :deep(.markdown-content) th,
.markdown-wrapper :deep(.markdown-content) td {
	border: 1px solid #EFEAE1;
	padding: 8px 11px;
	text-align: start;
	unicode-bidi: plaintext;
}
.markdown-wrapper :deep(.markdown-content) th {
	background: #FAF7F1;
	font-weight: 600;
	color: #6b6357;
}
.markdown-wrapper :deep(.markdown-content) td:first-child { font-weight: 600; }
.markdown-wrapper :deep(.markdown-content) hr {
	border: none;
	border-top: 1px solid #E9E0D3;
	margin: 18px 0;
}

/* FIX 1: hide the horizontal scrollbar on the right-panel tab group while
   keeping it scrollable when the panel is narrow. */
.no-scrollbar {
	-ms-overflow-style: none; /* IE/Edge */
	scrollbar-width: none; /* Firefox */
}
.no-scrollbar::-webkit-scrollbar {
	display: none; /* Chrome/Safari */
}

/* Merged-Activity collapsibles: hide native marker + rotate chevron when open. */
details > summary {
	list-style: none;
}
details > summary::-webkit-details-marker {
	display: none;
}
.chev {
	transition: transform 0.15s;
}
details[open] > summary .chev {
	transform: rotate(90deg);
}

/* Icon-only tab tooltip — dark pill below the icon, instant fade, no reflow. */
.tabico .ttip {
	position: absolute;
	top: calc(100% + 7px);
	left: 50%;
	transform: translateX(-50%) translateY(-3px);
	background: #1F2937;
	color: #fff;
	font-size: 10px;
	font-weight: 500;
	letter-spacing: .2px;
	padding: 3px 8px;
	border-radius: 7px;
	white-space: nowrap;
	z-index: 50;
	opacity: 0;
	pointer-events: none;
	transition: opacity .12s ease, transform .12s ease;
	box-shadow: 0 4px 12px rgba(0,0,0,.18);
}
.tabico .ttip::before {
	content: "";
	position: absolute;
	bottom: 100%;
	left: 50%;
	transform: translateX(-50%);
	border: 4px solid transparent;
	border-bottom-color: #1F2937;
}
.tabico:hover .ttip {
	opacity: 1;
	transform: translateX(-50%) translateY(0);
}

/* Thinking box - collapsible reasoning */
.thinking-box {
	margin-bottom: 4px;
}

.thinking-header {
	display: flex;
	align-items: center;
	cursor: pointer;
	font-size: 12px;
	font-weight: 400;
	color: #6b7280;
	user-select: none;
}

.thinking-header:hover {
	color: #374151;
}

.thinking-content {
	padding-block: 4px;
	padding-inline-start: 10px;
	padding-inline-end: 0;
	margin-top: 2px;
	margin-bottom: 4px;
	border-inline-start: 1px dashed #e5e7eb;
	font-size: 12px !important;
	line-height: 1.4;
	color: #6b7280;
}

.thinking-content :deep(*) {
	font-size: 12px !important;
	line-height: 1.4 !important;
}

.thinking-content :deep(.markdown-content) {
	font-size: 12px !important;
	line-height: 1.4 !important;
}

.thinking-content :deep(p) {
	font-size: 12px !important;
	margin: 0;
}

/* Tool execution - clear visual separation */
.tool-execution-container {
	margin: 8px 0;
}

/* Block content - assistant messages */
.block-content {
	margin-bottom: 4px;
	font-size: 13px;
}

/* Phase 4 — answer reads as the hero: larger, calmer line-height, serif
   headings + strong emphasis. Cosmetic; the small reasoning/thinking prose
   keeps its own .thinking-content sizing above. */
.markdown-wrapper :deep(.markdown-content) {
	@apply leading-relaxed;
	font-size: 15px;
	line-height: 1.7;
	color: #1f1d1a;
	/* Prevent layout thrashing during streaming */
	contain: content;
	content-visibility: auto;

	/* Paragraph spacing to match streaming text appearance */
	p {
		margin-bottom: 1em;
		unicode-bidi: plaintext;
	}
	p:last-child {
		margin-bottom: 0;
	}

	:where(h1, h2, h3, h4, h5, h6) {
		@apply font-bold mb-3 mt-6;
		font-family: 'Spectral', ui-serif, Georgia, serif;
		letter-spacing: -0.01em;
		unicode-bidi: plaintext;
	}

	h1 { @apply text-2xl; }
	h2 { @apply text-xl; }
	h3 { @apply text-lg; }

	/* Bold lead-ins pop a touch more than body weight. */
	strong, b { font-weight: 700; color: #15130f; }

	ul, ol { @apply ps-6 mb-4; unicode-bidi: plaintext; }
	ul { @apply list-disc; }
	ol { @apply list-decimal; }
	li { @apply mb-1.5; unicode-bidi: plaintext; }
	li > p:only-child,
	li > p:last-child { margin-bottom: 0; }

	/* Code blocks (fenced with ```) — always LTR regardless of surrounding direction */
	pre {
		@apply bg-gray-50 p-4 rounded-lg mb-4 overflow-x-auto;
		white-space: pre-wrap;
		word-wrap: break-word;
		direction: ltr;
		unicode-bidi: isolate;
		text-align: left;
	}
	pre code {
		/* Reset inline code styles for code blocks */
		background: none;
		padding: 0;
		border-radius: 0;
		font-size: 13px;
		line-height: 1.5;
		display: block;
		white-space: pre-wrap;
		word-wrap: break-word;
	}
	/* Inline code (single backticks) */
	code {
		@apply bg-gray-100 px-1.5 py-0.5 rounded font-mono;
		font-size: 12px;
		color: #374151;
		unicode-bidi: isolate;
		direction: ltr;
	}
	a { 
		@apply text-gray-900 no-underline relative;
		transition: color 0.15s ease;
	}
	a:hover {
		@apply text-gray-700;
	}
	a::before {
		content: '';
		position: absolute;
		left: -18px;
		top: 50%;
		transform: translateY(-50%);
		width: 14px;
		height: 14px;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke-width='1.5' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25'/%3E%3C/svg%3E");
		background-size: contain;
		background-repeat: no-repeat;
		opacity: 0;
		transition: opacity 0.15s ease;
	}
	a:hover::before {
		opacity: 1;
	}
	blockquote { @apply border-l-4 border-gray-200 pl-4 italic my-4; unicode-bidi: plaintext; }
	table { @apply w-full border-collapse mb-4; unicode-bidi: plaintext; }
	table th, table td { @apply border border-gray-200 p-2 text-xs bg-white; unicode-bidi: plaintext; }
}



/* Compact mode (Excel add-in) — smaller text throughout */
.compact-messages .block-content {
	font-size: 13px;
}
.compact-messages .markdown-wrapper :deep(.markdown-content) {
	font-size: 13px;
}
.compact-messages .markdown-wrapper :deep(.markdown-content pre code) {
	font-size: 12px;
}
.compact-messages .markdown-wrapper :deep(.markdown-content code) {
	font-size: 12px;
}
.compact-messages .thinking-header {
	font-size: 11px;
}
.compact-messages .thinking-content,
.compact-messages .thinking-content :deep(*),
.compact-messages .thinking-content :deep(.markdown-content),
.compact-messages .thinking-content :deep(p) {
	font-size: 11px !important;
}
.compact-messages li {
	font-size: 13px;
}

@keyframes simple-ellipsis { 0% { content: '.'; } 33% { content: '..'; } 66% { content: '...'; } }
.simple-dots::after { content: '.'; display: inline-block; margin-top: 5px; animation: simple-ellipsis 1.5s infinite; font-weight: 400; font-size: 14px; color: #888; }

@keyframes shimmer {
	0% { background-position: -100% 0; }
	100% { background-position: 100% 0; }
}

@keyframes ellipsis {
	0% { content: 'Thinking.'; }
	33% { content: 'Thinking..'; }
	66% { content: 'Thinking...'; }
}

.dots::after {
	content: 'Thinking...';
	display: inline-block;
	background: linear-gradient(90deg, #888 0%, #999 25%, #ccc 50%, #999 75%, #888 100%);
	background-size: 200% 100%;
	-webkit-background-clip: text;
	background-clip: text;
	color: transparent;
	animation: shimmer 2s linear infinite, ellipsis 1s infinite;
	font-weight: 400;
	font-size: 12px;
	opacity: 1;
}

/* Add fade transitions */
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}

.fade-in {
    animation: fadeIn 0.6s ease-in;
}

@keyframes fadeIn {
    0% {
        opacity: 0;
        transform: translateY(10px);
    }
    100% {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Minimal shimmer for reconnect banner */
.poll-shimmer {
	background: linear-gradient(90deg, #888 0%, #999 25%, #ccc 50%, #999 75%, #888 100%);
	background-size: 200% 100%;
	-webkit-background-clip: text;
	background-clip: text;
	color: transparent;
	animation: shimmer 2s linear infinite;
	font-weight: 400;
	opacity: 1;
}

/* =========================================================================
   DASHBOARD-FIRST NARROW CHAT DOCK (.dash-dock)
   Gated ONLY when dashboardFirst is active. Makes the ~360px dock content
   fit/wrap so the dock never scrolls left-right or clips text. All rules
   scoped under .dash-dock so chat-first (no ?focus=dashboard) is unchanged.
   Child message content is rendered by child components -> use :deep().
   ========================================================================= */

/* the whole chat pane + every descendant may shrink; never force horizontal
   scroll. Applies in BOTH the dashboard-first dock AND the chat-first split
   view so content always reflows to the panel width. */
.chat-pane,
.chat-pane :deep(*) {
	min-width: 0;
}
.chat-pane {
	overflow-x: hidden;
}

/* long words / URLs break instead of widening the pane */
.chat-pane :deep(p),
.chat-pane :deep(li),
.chat-pane :deep(a),
.chat-pane :deep(span),
.chat-pane :deep(.markdown-content),
.chat-pane :deep(.block-content),
.chat-pane :deep(code) {
	overflow-wrap: anywhere;
	word-break: break-word;
}

/* TABLES scroll inside their OWN block, never the pane */
.chat-pane :deep(table) {
	display: block;
	width: max-content;
	max-width: 100%;
	overflow-x: auto;
}

/* neutralize any fixed min-width on composer / message containers that
   would exceed the pane width */
.chat-pane :deep([class*="min-w-["]) {
	min-width: 0 !important;
}

/* dock header report title: ReportHeader's <h1> is a fixed w-[500px] which is
   wider than the dock -> force it to flex/shrink + truncate (ellipsis). */
.dash-dock :deep(header h1) {
	width: auto !important;
	min-width: 0;
	flex: 1 1 auto;
	overflow: hidden;
	white-space: nowrap;
	text-overflow: ellipsis;
}
.dash-dock :deep(header h1 input) {
	text-overflow: ellipsis;
}

/* follow-up chips stack vertically in the narrow dock, each chip auto-fits its
   text (left-aligned), capped at the column width and wrapping long questions
   onto multiple lines so nothing is ever clipped. */
.chat-pane :deep(.dock-followups) {
	flex-direction: column;
	align-items: flex-start;
}
.chat-pane :deep(.dock-followups > button) {
	width: auto;
	max-width: 100%;
	text-align: start;
	white-space: normal;
	overflow-wrap: anywhere;
	line-height: 1.35;
	border-radius: 14px;
}
</style>



