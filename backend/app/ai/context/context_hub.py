"""
ContextHub - Main orchestrator for all agent context.
"""
import json
import logging
import time
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

_hub_logger = logging.getLogger(__name__)

# Process-wide cache for the heaviest piece of `prime_static` —
# the schema build. Keyed by (org_id, sorted ds-ids tuple, build_id).
# Schemas only change when a data source is re-introspected or
# table_stats roll up; in steady state they're stable for minutes.
# Without this, every completion paid ~1.6s rebuilding the same
# TablesSchemaContext from scratch (the dominant chunk of "setup").
# TTL keeps freshness loose — out-of-band schema refreshes catch up
# within the window. For correctness-critical change events, callers
# can call `invalidate_schema_cache(org_id)` directly.
_SCHEMA_CACHE: Dict[Tuple[str, Tuple[str, ...], Optional[str]], Tuple[float, Any]] = {}
# 5 minutes: schemas only change on re-introspection / stats rollup,
# and a typical user reads + types between prompts longer than 60s.
# Bump cautiously — table_stats updates won't show up until the next
# refresh or explicit invalidate_schema_cache() call.
_SCHEMA_CACHE_TTL_S: float = 300.0

# Instructions are keyed on query, so cross-prompt hits are rare; the
# main win is when the same prompt fires twice (retries, scheduled
# reruns). 2 minutes covers that without giving stale rankings a long
# tail. Always-load instructions are query-independent so they're
# always correct; only LLM-ranked load_mode="auto" entries lag.
_INSTRUCTIONS_CACHE: Dict[Tuple[str, Tuple[str, ...], Optional[str], str], Tuple[float, Any]] = {}
_INSTRUCTIONS_CACHE_TTL_S: float = 120.0


def invalidate_schema_cache(org_id: Optional[str] = None) -> None:
    """Drop cached schema entries. Pass org_id to scope; None drops all."""
    if org_id is None:
        _SCHEMA_CACHE.clear()
        return
    for k in list(_SCHEMA_CACHE.keys()):
        if k[0] == str(org_id):
            _SCHEMA_CACHE.pop(k, None)


def invalidate_instructions_cache(org_id: Optional[str] = None) -> None:
    """Drop cached instruction-build entries. Pass org_id to scope."""
    if org_id is None:
        _INSTRUCTIONS_CACHE.clear()
        return
    for k in list(_INSTRUCTIONS_CACHE.keys()):
        if k[0] == str(org_id):
            _INSTRUCTIONS_CACHE.pop(k, None)

from .context_specs import (
    ContextMetadata, ContextSnapshot, ContextBuildSpec,
    ContextObjectsSnapshot,
    SchemaContextConfig, MessageContextConfig, 
    WidgetContextConfig, InstructionContextConfig, CodeContextConfig,
    ResourceContextConfig
)
from .builders.schema_context_builder import SchemaContextBuilder
from .builders.files_context_builder import FilesContextBuilder
from .builders.message_context_builder import MessageContextBuilder
from .builders.widget_context_builder import WidgetContextBuilder
from .builders.query_context_builder import QueryContextBuilder
from .builders.instruction_context_builder import InstructionContextBuilder
from .builders.brain_context_builder import BrainContextBuilder
from .builders.brain_graph_context_builder import BrainGraphContextBuilder
from .builders.join_graph_context_builder import JoinGraphContextBuilder
from .builders.docs_context_builder import DocsContextBuilder
# hybrid Agent Memory: recall relevant remembered notes (own personal +
# approved shared). Self-gates on flags.AGENT_MEMORY; empty section (no DB hit)
# when off or query-less. Query-driven (vectorless FTS / Jaccard).
from .builders.agent_memory_context_builder import AgentMemoryContextBuilder
from .builders.skill_context_builder import SkillContextBuilder
# hybrid Studios ST7: per-Studio engineered context (voice + active
# instructions + active golden examples). Self-gates on flags.STUDIOS +
# report.studio_id; empty section (no DB hit) when off / non-studio.
from .builders.studio_context_builder import StudioContextBuilder
# Knowledge Layer Phase 4: approved semantic tables + metrics catalog (read).
from .builders.semantic_context_builder import SemanticContextBuilder
# Kepler Phase 2: proven generate_df code memory (read).
from .builders.code_bank_context_builder import CodeBankContextBuilder
from .builders.metrics_context_builder import MetricsContextBuilder
# Wave1 P1: deep profiler — per-column role catalog + top-3 values + variant
# warnings stored in DataSourceTable.metadata_json['profile_v2'].
# Self-gates on flags.PROFILE_V2; empty section (no DB hit) when off.
from .builders.profile_v2_context_builder import ProfileV2ContextBuilder
# Wave1 P6: code enrich — pipeline logic (grain + formulas + population) from
# source DDL/view definitions.  Self-gates on flags.CODE_ENRICH; empty section
# (no DB hit) when off.
from .builders.pipeline_logic_context_builder import PipelineLogicContextBuilder
from .builders.code_context_builder import CodeContextBuilder
from .builders.resource_context_builder import ResourceContextBuilder
from .builders.observation_context_builder import ObservationContextBuilder
from .context_view import ContextView, StaticSections, WarmSections
from .sections.messages_section import MessagesSection
from .sections.widgets_section import WidgetsSection
from .sections.observations_section import ObservationsSection
from .sections.resources_section import ResourcesSection
from .sections.code_section import CodeSection
from .builders.mention_context_builder import MentionContextBuilder
from .builders.entity_context_builder import EntityContextBuilder
from app.ai.utils.token_counter import count_tokens


# Default caps to keep planner prompt small and predictable
DEFAULT_CONTEXT_LIMITS = {
    "messages_max": 20,        # last N messages
    "observations_max": 8    # last N observations
}

# Hard ceiling for the assembled prompt (tokens).  Bedrock Sonnet caps at
# 200 K; even Anthropic direct benefits from staying well under the limit.
DEFAULT_TOKEN_BUDGET = 200_000
# Reserve room for the model's completion output so we don't fill the
# entire context window with the prompt.
_OUTPUT_RESERVE = 8_000


def _truncate_list(items, max_items):
    if not isinstance(items, list) or not max_items:
        return items
    return items[-max_items:]


def _safe_setattr_list(section, attr, max_items):
    """Safely truncate a list attribute on a section object."""
    try:
        if section and hasattr(section, attr):
            value = getattr(section, attr)
            if isinstance(value, list):
                setattr(section, attr, _truncate_list(value, max_items))
    except Exception:
        # Best-effort truncation only; never fail the refresh/build
        pass


def _section_token_length(text: Optional[str]) -> int:
    """Measure a section's size using token counts with safe fallbacks."""
    if not text:
        return 0
    try:
        return count_tokens(text)
    except Exception:
        # As a last resort, approximate via character length
        return len(text)


def _estimate_tokens_fast(text: str) -> int:
    """Fast token estimate without tiktoken overhead (~4 chars/token)."""
    return len(text) // 4 if text else 0


def _trim_text_tail(text: str, keep_ratio: float, label: str = "") -> str:
    """Trim text keeping the tail (newest content). Returns trimmed string."""
    if not text:
        return text
    char_limit = int(len(text) * keep_ratio)
    if char_limit >= len(text):
        return text
    trimmed = text[-char_limit:]
    prefix = f"... ({label} trimmed to fit context budget)\n" if label else "... (trimmed)\n"
    return prefix + trimmed


def trim_context_to_budget(
    planner_input,
    model_context_window: Optional[int] = None,
) -> None:
    """Trim PlannerInput string fields in priority order to fit token budget.

    Mutates *planner_input* in place. Each trimmable section is cut by its
    ``keep_ratio``; after each cut we re-estimate and stop as soon as the
    total is under budget.

    Priority (cut first → last):
      1. past_observations  – serialised JSON list, oldest dropped first
      2. messages_context   – oldest conversation pairs dropped
      3. resources_combined – least important for correctness
      4. schemas_combined   – nuclear option, but better than a hard failure
    """
    budget = (model_context_window or DEFAULT_TOKEN_BUDGET) - _OUTPUT_RESERVE
    if budget <= 0:
        budget = DEFAULT_TOKEN_BUDGET - _OUTPUT_RESERVE

    # Collect all string fields for a rough total estimate
    _str_fields = [
        "instructions", "schemas_combined", "schemas_excerpt",
        "files_context", "messages_context", "resources_context",
        "resources_combined", "mentions_context", "entities_context",
        "history_summary", "user_message",
    ]

    def _estimate_total() -> int:
        total = 0
        for f in _str_fields:
            total += _estimate_tokens_fast(getattr(planner_input, f, None) or "")
        # past_observations is a list of dicts – estimate via JSON dump
        past = getattr(planner_input, "past_observations", None)
        if past:
            try:
                total += _estimate_tokens_fast(json.dumps(past))
            except Exception:
                total += len(past) * 200  # rough fallback per observation
        # last_observation
        last = getattr(planner_input, "last_observation", None)
        if last:
            try:
                total += _estimate_tokens_fast(json.dumps(last))
            except Exception:
                total += 500
        return total

    total = _estimate_total()
    if total <= budget:
        return  # nothing to do

    # --- Priority 1: past_observations (drop oldest, keep last 2) ---
    past = getattr(planner_input, "past_observations", None)
    if past and len(past) > 2:
        planner_input.past_observations = past[-2:]
        total = _estimate_total()
        if total <= budget:
            return

    # --- Priority 2: messages_context (keep newest 50%) ---
    msg = getattr(planner_input, "messages_context", None) or ""
    if msg and _estimate_tokens_fast(msg) > 500:
        planner_input.messages_context = _trim_text_tail(msg, 0.5, "messages")
        total = _estimate_total()
        if total <= budget:
            return

    # --- Priority 3: resources_combined (keep 30%) ---
    res = getattr(planner_input, "resources_combined", None) or ""
    if res and _estimate_tokens_fast(res) > 500:
        planner_input.resources_combined = _trim_text_tail(res, 0.3, "resources")
        total = _estimate_total()
        if total <= budget:
            return

    # --- Priority 4: schemas_combined (keep 50%) ---
    schemas = getattr(planner_input, "schemas_combined", None) or ""
    if schemas and _estimate_tokens_fast(schemas) > 1000:
        planner_input.schemas_combined = _trim_text_tail(schemas, 0.5, "schemas")
        total = _estimate_total()
        if total <= budget:
            return

    # If still over, do a more aggressive second pass
    if total > budget:
        if getattr(planner_input, "past_observations", None):
            planner_input.past_observations = planner_input.past_observations[-1:]
        planner_input.messages_context = _trim_text_tail(
            getattr(planner_input, "messages_context", "") or "", 0.25, "messages"
        )
        planner_input.schemas_combined = _trim_text_tail(
            getattr(planner_input, "schemas_combined", "") or "", 0.3, "schemas"
        )


class ContextHub:
    """
    Central hub for all agent context orchestration.
    
    Coordinates existing and new context builders to provide
    comprehensive context for agent execution.
    """
    
    def __init__(
        self,
        db: AsyncSession,
        organization,
        report,
        data_sources,
        user=None,
        head_completion=None,
        widget=None,
        organization_settings=None,
        build_id: Optional[str] = None
    ):
        self.db = db
        self.organization = organization
        self.organization_settings = organization_settings
        self.data_sources = data_sources
        self.report = report
        self.user = user
        self.head_completion = head_completion
        self.widget = widget
        self.prompt_content = head_completion.prompt if head_completion else ""
        # Build system: specific instruction build to use (None = main build)
        self.build_id = build_id
        
        # Initialize metadata
        self.metadata = ContextMetadata(
            organization_id=organization.id,
            user_id=user.id if user else None,
            report_id=report.id if report else None,
            completion_id=head_completion.id if head_completion else None,
            widget_id=widget.id if widget else None,
            external_platform=getattr(head_completion, 'external_platform', None) if head_completion else None,
            external_user_id=getattr(head_completion, 'external_user_id', None) if head_completion else None,
        )
        
        # Initialize builders
        self._init_builders()
        
        # Static context cache (will be added later)
        self._static_cache: Dict[str, Any] = {}
        self._warm_cache: Dict[str, Any] = {}
    
    def _init_builders(self):
        """Initialize all context builders."""
        
        # Existing builders (enhanced)
        self.instruction_builder = InstructionContextBuilder(
            self.db,
            self.organization,
            organization_settings=self.organization_settings,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )
        self.code_builder = CodeContextBuilder(self.db, self.organization)
        self.resource_builder = ResourceContextBuilder(self.db, self.data_sources, self.organization, self.prompt_content)
        self.files_builder = FilesContextBuilder(self.db, self.organization, self.report)
        
        # New builders (port from agent.py)
        self.schema_builder = SchemaContextBuilder(self.db, self.data_sources, self.organization, self.report, user=self.user)
        self.message_builder = MessageContextBuilder(self.db, self.organization, self.report, self.user)
        self.widget_builder = WidgetContextBuilder(self.db, self.organization, self.report)
        self.query_builder = QueryContextBuilder(self.db, self.organization, self.report)
        self.mention_builder = MentionContextBuilder(self.db, self.organization, self.report, self.head_completion)
        self.entity_builder = EntityContextBuilder(self.db, self.organization, self.report)
        
        # Observation context builder (tracks tool execution results)
        self.observation_builder = ObservationContextBuilder()

        # hybrid-brain Phase 4: reasoning-cache reads (proven proven queries).
        # Self-gates on flags.BRAIN_READ; degrades to an empty section.
        self.brain_builder = BrainContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # hybrid Phase 8: entity/correlation graph (brain_graph_edges, pgvector
        # table + recursive-CTE traversal — NOT Apache AGE). Self-gates on
        # flags.BRAIN_GRAPH; empty section (no DB hit) when off. Injects top
        # PUBLISHED correlation edges for the run's data source.
        self.brain_graph_builder = BrainGraphContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # hybrid Phase 6: join-graph context (mined relationship/join edges).
        # Self-gates on flags.JOIN_GRAPH; empty section (no DB hit) when off.
        self.join_graph_builder = JoinGraphContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # hybrid Phase 5: company-docs RAG. Self-gates on flags.DOC_KNOWLEDGE;
        # empty section (no DB hit) when off or query-less. Query-driven (FTS).
        self.docs_builder = DocsContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # hybrid Agent Memory: recall relevant remembered notes (own personal +
        # approved shared) for the run. Self-gates on flags.AGENT_MEMORY; empty
        # section (no DB hit) when off or query-less. Needs the user so own
        # personal-scope memory is visible.
        self.agent_memory_builder = AgentMemoryContextBuilder(
            self.db,
            self.organization,
            user=self.user,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # hybrid Phase 6: self-service skills L1 catalog. Self-gates on
        # flags.SKILLS; empty section when off or no user.
        self.skill_builder = SkillContextBuilder(
            self.db,
            self.organization,
            user=self.user,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
            # hybrid Studios ST5: pass the active report so the builder can
            # restrict the offered skills to the Studio's pinned set when the
            # report belongs to a Studio (report.studio_id; flag-gated inside).
            report=self.report,
        )

        # hybrid Studios ST7: per-Studio engineered context (voice + active
        # instructions + active golden examples). Self-gates on flags.STUDIOS
        # AND report.studio_id; empty section (no DB hit) when off / non-studio.
        # Adds ONLY voice + instructions + examples — skills + grounded schemas
        # are already injected by the skill / schema builders.
        self.studio_builder = StudioContextBuilder(
            self.db,
            self.organization,
            user=self.user,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
            report=self.report,
        )

        # Knowledge Layer Phase 4 (read): approved semantic-table/column meaning
        # and the metrics catalog, scoped to org + in-scope data sources.
        # Self-gate on flags.SEMANTIC_LAYER / flags.METRICS_CATALOG; empty when off.
        self.semantic_builder = SemanticContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )
        self.metrics_builder = MetricsContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )
        # Kepler Phase 2 (read): proven generate_df code memory. Self-gates on
        # flags.CODE_BANK (empty section when off).
        self.code_bank_builder = CodeBankContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # Wave1 P1: deep profiler column-role catalog. Self-gates on
        # flags.PROFILE_V2; empty section (no DB hit) when off.
        self.profile_v2_builder = ProfileV2ContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

        # Wave1 P6: code enrich pipeline-logic catalog (grain + formulas +
        # population from DDL). Self-gates on flags.CODE_ENRICH; empty section
        # (no DB hit) when off.
        self.pipeline_logic_builder = PipelineLogicContextBuilder(
            self.db,
            self.organization,
            data_source_ids=[str(ds.id) for ds in self.data_sources] if self.data_sources else None,
        )

    async def build_context(
        self,
        spec: Optional[ContextBuildSpec] = None,
        research_context: Optional[Dict[str, Any]] = None,
        loop_index: int = 0
    ) -> ContextSnapshot:
        """
        Build comprehensive context snapshot for agent execution.
        
        Args:
            spec: What context sections to include
            research_context: Accumulated research findings
            loop_index: Current execution loop index
            
        Returns:
            Complete context snapshot with metadata
        """
        start_time = time.time()
        
        # Use default spec if not provided
        if spec is None:
            spec = ContextBuildSpec()
        
        # Update metadata
        self.metadata.loop_index = loop_index
        self.metadata.research_step_count = len(research_context or {})
        
        # Build context sections
        context = ContextSnapshot(metadata=self.metadata)
        section_sizes: Dict[str, int] = {}
        
        # Core sections
        if spec.include_schemas:
            # Build object using config params
            schema_cfg = spec.schema_config or SchemaContextConfig()
            schemas_section = await self.schema_builder.build(
                with_stats=schema_cfg.with_stats,
                top_k=schema_cfg.top_k,
                active_only=schema_cfg.active_only,
            )
            context.schemas_excerpt = schemas_section.render()
            # Prefer object-based count of tables if available; fallback to rendered lines
            try:
                data_sources = getattr(schemas_section, 'data_sources', []) or []
                table_count = 0
                for ds in data_sources:
                    tables = getattr(ds, 'tables', None)
                    if tables is None and isinstance(ds, dict):
                        tables = (ds.get('tables') or [])
                    if tables is None:
                        tables = []
                    try:
                        table_count += len(list(tables))
                    except Exception:
                        pass
                # Only set if we found a meaningful count; else fallback
                self.metadata.schemas_count = table_count if table_count > 0 else len(context.schemas_excerpt.split('\n'))
            except Exception:
                self.metadata.schemas_count = len(context.schemas_excerpt.split('\n'))
            section_sizes['schemas'] = _section_token_length(context.schemas_excerpt or '')
        
        if spec.include_messages:
            # Use new config or fallback to legacy parameters
            message_config = spec.message_config
            if not message_config:
                # Create config from legacy parameters
                message_config = MessageContextConfig(
                    max_messages=spec.max_messages or DEFAULT_CONTEXT_LIMITS["messages_max"],
                    role_filter=spec.message_role_filter
                )
            
            context.messages_context = await self.message_builder.build_context(
                max_messages=message_config.max_messages,
                role_filter=message_config.role_filter
            )
            self.metadata.messages_count = len(context.messages_context.split('\n'))
            section_sizes['messages'] = _section_token_length(context.messages_context or '')
        
        if spec.include_widgets:
            # Use new config or fallback to legacy parameters
            widget_config = spec.widget_config
            if not widget_config:
                widget_config = WidgetContextConfig(
                    max_widgets=spec.max_widgets or 5,
                    status_filter=spec.widget_status_filter
                )
            
            context.widgets_context = await self.widget_builder.build_context(
                max_widgets=widget_config.max_widgets,
                status_filter=widget_config.status_filter,
                include_data_preview=widget_config.include_data_preview
            )
            self.metadata.widgets_count = len(context.widgets_context.split('\n'))
            section_sizes['widgets'] = _section_token_length(context.widgets_context or '')
        
        if spec.include_instructions:
            # Build object, then render for legacy ContextSnapshot
            instruction_config = spec.instruction_config or InstructionContextConfig()
            # Use instruction_config.build_id if specified, otherwise fall back to hub's build_id
            effective_build_id = instruction_config.build_id or self.build_id
            inst_section = await self.instruction_builder.build(
                category=instruction_config.category,
                build_id=effective_build_id,
            )
            context.instructions_context = inst_section.render()
            section_sizes['instructions'] = _section_token_length(context.instructions_context or '')
        
        # Optional sections
        if spec.include_code:
            # CodeContextBuilder has complex interface, skip for now
            # TODO: Implement when code context is needed
            context.code_context = ""
            section_sizes['code'] = _section_token_length(context.code_context or '')
        
        if spec.include_resource:
            context.resource_context = await self.resource_builder.build()
            section_sizes['resources'] = _section_token_length(context.resource_context or '')

        # Files section (object cached, string rendered into legacy snapshot)
        if getattr(spec, 'include_files', True):
            files_section = await self.files_builder.build()
            # We do not attach to ContextSnapshot directly; kept for future

        # Entities section (delegated to builder; no inline heuristics)
        try:
            if getattr(spec, 'include_entities', False):
                # Get allow_llm_see_data setting
                allow_llm_see_data = True
                try:
                    org_settings = await self.organization.get_settings(self.db)
                    cfg = org_settings.get_config("allow_llm_see_data") if org_settings else None
                    allow_llm_see_data = bool(cfg.value) if cfg is not None else True
                except Exception:
                    pass
                
                ent_cfg = getattr(spec, 'entities_config', None)
                ent_section = await self.entity_builder.build_for_turn(
                    types=(getattr(ent_cfg, 'types', None) if ent_cfg else None),
                    top_k=(getattr(ent_cfg, 'top_k', 10) if ent_cfg else 10),
                    require_source_assoc=(getattr(ent_cfg, 'require_data_source_association', True) if ent_cfg else True),
                    keywords=(getattr(ent_cfg, 'keywords', None) if ent_cfg else None),
                    user_text=(self.prompt_content.get("content") if isinstance(self.prompt_content, dict) else str(self.prompt_content or "")),
                    allow_llm_see_data=allow_llm_see_data,
                )
                if ent_section:
                    context.entities_context = ent_section.render()
                    self._warm_cache["entities"] = ent_section
                    try:
                        self.metadata.entities_count = len(getattr(ent_section, 'items', []) or [])
                    except Exception:
                        pass
                    section_sizes['entities'] = _section_token_length(context.entities_context or '')
        except Exception:
            pass
        
        # Research context
        if spec.include_research_context and research_context:
            context.research_context = research_context
        
        # Build history summary (simplified for now)
        context.history_summary = await self._build_history_summary(context)
        
        # Update metadata  
        self.metadata.build_duration_ms = (time.time() - start_time) * 1000
        
        # Count warm section items from object-based cache (more accurate than text line counting)
        messages_section = self._warm_cache.get("messages", None)
        if messages_section and hasattr(messages_section, 'items'):
            self.metadata.messages_count = len(messages_section.items)
            # Add messages section size for total_tokens calculation
            messages_text = messages_section.render() if messages_section else ""
            section_sizes['messages'] = _section_token_length(messages_text)
        
        widgets_section = self._warm_cache.get("widgets", None)
        if widgets_section and hasattr(widgets_section, 'items'):
            self.metadata.widgets_count = len(widgets_section.items)
            # Add widgets section size for total_tokens calculation
            widgets_text = widgets_section.render() if widgets_section else ""
            section_sizes['widgets'] = _section_token_length(widgets_text)
        
        queries_section = self._warm_cache.get("queries", None)
        if queries_section and hasattr(queries_section, 'items'):
            self.metadata.queries_count = len(queries_section.items)
            # Add queries section size for total_tokens calculation
            queries_text = queries_section.render() if queries_section else ""
            section_sizes['queries'] = _section_token_length(queries_text)
        
        # Mentions section counts (mirror pattern used above)
        mentions_section = self._warm_cache.get("mentions", None)
        if mentions_section is not None:
            try:
                files_len = len(getattr(mentions_section, 'files', []) or [])
                ds_len = len(getattr(mentions_section, 'data_sources', []) or [])
                tables_len = len(getattr(mentions_section, 'tables', []) or [])
                entities_len = len(getattr(mentions_section, 'entities', []) or [])
                # Expose a total mentions count in metadata for diagnostics
                self.metadata.__dict__["mentions_count"] = files_len + ds_len + tables_len + entities_len
            except Exception:
                pass
            # Add mentions section size for total_tokens calculation
            try:
                mentions_text = mentions_section.render()
                section_sizes['mentions'] = _section_token_length(mentions_text or '')
            except Exception:
                pass
        
        # Expose section sizes for UI diagnostics and calculate total_tokens as sum
        try:
            self.metadata.section_sizes = section_sizes
            # Calculate total_tokens as sum of all section sizes
            self.metadata.total_tokens = sum(section_sizes.values())
        except Exception:
            pass
        context.metadata = self.metadata
        
        return context

    async def build(self, spec: Optional[ContextBuildSpec] = None, research_context: Optional[Dict[str, Any]] = None, loop_index: int = 0) -> ContextObjectsSnapshot:
        """Build and return object-based snapshot."""
        if spec is None:
            spec = ContextBuildSpec()
        self.metadata.loop_index = loop_index
        self.metadata.research_step_count = len(research_context or {})

        # Build sections as objects
        schemas_obj = None
        files_obj = None
        if spec.include_schemas:
            schema_cfg = spec.schema_config or SchemaContextConfig()
            schemas_obj = await self.schema_builder.build(
                with_stats=schema_cfg.with_stats,
                top_k=schema_cfg.top_k,
                active_only=schema_cfg.active_only,
            )

        # Files
        files_obj = await self.files_builder.build()

        snapshot = ContextObjectsSnapshot(
            schemas=schemas_obj,
            files=files_obj,
            metadata=self.metadata,
        )
        # Cache
        self._static_cache["schemas"] = schemas_obj or self._static_cache.get("schemas")
        self._static_cache["files"] = files_obj or self._static_cache.get("files")
        return snapshot

    # --------------------------------------------------------------
    # Simple lifecycle helpers to prime static and refresh warm
    # --------------------------------------------------------------
    async def prime_static(self, query: str | None = None) -> None:
        """Build and cache static sections once (schemas, instructions, code, resources).

        Runs all builders in parallel for faster startup.

        Parameters
        ----------
        query : str | None, optional
            The user's query/prompt. If provided, enables intelligent instruction
            search to find relevant instructions beyond just 'always' load mode.
        """
        import asyncio
        _t0 = time.monotonic()

        async def _timed(name, coro):
            t = time.monotonic()
            result = await coro
            _hub_logger.info(f"[context_hub:prime_static] {name} done +{(time.monotonic()-t)*1000:.0f}ms")
            return result

        # Schema cache: by (org, ds-ids, build_id). Schemas dominate the
        # prime_static cost (~1.6s of ~1.9s) and are stable across user
        # prompts; the `query` only affects instructions, not schemas.
        org_id = str(self.organization.id) if self.organization else ""
        ds_ids: Tuple[str, ...] = tuple(sorted(str(d.id) for d in (self.data_sources or [])))
        cache_key = (org_id, ds_ids, str(self.build_id) if self.build_id else None)
        now = time.monotonic()
        cached = _SCHEMA_CACHE.get(cache_key)

        async def _build_or_get_schemas():
            if cached is not None and (now - cached[0]) < _SCHEMA_CACHE_TTL_S:
                _hub_logger.info(
                    f"[context_hub:prime_static] schemas cache hit (age={now - cached[0]:.1f}s)"
                )
                return cached[1]
            t = time.monotonic()
            built = await self.schema_builder.build()
            _hub_logger.info(
                f"[context_hub:prime_static] schemas done (cache miss) +{(time.monotonic()-t)*1000:.0f}ms"
            )
            _SCHEMA_CACHE[cache_key] = (time.monotonic(), built)
            return built

        instr_key = (org_id, ds_ids, str(self.build_id) if self.build_id else None, str(query or ""))
        instr_cached = _INSTRUCTIONS_CACHE.get(instr_key)

        async def _build_or_get_instructions():
            if instr_cached is not None and (now - instr_cached[0]) < _INSTRUCTIONS_CACHE_TTL_S:
                _hub_logger.info(
                    f"[context_hub:prime_static] instructions cache hit (age={now - instr_cached[0]:.1f}s)"
                )
                return instr_cached[1]
            t = time.monotonic()
            built = await self.instruction_builder.build(query, build_id=self.build_id)
            _hub_logger.info(
                f"[context_hub:prime_static] instructions done (cache miss) +{(time.monotonic()-t)*1000:.0f}ms"
            )
            _INSTRUCTIONS_CACHE[instr_key] = (time.monotonic(), built)
            return built

        # Run static builders in parallel; schemas/instructions come from
        # the cache when warm.
        schemas, instructions, resources, files, brain, brain_graph, skills, studio, semantic, metrics, code_bank, join_graph, docs, agent_memory, profile_v2, pipeline_logic = await asyncio.gather(
            _build_or_get_schemas(),
            _build_or_get_instructions(),
            _timed("resources", self.resource_builder.build()),
            _timed("files", self.files_builder.build()),
            _timed("brain", self.brain_builder.build(query=query)),
            _timed("brain_graph", self.brain_graph_builder.build(query=query)),
            _timed("skills", self.skill_builder.build(query=query)),
            _timed("studio", self.studio_builder.build(query=query)),
            _timed("semantic", self.semantic_builder.build(query=query)),
            _timed("metrics", self.metrics_builder.build(query=query)),
            _timed("code_bank", self.code_bank_builder.build(query=query)),
            _timed("join_graph", self.join_graph_builder.build(query=query)),
            _timed("docs", self.docs_builder.build(query=query)),
            _timed("agent_memory", self.agent_memory_builder.build(query=query)),
            _timed("profile_v2", self.profile_v2_builder.build(query=query)),
            _timed("pipeline_logic", self.pipeline_logic_builder.build(query=query)),
            return_exceptions=True,
        )
        _hub_logger.info(f"[context_hub:prime_static] all_done +{(time.monotonic()-_t0)*1000:.0f}ms")

        # Store results (handle exceptions gracefully)
        self._static_cache["schemas"] = schemas if not isinstance(schemas, Exception) else None
        self._static_cache["instructions"] = instructions if not isinstance(instructions, Exception) else None
        self._static_cache["code"] = None
        self._static_cache["resources"] = resources if not isinstance(resources, Exception) else None
        self._static_cache["files"] = files if not isinstance(files, Exception) else None
        self._static_cache["brain"] = brain if not isinstance(brain, Exception) else None
        self._static_cache["brain_graph"] = brain_graph if not isinstance(brain_graph, Exception) else None
        self._static_cache["join_graph"] = join_graph if not isinstance(join_graph, Exception) else None
        self._static_cache["skills"] = skills if not isinstance(skills, Exception) else None
        self._static_cache["studio"] = studio if not isinstance(studio, Exception) else None
        self._static_cache["semantic"] = semantic if not isinstance(semantic, Exception) else None
        self._static_cache["metrics"] = metrics if not isinstance(metrics, Exception) else None
        self._static_cache["code_bank"] = code_bank if not isinstance(code_bank, Exception) else None
        self._static_cache["docs"] = docs if not isinstance(docs, Exception) else None
        self._static_cache["agent_memory"] = agent_memory if not isinstance(agent_memory, Exception) else None
        self._static_cache["profile_v2"] = profile_v2 if not isinstance(profile_v2, Exception) else None
        self._static_cache["pipeline_logic"] = pipeline_logic if not isinstance(pipeline_logic, Exception) else None

    async def refresh_warm(self) -> None:
        """Rebuild warm sections each loop (messages, queries, observations, entities).

        Runs builders in parallel where possible for faster refresh.
        """
        import asyncio
        _t0 = time.monotonic()

        async def _timed(name, coro):
            t = time.monotonic()
            result = await coro
            _hub_logger.info(f"[context_hub:refresh_warm] {name} done +{(time.monotonic()-t)*1000:.0f}ms")
            return result

        # Get org settings first (needed for queries and entities)
        allow_llm_see_data = True
        try:
            org_settings = await self.organization.get_settings(self.db)
            cfg = org_settings.get_config("allow_llm_see_data") if org_settings else None
            allow_llm_see_data = bool(cfg.value) if cfg is not None else True
        except Exception:
            allow_llm_see_data = True

        # Extract user text for entity keyword matching
        user_text = ""
        try:
            if isinstance(self.prompt_content, dict):
                user_text = self.prompt_content.get("content", "")
            else:
                user_text = str(self.prompt_content or "")
        except Exception:
            user_text = ""

        # Run all warm builders in parallel
        messages, queries, mentions, entities = await asyncio.gather(
            _timed("messages", self.message_builder.build(max_messages=DEFAULT_CONTEXT_LIMITS["messages_max"])),
            _timed("queries", self.query_builder.build(max_queries=5, include_data_preview=allow_llm_see_data)),
            _timed("mentions", self.mention_builder.build()),
            _timed("entities", self.entity_builder.build_for_turn(
                top_k=5,
                require_source_assoc=True,
                user_text=user_text,
                allow_llm_see_data=allow_llm_see_data,
            )),
            return_exceptions=True,
        )
        _hub_logger.info(f"[context_hub:refresh_warm] all_done +{(time.monotonic()-_t0)*1000:.0f}ms")
        
        # Build observations synchronously (it's fast, no DB calls)
        observations = self.observation_builder.build()
        _safe_setattr_list(observations, "items", DEFAULT_CONTEXT_LIMITS["observations_max"])

        # Scheduled tasks for this report (warm: changes when created/cancelled mid-session)
        try:
            scheduled_tasks = await self._build_scheduled_tasks_section()
        except Exception as e:
            _hub_logger.warning(f"[context_hub:refresh_warm] scheduled_tasks failed: {e}")
            scheduled_tasks = None

        self._warm_cache.update({
            "messages": messages if not isinstance(messages, Exception) else None,
            "widgets": None,  # Deprecated
            "queries": queries if not isinstance(queries, Exception) else None,
            "observations": observations,
            "mentions": mentions if not isinstance(mentions, Exception) else None,
            "entities": entities if not isinstance(entities, Exception) else None,
            "scheduled_tasks": scheduled_tasks,
        })

    async def _build_scheduled_tasks_section(self):
        """Build the <scheduled_tasks> section for the current report.

        Lists active (non-deleted) recurring tasks so the agent can avoid
        duplicates and has task ids available for cancellation.
        """
        from app.ai.context.sections.scheduled_tasks_section import (
            ScheduledTasksSection,
            ScheduledTaskItem,
        )
        if not self.report:
            return ScheduledTasksSection(items=[])

        from sqlalchemy import select
        from app.models.scheduled_prompt import ScheduledPrompt

        cron_labels = {
            "0 * * * *": "Hourly",
            "0 8 * * *": "Daily at 8am",
            "0 9 * * *": "Daily at 9am",
            "0 0 * * *": "Daily at midnight",
            "0 9 * * 1": "Weekly on Monday at 9am",
            "0 8 * * 1": "Weekly on Monday at 8am",
            "0 0 * * 1": "Weekly on Monday at midnight",
        }

        result = await self.db.execute(
            select(ScheduledPrompt)
            .filter(ScheduledPrompt.report_id == self.report.id)
            .filter(ScheduledPrompt.is_active == True)  # noqa: E712
            .filter(ScheduledPrompt.deleted_at == None)  # noqa: E711
            .order_by(ScheduledPrompt.created_at.asc())
        )
        rows = list(result.scalars().all())

        items: list = []
        for sp in rows:
            content = ""
            try:
                content = (sp.prompt or {}).get("content", "") if isinstance(sp.prompt, dict) else ""
            except Exception:
                content = ""
            snippet = content.strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "…"
            items.append(ScheduledTaskItem(
                id=str(sp.id),
                cron_schedule=sp.cron_schedule,
                cron_label=cron_labels.get(sp.cron_schedule),
                prompt_snippet=snippet or None,
                last_run_at=sp.last_run_at.isoformat() if sp.last_run_at else None,
            ))
        return ScheduledTasksSection(items=items)

    def get_view(self) -> ContextView:
        """Return a read-only grouped view over current static + warm context."""
        static = StaticSections(
            schemas=self._static_cache.get("schemas", None),
            instructions=self._static_cache.get("instructions", None),
            resources=self._static_cache.get("resources", None),
            code=self._static_cache.get("code", None),
            files=self._static_cache.get("files", None),
            brain=self._static_cache.get("brain", None),
            skills=self._static_cache.get("skills", None),
            semantic=self._static_cache.get("semantic", None),
            metrics=self._static_cache.get("metrics", None),
            code_bank=self._static_cache.get("code_bank", None),
        )
        warm = WarmSections(
            messages=self._warm_cache.get("messages", None),
            observations=self._warm_cache.get("observations", None),
            widgets=self._warm_cache.get("widgets", None),
            queries=self._warm_cache.get("queries", None),
            mentions=self._warm_cache.get("mentions", None),
            entities=self._warm_cache.get("entities", None),
            scheduled_tasks=self._warm_cache.get("scheduled_tasks", None),
        )
        meta = self.metadata.model_dump()
        return ContextView(static=static, warm=warm, meta=meta)

    def render_brain_graph_section(self) -> str:
        """Render the primed Phase-8 correlation-graph block, or "" .

        hybrid Phase 8 (BRAIN_GRAPH): the correlation-graph section is primed by
        BrainGraphContextBuilder into ``_static_cache['brain_graph']`` (empty
        section, no DB hit, when flags.BRAIN_GRAPH is OFF). Surfaced via this
        helper rather than a typed ContextView field so the wiring stays
        additive (graph = brain_graph_edges table + recursive CTE, NOT AGE).
        Never raises — returns "" on any error / when off.
        """
        try:
            section = self._static_cache.get("brain_graph", None)
            return section.render() if section else ""
        except Exception:
            return ""

    def render_join_graph_section(self) -> str:
        """Render the primed Phase-6 join-graph block, or "".

        hybrid Phase 6 (JOIN_GRAPH): the join-graph section is primed by
        JoinGraphContextBuilder into ``_static_cache['join_graph']`` (empty
        section, no DB hit, when flags.JOIN_GRAPH is OFF). Surfaced via this
        helper rather than a typed ContextView field so the wiring stays
        additive (join edges mined offline by the join_miner daemon).
        Never raises — returns "" on any error / when off.
        """
        try:
            section = self._static_cache.get("join_graph", None)
            return section.render() if section else ""
        except Exception:
            return ""

    def render_docs_section(self) -> str:
        """Render the primed Phase-5 company-docs block, or "".

        hybrid Phase 5 (DOC_KNOWLEDGE): DocsContextBuilder runs a PG full-text
        search of the question against APPROVED doc chunks and primes a
        DocsSection into ``_static_cache['docs']`` (empty section, no DB hit,
        when flags.DOC_KNOWLEDGE is OFF or the query is empty). Surfaced via
        this helper — mirrors render_join_graph_section. Never raises.
        """
        try:
            section = self._static_cache.get("docs", None)
            return section.render() if section else ""
        except Exception:
            return ""

    def render_agent_memory_section(self) -> str:
        """Render the primed agent-memory block, or "".

        hybrid Agent Memory (flags.AGENT_MEMORY): AgentMemoryContextBuilder
        recalls the most relevant visible memories (own personal + approved
        shared) for the run's query and primes an AgentMemorySection into
        ``_static_cache['agent_memory']`` (empty section, no DB hit, when
        flags.AGENT_MEMORY is OFF or the query is empty). Surfaced via this
        helper — mirrors render_docs_section. Never raises.
        """
        try:
            section = self._static_cache.get("agent_memory", None)
            return section.render() if section else ""
        except Exception:
            return ""

    def render_studio_section(self) -> str:
        """Render the primed per-Studio engineered-context block, or "".

        hybrid Studios ST7 (flags.STUDIOS): when the active report belongs to a
        Studio, StudioContextBuilder primes a StudioSection (voice + ACTIVE
        instructions + ACTIVE golden examples) into ``_static_cache['studio']``
        (empty section, no DB hit, when flags.STUDIOS is OFF or the report has
        no studio_id). Surfaced via this helper — mirrors
        render_brain_graph_section — so agent_v2 appends it to the planner
        instructions with a single flag-agnostic call. Skills + grounded schemas
        are injected elsewhere; this block adds voice + instructions + examples
        only. Never raises — returns "" on any error / when off.
        """
        try:
            section = self._static_cache.get("studio", None)
            return section.render() if section else ""
        except Exception:
            return ""

    def render_profile_v2_section(self) -> str:
        """Render the primed Wave1-P1 deep-profiler column-role catalog, or "".

        Wave1 P1 (PROFILE_V2): ProfileV2ContextBuilder loads stored
        metadata_json['profile_v2'] blobs for ACTIVE tables in scope and primes a
        ProfileV2Section into ``_static_cache['profile_v2']`` (empty section, no DB
        hit, when flags.PROFILE_V2 is OFF).  Surfaced via this helper — mirrors
        render_brain_graph_section.  Never raises — returns "" on any error / when off.
        """
        try:
            section = self._static_cache.get("profile_v2", None)
            return section.render() if section else ""
        except Exception:
            return ""

    def render_pipeline_logic_section(self) -> str:
        """Render the primed Wave1-P6 pipeline-logic block, or "".

        Wave1 P6 (CODE_ENRICH): PipelineLogicContextBuilder loads stored
        metadata_json['pipeline_logic'] blobs for ACTIVE tables in scope and primes a
        PipelineLogicSection into ``_static_cache['pipeline_logic']`` (empty section,
        no DB hit, when flags.CODE_ENRICH is OFF).  Surfaced via this helper — mirrors
        render_profile_v2_section.  Never raises — returns "" on any error / when off.
        """
        try:
            section = self._static_cache.get("pipeline_logic", None)
            return section.render() if section else ""
        except Exception:
            return ""

    async def _build_history_summary(self, context: ContextSnapshot) -> str:
        """Build a summary of conversation history for planner context."""
        # Simplified implementation - can be enhanced later
        summary_parts = []
        
        if context.messages_context:
            summary_parts.append(f"Previous conversation: {len(context.messages_context.split('user:'))} exchanges")
        
        if context.widgets_context:
            summary_parts.append(f"Created widgets: {self.metadata.widgets_count}")
        
        if context.research_context:
            research_tools = list(context.research_context.keys())
            summary_parts.append(f"Research completed: {', '.join(research_tools)}")
        
        return "; ".join(summary_parts) if summary_parts else "No previous context"
    
    async def get_schemas(self) -> str:
        """Quick access to schemas context only."""
        section = await self.schema_builder.build()
        return section.render()
    
    async def get_messages_context(self, max_messages: int = 20) -> str:
        """Quick access to messages context only."""
        section = await self.message_builder.build(max_messages=max_messages)
        return section.render()
    
    async def get_resources_context(self) -> str:
        """Quick access to resources context from metadata resources."""
        section = await self.resource_builder.build()
        return section.render()
    
    def get_history_summary(self, research_context: Optional[Dict[str, Any]] = None) -> str:
        """Quick access to history summary from cached warm sections.
        
        This is a fast synchronous method that uses already-cached data from
        refresh_warm() instead of rebuilding context via build_context().
        """
        summary_parts = []
        
        # Use cached messages section
        messages_section = self._warm_cache.get("messages")
        if messages_section:
            try:
                items = getattr(messages_section, 'items', []) or []
                user_count = sum(1 for m in items if getattr(m, 'role', '') == 'user')
                summary_parts.append(f"Previous conversation: {user_count} exchanges")
            except Exception:
                pass
        
        # Use cached widgets section
        widgets_section = self._warm_cache.get("widgets")
        if widgets_section:
            try:
                items = getattr(widgets_section, 'items', []) or []
                if items:
                    summary_parts.append(f"Created widgets: {len(items)}")
            except Exception:
                pass
        
        # Use cached queries section
        queries_section = self._warm_cache.get("queries")
        if queries_section:
            try:
                items = getattr(queries_section, 'items', []) or []
                if items:
                    summary_parts.append(f"Queries executed: {len(items)}")
            except Exception:
                pass
        
        # Include research context if provided
        if research_context:
            research_tools = list(research_context.keys())
            if research_tools:
                summary_parts.append(f"Research completed: {', '.join(research_tools)}")
        
        return "; ".join(summary_parts) if summary_parts else "No previous context"
    
    async def render(self, format_for_prompt: bool = True, include_metadata: bool = False) -> str:
        """
        Render context for prompt inclusion or debugging.
        
        Args:
            format_for_prompt: If True, format for LLM prompt inclusion (compact).
                             If False, format for debugging/inspection (detailed).
            include_metadata: Whether to include metadata in the output
            
        Returns:
            Formatted string representation of all context
        """
        context = await self.build_context()
        
        if format_for_prompt:
            return self._render_for_prompt(context, include_metadata)
        else:
            return self._render_for_debug(context, include_metadata)
    
    def _render_for_prompt(self, context: ContextSnapshot, include_metadata: bool) -> str:
        """Render context optimized for LLM prompt inclusion (compact format)."""
        parts = []
        
        if include_metadata:
            parts.append(f"<context_meta org={self.metadata.organization_id} report={self.metadata.report_id} loop={self.metadata.loop_index}/>")
        
        if context.schemas_excerpt:
            parts.append(f"<schemas>\n{context.schemas_excerpt}\n</schemas>")
        
        if context.messages_context:
            # Compact message format for prompts
            parts.append(f"<conversation>\n{context.messages_context[:2000]}...\n</conversation>")
        
        if context.widgets_context:
            parts.append(f"<widgets>\n{context.widgets_context}\n</widgets>")
        
        if context.instructions_context:
            parts.append(f"<instructions>\n{context.instructions_context}\n</instructions>")
        
        if context.research_context:
            research_summary = "; ".join([f"{k}: {v}" for k, v in context.research_context.items()])
            parts.append(f"<research>\n{research_summary}\n</research>")
        
        return "\n\n".join(parts)
    
    def _render_for_debug(self, context: ContextSnapshot, include_metadata: bool) -> str:
        """Render context for debugging/inspection (detailed format)."""
        parts = []
        
        if include_metadata:
            parts.append("=== CONTEXT METADATA ===")
            parts.append(f"Organization: {self.metadata.organization_id}")
            parts.append(f"Report: {self.metadata.report_id}")
            parts.append(f"User: {self.metadata.user_id}")
            parts.append(f"Loop: {self.metadata.loop_index}")
            parts.append(f"Research Steps: {self.metadata.research_step_count}")
            parts.append(f"Generated: {self.metadata.generation_time}")
            parts.append("")
        
        if context.schemas_excerpt:
            parts.append("=== SCHEMAS ===")
            parts.append(context.schemas_excerpt)
            parts.append("")
        
        if context.messages_context:
            parts.append("=== CONVERSATION HISTORY ===")
            parts.append(context.messages_context)
            parts.append("")
        
        if context.widgets_context:
            parts.append("=== WIDGETS ===")
            parts.append(context.widgets_context)
            parts.append("")
        
        if context.instructions_context:
            parts.append("=== INSTRUCTIONS ===")
            parts.append(context.instructions_context)
            parts.append("")
        
        # Add observation context if available
        observation_context = self.observation_builder.build_context(format_for_prompt=False)
        if observation_context:
            parts.append("=== OBSERVATION CONTEXT ===")
            parts.append(observation_context)
            parts.append("")
        
        if context.history_summary:
            parts.append("=== SUMMARY ===")
            parts.append(context.history_summary)
        
        return "\n".join(parts)