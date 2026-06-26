"""Nodes for the KOL copy-trade strategy.

The rule nodes (`fast_safety`, `kol_quality`, `fast_market`, `sizing`)
are deterministic; no LLM call. They mirror the sniper's fast-path
style (set ``state.output`` and ``goto=__end__`` on rejection) so the
graph can short-circuit without the analyst.

In ``confirmed`` mode the graph also runs an LLM analyst node
(``kol_analyst_prompt`` + ``neutral_kol_verdict``) between
``fast_market`` and ``sizing``. The analyst can veto the buy entirely
(approve=False → action=skip) or nudge size up/down via
``size_multiplier`` — the sizing node respects the verdict.

In ``audit`` mode (K6) the graph runs rule sizing first (sub-ms decide
returned to the bot), then fires a fire-and-forget LLM audit task
that lands in ``state.scratch["kol_audit_task"]``. The bot can ``await``
the task later and write the verdict to ``DecisionLog`` for offline
tuning — the hot path is never blocked. Mirrors the sniper's
``hybrid_audit`` pattern.

Boundary recap: the framework owns the *rules*; the bot owns the
*data and state*. ``last_copy_ts`` (for cooldown), KOL whitelist
contents, token enrichment, and any tool implementations the analyst
may invoke are all bot-supplied via ``KOLContext`` and the injected
``KOLRegistry``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from trading.schemas import Decision, KOLAnalystVerdict
from zetryn.core import Command, State
from zetryn.knowledge import KnowledgePack
from zetryn.llm import LLMClient, Message, system, user
from zetryn.llm.structured import structured_complete

from ..kol_registry import KOLRegistry


def _latency_ms(state: State) -> float:
    return round(sum(t.duration_ms for t in state.trace), 4)


def _abort(state: State, reason: str, *, action: str = "skip",
           rug_risk: bool = False) -> Command:
    state.output = Decision(
        action=action,
        confidence=0.0,
        reasons=[reason],
        flags={"rug_risk": rug_risk, "llm_failed": False},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )
    return Command(goto="__end__")


# -- node 1: contract safety -------------------------------------------------


def fast_safety(state: State) -> Command | None:
    """Instant abort on a dangerous contract (reuses TokenInput.contract)."""
    c = state.context.token.contract
    if c.is_dangerous:
        return _abort(
            state,
            "contract unsafe: " + (", ".join(c.notes) or "rug risk"),
            action="abort",
            rug_risk=True,
        )
    return None


# -- node 2: KOL whitelist + signal-quality gate ----------------------------


def make_kol_quality(registry: KOLRegistry) -> Callable[[State], Command | None]:
    """Factory: binds the bot's `KOLRegistry` to a rule node.

    The node enforces, in order:
      1. Wallet is on the whitelist.
      2. Profile clears the pack-wide tier + hit-rate floor.
      3. Profile clears the per-deployment `KOLCopyTradeConfig` floors.
      4. KOL's own buy size meets `profile.min_sol_to_copy`.
      5. Signal is fresh (`event.block_age_seconds` ≤
         `config.max_signal_age_seconds`).
      6. Cooldown respected (`event.detected_at_ts - last_copy_ts` ≥
         `config.kol_cooldown_seconds`).

    Each rejection writes a `Decision(action="skip")` with a precise
    `reasons[]` entry so the bot can log which gate fired.
    """
    _TIER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3}

    def kol_quality(state: State) -> Command | None:
        ctx = state.context
        ev = ctx.event
        cfg = ctx.config

        # 1. on the whitelist at all?
        profile = registry.get(ev.wallet)
        if profile is None:
            return _abort(state, f"unknown KOL wallet: {ev.wallet[:8]}...")

        # 2. pack-wide global floor
        if not registry.passes_global_floor(profile):
            return _abort(
                state,
                f"KOL {profile.name or ev.wallet[:8]} below pack floor "
                f"(tier={profile.tier}, hit_rate={profile.hit_rate:.2f}, "
                f"required tier≥{registry.min_tier} hit_rate≥{registry.min_hit_rate:.2f})",
            )

        # 3. per-deployment floor (tighter than pack)
        my_tier = _TIER_ORDER.get(profile.tier, 99)
        deploy_floor = _TIER_ORDER.get(cfg.min_kol_tier, 99)
        if my_tier > deploy_floor:
            return _abort(
                state,
                f"KOL tier {profile.tier} below deployment min {cfg.min_kol_tier}",
            )
        if profile.hit_rate < cfg.min_kol_hit_rate:
            return _abort(
                state,
                f"KOL hit_rate {profile.hit_rate:.2f} below deployment min "
                f"{cfg.min_kol_hit_rate:.2f}",
            )

        # 4. KOL's own bet must be meaningful
        if ev.sol_amount < profile.min_sol_to_copy:
            return _abort(
                state,
                f"KOL buy size {ev.sol_amount} SOL below profile threshold "
                f"{profile.min_sol_to_copy} SOL",
            )

        # 5. signal staleness
        if ev.block_age_seconds > cfg.max_signal_age_seconds:
            return _abort(
                state,
                f"signal too stale: {ev.block_age_seconds:.1f}s > "
                f"{cfg.max_signal_age_seconds:.0f}s",
            )

        # 6. cooldown
        if ctx.last_copy_ts is not None:
            elapsed = ev.detected_at_ts - ctx.last_copy_ts
            if elapsed < cfg.kol_cooldown_seconds:
                return _abort(
                    state,
                    f"KOL cooldown active: {elapsed:.1f}s since last copy "
                    f"(min {cfg.kol_cooldown_seconds:.0f}s)",
                )

        # All checks passed — record the profile for downstream nodes.
        state.scratch["kol_profile"] = profile
        return None

    kol_quality.__name__ = "kol_quality"
    return kol_quality


# -- node 3: market hard-gate (mirror sniper.fast_market) -------------------


def fast_market(state: State) -> Command | None:
    """Skip if liquidity/volume too thin, or bundler/sniper density too high."""
    m = state.context.token.market
    w = state.context.token.wallets
    cfg = state.context.config

    if m.liquidity_usd < cfg.min_liquidity_usd:
        return _abort(state, f"liquidity ${m.liquidity_usd:,.0f} below min "
                             f"${cfg.min_liquidity_usd:,.0f}")
    if m.volume_1h < cfg.min_volume_1h:
        return _abort(state, f"volume_1h ${m.volume_1h:,.0f} below min "
                             f"${cfg.min_volume_1h:,.0f}")

    h = state.context.token.holders
    if h.top10_pct > cfg.max_top10_pct:
        return _abort(state, f"top10_pct {h.top10_pct:.0%} above max "
                             f"{cfg.max_top10_pct:.0%}")
    if w.bundler_wallet_count > cfg.max_bundler_count:
        return _abort(state, f"bundler_count {w.bundler_wallet_count} above max "
                             f"{cfg.max_bundler_count}")
    if w.sniper_wallet_count > cfg.max_sniper_count:
        return _abort(state, f"sniper_count {w.sniper_wallet_count} above max "
                             f"{cfg.max_sniper_count}")
    return None


# -- node 4 (optional, confirmed mode): LLM analyst -------------------------


_KOL_LESSONS_HEADER = (
    "LESSONS from recent KOL copy-trade outcomes — use these to avoid "
    "repeating losing patterns. The agent ran on the same data sources "
    "and these are real outcomes:"
)


def _kol_lessons_block(state: State) -> Message | None:
    """Return a system message with the ReflectiveNode summary, or None if absent."""
    text = state.scratch.get("lessons_text")
    if not text or not isinstance(text, str):
        return None
    return system(f"{_KOL_LESSONS_HEADER}\n\n{text}")


def kol_analyst_prompt(state: State) -> list[Message]:
    """Build the analyst prompt for `confirmed` mode.

    The token has already passed every hard rule + the KOL whitelist
    check. The analyst is NOT deciding "buy or not from scratch" — it is
    looking for qualitative red flags the rule layer cannot encode, and
    nudging size based on observed confluence.

    When ``state.scratch["lessons_text"]`` is set by a ``ReflectiveNode``
    upstream, an extra system message is inserted between the analyst
    persona and the per-token fact sheet so the LLM conditions on real
    historical outcomes — closing the K7 learning loop.
    """
    ctx = state.context
    ev = ctx.event
    t = ctx.token
    profile = state.scratch["kol_profile"]   # set by kol_quality

    m, h, c, a, w, s = (
        t.market, t.holders, t.contract, t.activity, t.wallets, t.social
    )
    tw = s.twitter
    facts: list[str] = [
        f"KOL: {profile.name or ev.wallet[:8]} (tier {profile.tier}, "
        f"hit_rate {profile.hit_rate:.2f}, avg_pnl {profile.avg_pnl_pct:+.0%}, "
        f"exit_pattern={profile.exit_pattern or 'unknown'})",
        f"KOL just bought {ev.sol_amount} SOL of {t.symbol} "
        f"({ev.block_age_seconds:.1f}s ago)",
        "",
        "TOKEN — Market",
        f"  mcap=${m.mcap:,.0f}  liquidity=${m.liquidity_usd:,.0f}  "
        f"vol_1h=${m.volume_1h:,.0f}  age={m.age_seconds or 0:.0f}s",
        "TOKEN — Activity (5m)",
        f"  vol_5m=${a.volume_5m_usd:,.0f}  buys={a.buys_5m}  sells={a.sells_5m}  "
        f"buy_ratio={a.buy_ratio_5m:.2f}",
        "TOKEN — Holders",
        f"  count={h.count}  top10={h.top10_pct:.0%}  dev={h.dev_pct:.0%}",
        "TOKEN — Contract",
        f"  honeypot={c.is_honeypot}  bundled={c.bundled_supply}  "
        f"dev_rug={c.dev_rug_history}  lp_burned={c.lp_burned}  lp_locked={c.lp_locked}",
        "TOKEN — Wallet intel",
        f"  smart_buys={w.smart_wallet_buys}  kol_count={w.kol_wallet_count}  "
        f"snipers={w.sniper_wallet_count}  bundlers={w.bundler_wallet_count}",
        "TOKEN — Social",
        f"  twitter @{tw.handle or '?'}: followers={tw.followers}  "
        f"mention_growth={tw.mention_growth_pct:+.0f}%  velocity={tw.velocity_tpm:.1f}tpm  "
        f"sentiment={tw.sentiment or 'unknown'}",
        f"  kol_buying_5m={s.kol_count_5m}",
    ]

    messages: list[Message] = [
        system(
            "You are a senior memecoin trade auditor. A KOL has just made a buy "
            "on Solana, and a rule-based filter has already approved both the "
            "KOL's quality and the token's safety + market structure. Your job "
            "is to second-guess that approval ONLY on qualitative concerns the "
            "rules cannot encode:\n"
            "- Is the KOL's tier / hit_rate consistent with their exit pattern? "
            "  An S-tier with a 'dumps_into_followers' pattern is more dangerous "
            "  than a B-tier with 'scales_out_50pct'.\n"
            "- Does the on-chain confluence support the KOL signal? Smart buys + "
            "  KOL count + positive buy_ratio + organic social growth = strong "
            "  confluence. KOL alone with no other confirmation = weaker.\n"
            "- SUB-THRESHOLD red flags MATTER. Rules approved this token, but a "
            "  sub-threshold metric is still a yellow flag and should reduce size:\n"
            "    * bundler_count >= 1 (even 1 or 2, below the cap) — coordinated\n"
            "      manipulation risk\n"
            "    * sniper_count >= 5 (even below the cap) — bot-driven launch, "
            "      choppy exit\n"
            "    * dev_pct == 0% or unusually high — abnormal project structure\n"
            "    * LP not locked (even when burned) — soft contract risk\n"
            "    * social_velocity dropping while mention_growth is high — paid hype\n"
            "  Each of these alone is worth ~0.1-0.2 off the multiplier. Two or "
            "  more compounding warrants 0.5-0.7.\n"
            "\n"
            "Output JSON matching KOLAnalystVerdict:\n"
            "- approve=True with size_multiplier 1.0-1.2 by default if everything\n"
            "  is genuinely clean (no sub-threshold flags)\n"
            "- approve=True with size_multiplier 1.3-1.5 only on STRONG multi-aspect\n"
            "  confluence (smart_buys ≥ 5 AND kol_count ≥ 3 AND velocity ≥ 8 AND\n"
            "  zero sub-threshold flags)\n"
            "- approve=True with size_multiplier 0.5-0.8 for one or two\n"
            "  sub-threshold concerns\n"
            "- approve=True with size_multiplier 0.3-0.5 for compounded soft\n"
            "  concerns or weak confluence (KOL alone, social hype with no\n"
            "  on-chain backing, etc.)\n"
            "- approve=False ONLY when:\n"
            "    * KOL exit_pattern explicitly indicates predation\n"
            "      ('dumps_into_followers', 'rug_pulls', etc.), OR\n"
            "    * three or more independent red flags compound\n"
            "List concerns as short phrases. Reasoning is one or two sentences."
        ),
    ]
    lessons = _kol_lessons_block(state)
    if lessons is not None:
        messages.append(lessons)
    messages.append(user("Fact sheet:\n" + "\n".join(facts)))
    return messages


def neutral_kol_verdict(state: State, exc: Exception) -> KOLAnalystVerdict:
    """Conservative fallback when the analyst LLM is unavailable.

    Defaults to approve=True (rules already passed) with size_multiplier=1.0
    so we don't punish the trade for an infrastructure failure — but we flag
    `llm_failed` downstream so the caller can demote in their own logic if
    they prefer to skip on LLM outages.
    """
    return KOLAnalystVerdict(
        approve=True,
        size_multiplier=1.0,
        confidence=0.0,
        concerns=["analyst LLM unavailable"],
        reasoning=f"LLM unavailable ({type(exc).__name__}); deferring to rule decision.",
    )


# -- node 5: sizing + buy (terminal) -----------------------------------------


def sizing(state: State) -> None:
    """Compute final size and emit the buy Decision (terminal rule node).

    Formula (parameters from KOLCopyTradeConfig):
        kol_conf  = clamp((hit_rate - floor) / (ceiling - floor), 0, 1)
        kol_mult  = 1 + 2 * kol_conf                          # 1.0 .. 3.0
        top10_pen = 1 - max(0, top10_pct - penalty_start)     # 1.0 .. ~0.4
        rule_size = clamp(base_size * kol_mult * top10_pen, 0, max_size)
        size      = clamp(rule_size * analyst_size_multiplier, 0, max_size)

    `analyst_size_multiplier` defaults to 1.0 when no analyst ran (rule mode).
    In `confirmed` mode the LLM verdict can:
      - approve=False → action=skip (size=None, ignored)
      - approve=True + multiplier in [0, 1.5] → scale the rule size
    """
    cfg = state.context.config
    h = state.context.token.holders
    profile = state.scratch["kol_profile"]   # set by kol_quality

    floor, ceiling = cfg.kol_confidence_floor, cfg.kol_confidence_ceiling
    raw = (profile.hit_rate - floor) / max(ceiling - floor, 1e-9)
    kol_conf = max(0.0, min(1.0, raw))
    kol_mult = 1.0 + 2.0 * kol_conf

    top10_pen = 1.0 - max(0.0, h.top10_pct - cfg.top10_penalty_start)
    top10_pen = max(0.0, min(1.0, top10_pen))

    rule_size = cfg.base_size * kol_mult * top10_pen
    rule_size = max(0.0, min(rule_size, cfg.max_size))

    # Read the analyst verdict if one was produced (confirmed mode).
    verdict: KOLAnalystVerdict | None = state.scratch.get("kol_analyst")
    llm_failed = bool(state.scratch.get("kol_analyst__llm_failed", False))

    if verdict is not None and not verdict.approve:
        # Analyst veto wins — skip the trade even though rules approved.
        state.output = Decision(
            action="skip",
            confidence=verdict.confidence,
            reasons=[
                f"KOL {profile.name or 'unknown'} (tier {profile.tier}, "
                f"hit_rate {profile.hit_rate:.2f})",
                f"analyst veto: {verdict.reasoning}",
                *(f"concern: {c}" for c in verdict.concerns),
            ],
            flags={"rug_risk": False, "llm_failed": llm_failed, "analyst_veto": True},
            meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
        )
        return

    size_mult = verdict.size_multiplier if verdict is not None else 1.0
    size = max(0.0, min(rule_size * size_mult, cfg.max_size))

    base_conf = 0.5 + 0.5 * kol_conf
    confidence = base_conf if verdict is None else round((base_conf + verdict.confidence) / 2, 3)

    reasons = [
        f"KOL {profile.name or 'unknown'} (tier {profile.tier}, "
        f"hit_rate {profile.hit_rate:.2f})",
        f"size {size:.4f} = base {cfg.base_size} × "
        f"kol_mult {kol_mult:.2f} × top10_pen {top10_pen:.2f}"
        + (f" × analyst×{size_mult:.2f}" if verdict is not None else ""),
    ]
    if verdict is not None:
        reasons.append(f"analyst: {verdict.reasoning}")
        for c in verdict.concerns:
            reasons.append(f"concern: {c}")

    scores = {
        "kol_confidence": round(kol_conf, 3),
        "top10_penalty": round(top10_pen, 3),
    }
    if verdict is not None:
        scores["analyst_size_multiplier"] = round(size_mult, 3)
        scores["analyst_confidence"] = round(verdict.confidence, 3)

    state.output = Decision(
        action="buy",
        confidence=round(confidence, 3),
        size=round(size, 4),
        scores=scores,
        reasons=reasons,
        flags={"rug_risk": False, "llm_failed": llm_failed},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )


# -- node 6 (optional, audit mode): async LLM second-opinion ----------------


def kol_audit_prompt(state: State) -> list[Message]:
    """Build the audit prompt — runs AFTER the rule-only sizing has set
    state.output. The auditor is reviewing a decision, not making one.
    """
    ctx = state.context
    ev = ctx.event
    t = ctx.token
    profile = state.scratch["kol_profile"]   # set by kol_quality
    d: Decision = state.output

    m, h, c, a, w, s = (
        t.market, t.holders, t.contract, t.activity, t.wallets, t.social
    )
    tw = s.twitter
    facts: list[str] = [
        f"DECISION (already returned to bot): action={d.action} size={d.size} "
        f"confidence={d.confidence}",
        f"Rule reasons: {'; '.join(d.reasons)}",
        "",
        f"KOL: {profile.name or ev.wallet[:8]} (tier {profile.tier}, "
        f"hit_rate {profile.hit_rate:.2f}, exit_pattern={profile.exit_pattern or '?'})",
        f"KOL bought {ev.sol_amount} SOL of {t.symbol} "
        f"({ev.block_age_seconds:.1f}s ago)",
        "",
        "TOKEN snapshot",
        f"  market: mcap=${m.mcap:,.0f} liq=${m.liquidity_usd:,.0f} "
        f"vol_1h=${m.volume_1h:,.0f}",
        f"  activity 5m: buys={a.buys_5m} sells={a.sells_5m} "
        f"buy_ratio={a.buy_ratio_5m:.2f}",
        f"  holders: count={h.count} top10={h.top10_pct:.0%} dev={h.dev_pct:.0%}",
        f"  contract: bundled={c.bundled_supply} dev_rug={c.dev_rug_history} "
        f"lp_burned={c.lp_burned} lp_locked={c.lp_locked}",
        f"  wallets: smart_buys={w.smart_wallet_buys} kol_count={w.kol_wallet_count} "
        f"snipers={w.sniper_wallet_count} bundlers={w.bundler_wallet_count}",
        f"  social: tw_followers={tw.followers} "
        f"mention_growth={tw.mention_growth_pct:+.0f}% "
        f"velocity={tw.velocity_tpm:.1f}tpm kol_buying_5m={s.kol_count_5m}",
    ]

    return [
        system(
            "You are a memecoin trading auditor reviewing a KOL copy-trade "
            "decision a rule-based bot ALREADY made. The trade is already "
            "executed (or about to be) — your verdict cannot stop it. Your "
            "job is to flag disagreement so the bot can learn:\n"
            "- Do you AGREE with the action and size?\n"
            "- What concrete concerns did the rule layer miss?\n"
            "Be honest. Disagree when warranted — this audit informs future "
            "rule tuning, NOT this trade. Output JSON matching the schema."
        ),
        user("Audit fact sheet:\n" + "\n".join(facts)),
    ]


async def _run_kol_audit(
    client: LLMClient,
    messages: list[Message],
    model: str | None,
) -> KOLAnalystVerdict:
    """Background coroutine — call the LLM, parse to KOLAnalystVerdict.

    Errors are swallowed into a flagged verdict so the bg task always
    completes — must never raise into the event loop and crash the bot.
    """
    try:
        return await structured_complete(
            client, messages, KOLAnalystVerdict, model=model
        )
    except Exception as exc:  # noqa: BLE001 — bg task must not propagate
        return KOLAnalystVerdict(
            approve=False,
            size_multiplier=0.0,
            confidence=0.0,
            concerns=[f"audit_failed: {type(exc).__name__}"],
            reasoning=str(exc)[:200],
        )


def make_kol_audit_dispatch(
    client: LLMClient,
    *,
    model: str | None = None,
    knowledge_pack: KnowledgePack | None = None,
):
    """Build the audit-dispatch node for KOL copy-trade audit mode.

    The decision is already in state.output (set by the sizing node).
    This node fires a background task that the bot can ``await`` later
    to get the audit verdict — typically writing it to DecisionLog for
    offline analysis. The hot path is NOT blocked.

    Task handle lands in ``state.scratch["kol_audit_task"]``.

    When ``knowledge_pack`` is provided, its system blocks are prepended
    to the audit prompt so the auditor sees the deployment playbook too.
    """
    pack_blocks: list[Message] = (
        knowledge_pack.system_blocks() if knowledge_pack is not None else []
    )

    def kol_audit_dispatch(state: State) -> None:
        # Only audit actual buys — skip / abort decisions aren't interesting.
        if state.output is None or state.output.action not in {"buy"}:
            state.scratch["kol_audit_skipped"] = True
            return

        base_msgs = kol_audit_prompt(state)
        messages = pack_blocks + base_msgs if pack_blocks else base_msgs
        task = asyncio.create_task(_run_kol_audit(client, messages, model))
        state.scratch["kol_audit_task"] = task
        # Mark decision so observers know an audit is in flight.
        state.output.flags["kol_audit_dispatched"] = True

    kol_audit_dispatch.__name__ = "kol_audit_dispatch"
    return kol_audit_dispatch
