"""
LLM Reasoning Analyzer

Uses Claude (Anthropic) to reason through market fundamentals and identify opportunities
that require domain knowledge, logical reasoning, or nuanced understanding.

This analyzer is designed to be used sparingly (cost ~$0.01-0.05 per analysis) on:
- Markets where domain knowledge would help (legislation, sports rules, etc.)
- Markets flagged by other analyzers
- Markets with unusual or ambiguous descriptions
- High-value opportunities worth the API cost

Cost with Claude Haiku:
- Input: $0.25 per million tokens (~$0.001 per market)
- Output: $1.25 per million tokens (~$0.005 per market)
- Total: ~$0.006 per market analysis
"""

import os
import logging
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from analyzers.base import (
    BaseAnalyzer,
    Opportunity,
    OpportunityType,
    ConfidenceLevel,
    OpportunityStrength,
)

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("Anthropic SDK not available. LLMReasoningAnalyzer will be disabled.")


logger = logging.getLogger(__name__)


class LLMReasoningAnalyzer(BaseAnalyzer):
    """
    Analyzer that uses Claude to reason through market fundamentals.

    Provides domain expertise and logical reasoning that's hard to replicate
    with rule-based analyzers.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, kalshi_client=None):
        """
        Initialize the LLM reasoning analyzer.

        Args:
            config: Configuration dictionary
            kalshi_client: KalshiDataClient instance
        """
        super().__init__(config, kalshi_client)

        # Cost tracking
        self.total_api_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # Cache to avoid re-analyzing same markets
        self.analysis_cache: Dict[str, Dict] = {}

        # Configuration
        self.max_markets_per_cycle = self.config.get("max_markets_per_cycle", 5)
        self.model = self.config.get("model", "claude-3-5-haiku-20241022")  # Haiku for speed/cost
        self.min_market_value = self.config.get("min_market_value", 100)  # Min volume to analyze
        self.cache_ttl_seconds = self.config.get("cache_ttl_seconds", 3600)  # 1 hour cache

        # Market type priorities (which types to analyze first)
        self.priority_types = self.config.get("priority_types", [
            "legislation",
            "politics",
            "sports_rules",
            "weather",
            "economics",
            "celebrity",
        ])

        # Initialize Anthropic client
        if not ANTHROPIC_AVAILABLE:
            logger.error("Anthropic SDK not installed. Install with: pip install anthropic")
            self.client = None
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set. LLM analyzer will be disabled.")
            self.client = None
        else:
            self.client = Anthropic(api_key=api_key)
            logger.info("LLM Reasoning Analyzer initialized with Claude")

    def get_name(self) -> str:
        """Return analyzer name."""
        return "LLM Reasoning Analyzer"

    def get_description(self) -> str:
        """Return analyzer description."""
        return "Uses Claude AI to reason through market fundamentals and identify opportunities requiring domain knowledge"

    def _is_cache_valid(self, ticker: str) -> bool:
        """Check if cached analysis is still valid."""
        if ticker not in self.analysis_cache:
            return False

        cached = self.analysis_cache[ticker]
        age_seconds = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
        return age_seconds < self.cache_ttl_seconds

    def _classify_market_type(self, market: Dict[str, Any]) -> str:
        """
        Classify market type to prioritize analysis.

        Returns:
            Market type string (e.g., "legislation", "sports_rules", "general")
        """
        title = market.get("title", "").lower()
        ticker = market.get("ticker", "").lower()

        # Legislation/politics
        if any(word in title for word in ["bill", "law", "congress", "senate", "house", "legislation", "vote", "pass"]):
            return "legislation"
        if any(word in title for word in ["election", "president", "governor", "mayor", "political"]):
            return "politics"

        # Sports with rules
        if any(word in title for word in ["championship", "playoff", "tournament", "qualify", "seed"]):
            return "sports_rules"

        # Weather
        if any(word in title for word in ["temperature", "rain", "snow", "weather", "storm", "hurricane"]):
            return "weather"

        # Economics
        if any(word in title for word in ["gdp", "inflation", "rate", "economic", "unemployment", "market"]):
            return "economics"

        # Celebrity/pop culture
        if any(word in title for word in ["time person", "oscar", "grammy", "emmy", "award", "celebrity"]):
            return "celebrity"

        return "general"

    def _create_analysis_prompt(self, market: Dict[str, Any]) -> str:
        """
        Create the prompt for Claude to analyze the market.

        Args:
            market: Market dictionary

        Returns:
            Prompt string
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "No title")
        subtitle = market.get("subtitle", "")
        current_price = market.get("last_price", 50)
        volume = market.get("volume", 0)
        open_interest = market.get("open_interest", 0)
        expiration = market.get("close_time", "Unknown")

        # Build context
        context_parts = []
        if subtitle:
            context_parts.append(f"Subtitle: {subtitle}")
        context_parts.append(f"Current price: {current_price}¢ (implies {current_price}% probability)")
        context_parts.append(f"Volume: {volume} contracts")
        if open_interest:
            context_parts.append(f"Open interest: {open_interest}")
        context_parts.append(f"Expiration: {expiration}")

        context = "\n".join(context_parts)

        prompt = f"""You are an expert analyst evaluating a prediction market. Analyze this market and provide insights:

**Market:** {title}

**Details:**
{context}

**Your task:**
1. Analyze the fundamentals: What base rates, domain knowledge, or logical reasoning is relevant?
2. Evaluate the current price: Is {current_price}¢ reasonable given the fundamentals?
3. Identify any edge cases, ambiguities, or resolution risks
4. Estimate a fair value and your confidence level

**Response format (JSON):**
{{
    "fair_value_cents": <number between 0-100>,
    "confidence": "<LOW|MEDIUM|HIGH>",
    "reasoning": "<concise explanation of your analysis>",
    "edge_cents": <current_price - fair_value>,
    "suggested_side": "<yes|no|none>",
    "key_factors": ["<factor 1>", "<factor 2>", ...],
    "risk_factors": ["<risk 1>", "<risk 2>", ...],
    "domain_knowledge": "<relevant domain expertise applied>"
}}

**Important:**
- Be contrarian if the market is clearly mispriced
- Use your knowledge of rules, procedures, base rates, etc.
- Consider resolution criteria ambiguities
- Focus on factors that typical traders might miss
- Be honest about uncertainty (LOW confidence when appropriate)

Respond with ONLY the JSON, no additional text."""

        return prompt

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse the LLM's JSON response.

        Args:
            response_text: Raw response from Claude

        Returns:
            Parsed response dictionary or None if parsing fails
        """
        try:
            # Extract JSON from response (in case there's extra text)
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            if start_idx == -1 or end_idx == 0:
                logger.error("No JSON found in LLM response")
                return None

            json_str = response_text[start_idx:end_idx]
            parsed = json.loads(json_str)

            # Validate required fields
            required_fields = ["fair_value_cents", "confidence", "reasoning", "suggested_side"]
            if not all(field in parsed for field in required_fields):
                logger.error(f"LLM response missing required fields: {parsed}")
                return None

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response text: {response_text}")
            return None

    def _analyze_market_with_llm(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyze a single market using Claude.

        Args:
            market: Market dictionary

        Returns:
            Analysis dictionary or None if analysis fails
        """
        if not self.client:
            return None

        ticker = market.get("ticker", "UNKNOWN")

        # Check cache first
        if self._is_cache_valid(ticker):
            logger.debug(f"Using cached analysis for {ticker}")
            return self.analysis_cache[ticker]["analysis"]

        try:
            prompt = self._create_analysis_prompt(market)

            logger.debug(f"Analyzing {ticker} with Claude...")

            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Track usage
            self.total_api_calls += 1
            self.total_input_tokens += message.usage.input_tokens
            self.total_output_tokens += message.usage.output_tokens

            # Log costs (approximate)
            input_cost = (message.usage.input_tokens / 1_000_000) * 0.25  # $0.25 per M tokens
            output_cost = (message.usage.output_tokens / 1_000_000) * 1.25  # $1.25 per M tokens
            total_cost = input_cost + output_cost

            logger.info(f"[LLM] {ticker}: {message.usage.input_tokens} in, {message.usage.output_tokens} out (~${total_cost:.4f})")

            # Parse response
            response_text = message.content[0].text
            analysis = self._parse_llm_response(response_text)

            if analysis:
                # Cache the result
                self.analysis_cache[ticker] = {
                    "analysis": analysis,
                    "timestamp": datetime.now(timezone.utc)
                }

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {ticker} with LLM: {e}")
            return None

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets using LLM reasoning.

        Args:
            markets: List of market dictionaries

        Returns:
            List of opportunities
        """
        if not self.client:
            logger.warning("LLM client not available, skipping analysis")
            return []

        opportunities = []

        # Filter markets worth analyzing
        candidates = []
        for market in markets:
            volume = market.get("volume", 0)
            if volume < self.min_market_value:
                continue

            ticker = market.get("ticker", "")
            market_type = self._classify_market_type(market)

            # Prioritize certain types
            priority = 0
            if market_type in self.priority_types:
                priority = self.priority_types.index(market_type)
            else:
                priority = len(self.priority_types)  # Lower priority for general

            candidates.append((priority, market_type, market))

        # Sort by priority and limit
        candidates.sort(key=lambda x: x[0])
        candidates = candidates[:self.max_markets_per_cycle]

        if not candidates:
            logger.info(f"LLMReasoningAnalyzer: No markets meet criteria for analysis")
            return []

        logger.info(f"LLMReasoningAnalyzer: Analyzing {len(candidates)} markets")

        # Analyze each candidate
        for priority, market_type, market in candidates:
            ticker = market.get("ticker", "UNKNOWN")
            title = market.get("title", "No title")
            current_price = market.get("last_price", 50)

            logger.info(f"[LLM] Analyzing {ticker} (type: {market_type})")

            analysis = self._analyze_market_with_llm(market)

            if not analysis:
                continue

            # Extract analysis results
            fair_value = analysis.get("fair_value_cents", current_price)
            edge_cents = abs(current_price - fair_value)
            suggested_side = analysis.get("suggested_side", "none")
            reasoning = analysis.get("reasoning", "")
            confidence_str = analysis.get("confidence", "MEDIUM").upper()

            # Map confidence string to enum
            confidence_map = {
                "LOW": ConfidenceLevel.LOW,
                "MEDIUM": ConfidenceLevel.MEDIUM,
                "HIGH": ConfidenceLevel.HIGH,
            }
            confidence = confidence_map.get(confidence_str, ConfidenceLevel.MEDIUM)

            # Only create opportunity if there's meaningful edge and a suggested side
            if suggested_side != "none" and edge_cents >= 5:
                # Determine strength based on edge and confidence
                if confidence == ConfidenceLevel.HIGH and edge_cents >= 15:
                    strength = OpportunityStrength.HARD
                elif edge_cents >= 10:
                    strength = OpportunityStrength.HARD
                else:
                    strength = OpportunityStrength.SOFT

                # Build detailed reasoning
                key_factors = analysis.get("key_factors", [])
                risk_factors = analysis.get("risk_factors", [])
                domain_knowledge = analysis.get("domain_knowledge", "")

                detailed_reasoning = f"{reasoning}\n\n"
                if key_factors:
                    detailed_reasoning += f"Key factors: {', '.join(key_factors)}\n"
                if domain_knowledge:
                    detailed_reasoning += f"Domain knowledge: {domain_knowledge}\n"
                if risk_factors:
                    detailed_reasoning += f"Risks: {', '.join(risk_factors)}"

                opp = Opportunity(
                    opportunity_type=OpportunityType.MISPRICING,
                    confidence=confidence,
                    strength=strength,
                    market_tickers=[ticker],
                    market_titles=[title],
                    current_prices={ticker: current_price},
                    estimated_edge_cents=edge_cents,
                    estimated_edge_percent=(edge_cents / fair_value * 100) if fair_value > 0 else 0,
                    reasoning=detailed_reasoning,
                    additional_data={
                        "llm_fair_value": fair_value,
                        "llm_confidence": confidence_str,
                        "llm_suggested_side": suggested_side,
                        "market_type": market_type,
                        "analysis_method": "claude_reasoning",
                    },
                    suggested_side=suggested_side
                )

                opportunities.append(opp)

                logger.info(
                    f"[LLM] {ticker}: Fair value {fair_value}¢ vs {current_price}¢ "
                    f"(edge: {edge_cents:.1f}¢, {confidence_str}, suggest: {suggested_side})"
                )

        # Log total costs
        if self.total_api_calls > 0:
            total_cost = (self.total_input_tokens / 1_000_000) * 0.25 + (self.total_output_tokens / 1_000_000) * 1.25
            logger.info(
                f"LLMReasoningAnalyzer session stats: {self.total_api_calls} calls, "
                f"{self.total_input_tokens} input tokens, {self.total_output_tokens} output tokens "
                f"(~${total_cost:.4f} total)"
            )

        logger.info(f"LLMReasoningAnalyzer found {len(opportunities)} opportunities out of {len(candidates)} markets")

        return opportunities
