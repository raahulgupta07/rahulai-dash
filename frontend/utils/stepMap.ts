// stepMap.ts — pure helpers that turn raw agent stream events into a timeline
// of AgentStep objects for <AgentStepTimeline>. Shared contract — do not change
// the AgentStep shape or the exported function names/signatures without syncing
// the reducer + timeline agents.
//
// REACTIVITY CONTRACT: reduceStepEvent MUTATES the passed `steps` array IN PLACE
// (push / patch existing objects) and returns the SAME array reference. Pass a
// Vue `reactive([])` (or a `ref([]).value`) so per-object patches stay reactive.
// On any error it returns the original array untouched and never throws.

export interface PlanTask {
  title: string
  // 'pending' | 'done' | 'run' (the backend emits pending|done; 'run' is a
  // client-derived state for the currently-active task).
  status: string
}

export interface AgentStep {
  id: string
  kind: 'think' | 'tool' | 'retry' | 'warn' | 'subagent' | 'plan'
  // Plan steps (kind:'plan') carry the agent's up-front numbered task list.
  // Absent on every other kind. Optional so the shape stays backward-compatible.
  tasks?: PlanTask[]
  icon: string // heroicon name e.g. 'heroicons:play'
  title: string // e.g. 'Ran SQL query'
  badge: string // e.g. 'run_query' (tool name / event)
  status: 'run' | 'done' | 'warn' | 'err'
  durationMs?: number
  body?: { code?: string; output?: string; text?: string }
  ts: number
  // Recovery metadata (set by blocksToSteps). When a step's tool_execution
  // errored but the run ultimately recovered/progressed, status is 'warn' and
  // these describe the amber "retried / self-fixed" treatment + the raw error
  // text to collapse behind a "show detail" toggle.
  recovered?: boolean
  recoveredLabel?: string // 'retried' | 'self-fixed'
  errorDetail?: string // the raw red error text (hidden by default)
  // Narration (FIX 3): the model's own plain-language reasoning for this step,
  // lifted from `block.plan_decision.reasoning` when present. Trimmed to a short
  // one-liner for the Activity panel. Empty/absent → render falls back to the
  // terse title (never fabricated).
  why?: string
}

interface PrettyTool {
  icon: string
  title: string
}

const TOOL_MAP: Record<string, PrettyTool> = {
  run_query: { icon: 'heroicons:play', title: 'Ran SQL query' },
  execute_query: { icon: 'heroicons:play', title: 'Ran SQL query' },
  create_data: { icon: 'heroicons:table-cells', title: 'Built dataset' },
  create_viz: { icon: 'heroicons:chart-bar-square', title: 'Built chart' },
  create_widget: { icon: 'heroicons:chart-bar-square', title: 'Built chart' },
  create_artifact: { icon: 'heroicons:rectangle-group', title: 'Built artifact' },
  search_tables: { icon: 'heroicons:magnifying-glass', title: 'Searched schema' },
  search_schema: { icon: 'heroicons:magnifying-glass', title: 'Searched schema' },
  load_skill: { icon: 'heroicons:puzzle-piece', title: 'Loaded skill' },
  run_skill_file: { icon: 'heroicons:puzzle-piece', title: 'Ran skill' },
  resolve_metric: { icon: 'heroicons:calculator', title: 'Resolved metric' },
  build_data_asset: { icon: 'heroicons:cube', title: 'Built data asset' },
  remember: { icon: 'heroicons:cpu-chip', title: 'Memory' },
  recall: { icon: 'heroicons:cpu-chip', title: 'Memory' },
  memory: { icon: 'heroicons:cpu-chip', title: 'Memory' },
  delegate_subtask: { icon: 'heroicons:rectangle-stack', title: 'Sub-agent' },
  clarify: { icon: 'heroicons:chat-bubble-left-right', title: 'Asked for clarification' },
  done: { icon: 'heroicons:check-circle', title: 'Finished' },
}

function titleCase(name: string): string {
  return String(name || '')
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Map a known tool name to a {icon, title}. Unknown names fall back to a
 * generic wrench icon + title-cased name.
 */
export function prettyTool(name: string): PrettyTool {
  const key = String(name || '').toLowerCase()
  if (TOOL_MAP[key]) return { ...TOOL_MAP[key] }
  return { icon: 'heroicons:wrench-screwdriver', title: titleCase(name) || 'Tool' }
}

function safeGet<T>(fn: () => T): T | undefined {
  try {
    return fn()
  } catch {
    return undefined
  }
}

// ----- Recovered-error classification (FIX 2C) -------------------------------
// The backend now auto-retries transient LLM/network blips and self-heals the
// "unsafe_python" security block (it re-runs without the forbidden call). When
// that happens the agent ultimately PROGRESSES, so an errored attempt should
// read as amber "retried / self-fixed", NOT an alarming red wall. Red is kept
// only for a FINAL failure with no recovery.

const RECOVERABLE_PATTERNS: { test: RegExp; label: string; friendly: string }[] = [
  {
    // LLM v2 streaming / connection blips → retried
    test: /llm v2 streaming failed|connection error|stream(ing)? failed|read timed out|timeout/i,
    label: 'retried',
    friendly: 'Network hiccup to the model — auto-retried.',
  },
  {
    // unsafe_python / forbidden construct (locals()/globals()/…) → self-fixed
    test: /security violation|unsafe_python|forbidden (function|construct)|locals\(\)|globals\(\)/i,
    label: 'self-fixed',
    friendly: 'Removed a disallowed construct and re-ran automatically.',
  },
  {
    // FIX E2: deliberate skip / reuse ("already exists … no need to re-run") is the
    // agent's NARRATION for not redoing work, NOT a failure → amber 'skipped', not red.
    test: /already (exist|present|created|available)|no need to (re-?run|recompute|regenerate)|skipp(ed|ing)|reus(e|ing)|nothing to do/i,
    label: 'skipped',
    friendly: 'Reused existing work — no need to re-run.',
  },
]

function errorText(te: any): string {
  return String(
    te?.error
    || te?.error_message
    || te?.result_summary
    || safeGet(() => te?.result_json?.error)
    || safeGet(() => {
      const errs = te?.result_json?.errors
      if (Array.isArray(errs) && errs.length) {
        const last = errs[errs.length - 1]
        return Array.isArray(last) ? last[1] : (last?.message || last)
      }
      return ''
    })
    || '',
  )
}

// Lift the model's plain-language reasoning for a block into a short one-liner
// (FIX 3 narration). Returns '' when no reasoning is present — callers must
// degrade gracefully to the step title, never fabricate.
function whyFromBlock(b: any, maxLen = 140): string {
  const raw = b?.plan_decision?.reasoning || b?.reasoning
  if (!raw || typeof raw !== 'string') return ''
  // Collapse whitespace + take the first sentence-ish chunk, capped.
  const flat = raw.replace(/\s+/g, ' ').trim()
  if (!flat) return ''
  return flat.length > maxLen ? `${flat.slice(0, maxLen - 1).trimEnd()}…` : flat
}

/** Match a known transient/recoverable error message → {label, friendly}. */
function matchRecoverable(text: string): { label: string; friendly: string } | null {
  const t = String(text || '')
  for (const p of RECOVERABLE_PATTERNS) {
    if (p.test.test(t)) return { label: p.label, friendly: p.friendly }
  }
  return null
}

/**
 * Fold a single stream event into the step list. MUTATES `steps` in place and
 * returns the same reference (see REACTIVITY CONTRACT at top). Never throws.
 */
export function reduceStepEvent(
  steps: AgentStep[],
  eventType: string,
  payload: any,
): AgentStep[] {
  try {
    const list = Array.isArray(steps) ? steps : []
    const p = payload || {}

    switch (eventType) {
      case 'tool.started': {
        const id = String(p.tool_id || p.id || `t${list.length}`)
        const toolName = String(p.tool_name || 'tool')
        const pretty = prettyTool(toolName)
        let title = pretty.title

        // Append a name/skill/task label for skill + sub-agent steps.
        if (
          title === 'Loaded skill' ||
          title === 'Ran skill' ||
          title === 'Sub-agent'
        ) {
          const args = p.arguments || {}
          const label = p.name || p.skill || p.task || args.name || args.skill || args.task
          if (label) title = `${title} · ${String(label)}`
        }

        const args = p.arguments || {}
        const code = args.sql || args.code
        const body = code ? { code: String(code) } : undefined

        list.push({
          id,
          kind: 'tool',
          icon: pretty.icon,
          title,
          badge: toolName,
          status: 'run',
          body,
          ts: Date.now(),
        })
        return list
      }

      case 'tool.progress': {
        const id = String(p.tool_id || p.id || '')
        const step = list.find((s) => s.id === id)
        if (step) {
          const code = safeGet(() => p.payload?.code) ?? p.code
          const output = safeGet(() => p.payload?.output) ?? p.stage
          if (code != null || output != null) {
            step.body = step.body || {}
            if (code != null) step.body.code = String(code)
            if (output != null) step.body.output = String(output)
          }
          step.status = 'run'
        }
        return list
      }

      case 'tool.finished': {
        const id = String(p.tool_id || p.id || '')
        const step = list.find((s) => s.id === id)
        if (step) {
          step.status = 'done'
          if (step.ts) step.durationMs = Math.max(0, Date.now() - step.ts)
          const output = safeGet(() => p.payload?.output) ?? p.output
          if (output != null) {
            step.body = step.body || {}
            step.body.output = String(output)
          }
        }
        return list
      }

      case 'planner.retry': {
        const reason = p.reason
        list.push({
          id: `retry${list.length}`,
          kind: 'retry',
          icon: 'heroicons:arrow-path',
          title: 'Retried' + (reason ? ` · ${String(reason)}` : ''),
          badge: 'planner.retry',
          status: 'warn',
          body: p.message || reason ? { text: String(p.message || reason) } : undefined,
          ts: Date.now(),
        })
        return list
      }

      case 'agent.warning': {
        list.push({
          id: `warn${list.length}`,
          kind: 'warn',
          icon: 'heroicons:exclamation-triangle',
          title: String(p.message || 'Warning'),
          badge: 'warning',
          status: 'warn',
          ts: Date.now(),
        })
        return list
      }

      case 'block.delta.token': {
        if (p.field === 'reasoning') {
          const last = list[list.length - 1]
          const liveThink = last && last.kind === 'think' && last.status === 'run'
          if (!liveThink) {
            list.push({
              id: `think${list.length}`,
              kind: 'think',
              icon: 'heroicons:cpu-chip',
              title: 'Reasoning…',
              badge: 'thinking',
              status: 'run',
              ts: Date.now(),
            })
          }
        }
        return list
      }

      default:
        return list
    }
  } catch {
    // Never break the stream on a malformed payload.
    return steps
  }
}

/**
 * Derive timeline steps from a system message's `completion_blocks` (the REAL
 * source of agent activity in this app — the page renders these directly).
 * One step per meaningful block: a tool execution, a reasoning pass, or a
 * final answer. Fully defensive — never throws, returns [] on any error.
 */
export function blocksToSteps(blocks: any[]): AgentStep[] {
  try {
    const out: AgentStep[] = []
    const list = Array.isArray(blocks) ? blocks : []

    // ---- Pass 0: did the run ultimately progress / succeed? --------------
    // The run is considered "recovered/progressed" if ANY block after the
    // current one is a successful tool, a written answer, or non-error
    // content. We compute, per index, whether progress happens LATER.
    const blockIsProgress = (b: any): boolean => {
      if (!b) return false
      const te = (b as any).tool_execution
      const teRaw = String(te?.status || '').toLowerCase()
      if (te && (teRaw === 'success' || teRaw === 'done' || teRaw === 'completed')) return true
      const content = (b as any).content
        || (b as any).plan_decision?.final_answer
        || (b as any).plan_decision?.assistant
      const bRaw = String((b as any).status || '').toLowerCase()
      // Non-errored content / answer = the run moved forward.
      if (content && bRaw !== 'error' && bRaw !== 'failed') return true
      return false
    }
    // progressAfter[i] === true when some block at index > i represents progress.
    const progressAfter: boolean[] = new Array(list.length).fill(false)
    for (let i = list.length - 1, seen = false; i >= 0; i--) {
      progressAfter[i] = seen
      if (blockIsProgress(list[i])) seen = true
    }
    // Did the overall run reach a final answer anywhere?
    const runReachedAnswer = list.some(
      (b: any) =>
        (b?.plan_decision?.analysis_complete === true && b?.content) ||
        ((b?.content || b?.plan_decision?.final_answer) &&
          String(b?.status || '').toLowerCase() !== 'error'),
    )

    for (let bi = 0; bi < list.length; bi++) {
      const b = list[bi]
      if (!b || (b as any).phase === 'knowledge_harness') continue
      // Plan blocks are surfaced separately via extractPlanTasks() — they are
      // NOT timeline tool/think steps, so skip them here (keeps the legacy
      // Activity step list byte-identical for runs that emit no plan).
      if ((b as any).source_type === 'plan') continue
      const te = (b as any).tool_execution
      if (te && te.tool_name) {
        const p = prettyTool(te.tool_name)
        const raw = String(te.status || '').toLowerCase()
        const isErr = raw === 'error' || raw === 'failed'
        const isStopped = raw === 'stopped'
        // A failed attempt is "recovered" when the run progressed after it OR
        // ultimately reached an answer — and especially when the error text is
        // a known transient/self-healing one.
        const detail = isErr ? errorText(te) : ''
        const recoverable = isErr ? matchRecoverable(detail) : null
        const progressed = progressAfter[bi] || runReachedAnswer
        const recovered = isErr && (progressed || !!recoverable)

        let status: AgentStep['status']
        if (raw === 'success' || raw === 'done' || raw === 'completed') status = 'done'
        else if (isStopped) status = 'warn'
        else if (isErr) status = recovered ? 'warn' : 'err'
        else status = 'run'

        // Serialized completion blocks carry `arguments_json`; the live step-map
        // event path carries `tool_arguments`. Read whichever is present so the
        // skill name + SQL are available in both renders.
        const targs = te.arguments_json || te.tool_arguments || {}
        let title = p.title
        const extra =
          targs?.name ||
          targs?.skill ||
          targs?.task ||
          te.created_widget?.title
        if (extra && (p.title === 'Loaded skill' || p.title === 'Ran skill' || p.title === 'Sub-agent')) {
          title = `${p.title} · ${extra}`
        }
        // Narration: the model's reasoning for this step (if it emitted any).
        // For a recovered step, prefer the friendly recovery note so the
        // narration honestly reflects the retry instead of hiding it.
        const why = recovered && recoverable?.friendly
          ? recoverable.friendly
          : whyFromBlock(b)

        // Sub-agent recursive-verify outcome (HYBRID_RECURSIVE). The
        // delegate_subtask tool returns `verified`/`attempts` in its output and
        // prefixes its observation summary with `[verified] ` / `[unverified] `.
        // Surface that as a recovery-style pill, REUSING recovered/recoveredLabel
        // (amber, like 'self-fixed'). Null-safe: undefined → no pill (flag OFF =
        // today's behavior). Only touches the subagent path.
        let verifyStatus: AgentStep['status'] | undefined
        let verifyRecovered = false
        let verifyLabel: string | undefined
        if (te.tool_name === 'delegate_subtask') {
          const vOut = safeGet(() => te.result_json) ?? {}
          let verified: boolean | undefined =
            typeof vOut?.verified === 'boolean' ? vOut.verified : undefined
          let attempts: number | undefined =
            typeof vOut?.attempts === 'number' ? vOut.attempts : undefined
          // Fall back to the observation summary prefix when the JSON fields
          // aren't present (attempts unknown in that case).
          if (verified === undefined) {
            const summary = String(te.result_summary || '')
            if (/^\s*\[verified\]/i.test(summary)) verified = true
            else if (/^\s*\[unverified\]/i.test(summary)) verified = false
          }
          if (verified === false) {
            // Finding still returned, just unverified → amber caution, not red.
            verifyStatus = 'warn'
            verifyLabel = 'unverified'
          } else if (verified === true && attempts !== undefined && attempts > 1) {
            // Verified only after a retry → amber 'verified' pill (like self-fixed).
            verifyRecovered = true
            verifyLabel = 'verified'
          }
          // verified-on-first-try (attempts == 1) → leave clean 'done'.
        }
        out.push({
          id: String(te.id || b.id || `b${out.length}`),
          kind: te.tool_name === 'delegate_subtask' ? 'subagent' : 'tool',
          icon: p.icon,
          title,
          badge: te.tool_name,
          // A subagent 'unverified' outcome downgrades a clean 'done' to 'warn'.
          status: verifyStatus ?? status,
          durationMs: typeof te.duration_ms === 'number' ? te.duration_ms : undefined,
          ...(why ? { why } : {}),
          body: {
            code: targs?.sql || targs?.code,
            output: te.result_summary,
          },
          ts: 0,
          ...(recovered
            ? {
                recovered: true,
                recoveredLabel: recoverable?.label || 'retried',
                errorDetail: recoverable?.friendly
                  ? `${recoverable.friendly}\n\n${detail}`.trim()
                  : detail,
              }
            : verifyRecovered
              ? { recovered: true, recoveredLabel: verifyLabel || 'verified' }
              : verifyLabel
                ? { recoveredLabel: verifyLabel }
                : isErr
                  ? { errorDetail: detail }
                  : {}),
        })
        continue
      }
      const reasoning = (b as any).plan_decision?.reasoning || (b as any).reasoning
      const content = (b as any).content || (b as any).plan_decision?.final_answer || (b as any).plan_decision?.assistant
      const complete = (b as any).plan_decision?.analysis_complete === true
      if (content && complete) {
        out.push({ id: String(b.id || `b${out.length}`), kind: 'think', icon: 'heroicons:pencil', title: 'Wrote answer', badge: 'answer', status: 'done', ts: 0 })
      } else if (reasoning) {
        const why = whyFromBlock(b)
        out.push({ id: String(b.id || `b${out.length}`), kind: 'think', icon: 'heroicons:cpu-chip', title: 'Reasoning', badge: 'thinking', status: content ? 'done' : 'run', ...(why ? { why } : {}), body: { text: typeof reasoning === 'string' ? reasoning.slice(0, 600) : undefined }, ts: 0 })
      }
    }
    return out
  } catch {
    return []
  }
}

/**
 * Surface the agent's up-front numbered PLAN from a system message's
 * `completion_blocks`. The backend emits a block with `source_type === 'plan'`
 * whose content is the JSON `{"tasks":[{"title":"…","status":"pending|done"}]}`.
 * Returns the tasks of the LAST plan block (the agent may re-emit a refined plan
 * mid-run). Fully defensive — `[]` on any error or when no plan block exists, so
 * callers fall back to the live step list. Never throws.
 */
export function extractPlanTasks(blocks: any[]): PlanTask[] {
  try {
    const list = Array.isArray(blocks) ? blocks : []
    for (let i = list.length - 1; i >= 0; i--) {
      const b = list[i]
      if (!b || (b as any).source_type !== 'plan') continue
      let raw: any =
        (b as any).content ??
        (b as any).plan ??
        safeGet(() => (b as any).plan_decision?.plan)
      if (typeof raw === 'string') {
        try {
          raw = JSON.parse(raw)
        } catch {
          raw = undefined
        }
      }
      const tasks = raw?.tasks ?? (Array.isArray(raw) ? raw : undefined)
      if (Array.isArray(tasks)) {
        return tasks
          .map((t: any) => ({
            title: String(t?.title ?? t?.name ?? t ?? '').trim(),
            status: String(t?.status ?? 'pending').toLowerCase(),
          }))
          .filter((t: PlanTask) => !!t.title)
      }
    }
    return []
  } catch {
    return []
  }
}
