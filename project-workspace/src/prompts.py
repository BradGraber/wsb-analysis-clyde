"""
AI prompt templates for GPT-4o-mini sentiment analysis of WSB comments.

This module provides the system prompt defining WSB communication context and
the user prompt template for injecting comment/post data into analysis requests.
"""

from typing import List, Optional, Union, Dict, Any


# System prompt defining WSB style, meme language, and analysis tasks (PRD E.2)
SYSTEM_PROMPT = """You are a financial sentiment analyzer specializing in WallStreetBets (WSB) content.
Your task is to analyze comments and extract structured trading signals.

WSB Communication Style:
WSB has a distinctive culture — learn to distinguish cultural humor from true sarcasm:

CULTURAL HUMOR (NOT sarcasm):
- Self-deprecating humor: "welp, there goes 27k", "my portfolio is dead"
- Loss porn celebration: celebrating losses, downplaying gains
- Meme language: "diamond hands" (hold), "paper hands" (sell), "tendies" (profits),
  "to the moon" (bullish), "GUH" (loss), "apes" (retail investors), "regarded" (self-censored)
- Exaggeration for effect: "TSLA to $10,000", "printing money"
- Joke disclaimers: "This is financial advice" (always ironic)

TRUE SARCASM (mark sarcasm_detected=true):
Sarcasm means the commenter's actual opinion is the OPPOSITE of what they literally say.
Only flag sarcasm when the commenter appears to express one direction but actually means the other.
- "Oh yeah, NVDA is definitely going to zero" (commenter is actually bullish)
- "Great idea buying calls at the top" (commenter thinks it was a bad decision)
- "Sure, a company with no revenue is a great investment" (commenter is bearish)
Test: Would flipping the literal meaning reveal the commenter's actual belief?

When sarcasm IS detected, set sentiment to what the commenter ACTUALLY means (the inverse).

Sentiment Classification (CRITICAL):
- bullish: Commenter predicts or believes a stock/market will go UP
- bearish: Commenter predicts or believes a stock/market will go DOWN
- neutral: NOT predictive — loss/gain reports, questions, general commentary, emotional
  reactions, humor without directional prediction, or ambiguous statements

Only assign bullish or bearish if the comment expresses a belief about future direction.

MARKET CONTEXT (when provided):
On days with significant market moves (>0.8% on major indexes), many comments will be
reactive — venting about losses, reporting current damage, or expressing frustration.
These are NOT predictive and should be classified as neutral.
Only classify as bullish/bearish if the commenter expresses a belief about FUTURE direction,
not just reacting to what already happened today.
Examples of reactive (neutral): "this market is trash", "my portfolio is dead today",
"how did you lose on puts on a day like this"
Examples of predictive (bearish): "I think there's a bigger dip coming", "SPY to 680 next week"

Your job:
1. Identify true sarcasm (inverse-meaning only) vs. WSB cultural humor
2. Extract ticker symbols mentioned (normalize to uppercase)
3. Determine sentiment (bullish/bearish only if predictive; otherwise neutral)
4. Identify if the comment contains substantive reasoning vs. hype
5. Assess confidence based on argument quality and author trust

Confidence Scoring Guidelines:
Base confidence: 0.5
Modifiers:
- Clear, direct statement: +0.2
- Substantive reasoning provided: +0.2
- High author trust (>0.7): +0.1
- True inverse-meaning sarcasm detected: -0.2
- Meme-heavy, no substance: -0.2
- Contradicts parent context: -0.1

Apply modifiers to the base, clamping result to [0.0, 1.0]."""


def format_parent_chain(parent_chain: List[Union[Dict[str, Any], Any]]) -> str:
    """
    Format parent chain as readable threaded context.

    Parent chain is ordered from deepest ancestor (root) to immediate parent
    (chronological reading order). Format shows thread hierarchy with arrows.
    Example: "Reply to trader456 (depth 0): 'Original comment...' -> Reply to user123 (depth 1): 'I think NVDA...'"

    Long parent bodies are truncated to ~200 characters to manage prompt token usage.

    Args:
        parent_chain: List of dict objects or ParentChainEntry dataclass objects.
                     Each entry must have: id, body, depth, author attributes/keys.
                     Input is reversed to show root-to-parent order.

    Returns:
        Formatted string suitable for AI prompt context. Empty string if no parents.
    """
    if not parent_chain:
        return ""

    parts = []
    # Reverse to show root (deepest ancestor) first, immediate parent last (chronological)
    for entry in reversed(parent_chain):
        # Support both dict access and attribute access (ParentChainEntry)
        if isinstance(entry, dict):
            body = entry['body']
            author = entry['author']
            depth = entry['depth']
        else:
            body = entry.body
            author = entry.author
            depth = entry.depth

        # Truncate long bodies to manage prompt tokens
        if len(body) > 200:
            body = body[:197] + "..."

        parts.append(f"Reply to {author} (depth {depth}): '{body}'")

    # Join with arrows to show thread flow
    return " -> ".join(parts)


def build_user_prompt(
    post_title: str,
    image_description: Optional[str],
    parent_chain_formatted: str,
    author: str,
    author_trust: float,
    comment_body: str,
    market_context: Optional[str] = None,
) -> str:
    """
    Build user prompt for GPT-4o-mini sentiment analysis.

    Template injects post title, optional market context, optional image analysis,
    parent chain context, author + trust score, and comment body. Includes JSON
    response structure and validation rules from PRD E.3.

    Args:
        post_title: Title of the post containing this comment
        image_description: GPT-4o-mini vision analysis of post image (None if no image)
        parent_chain_formatted: Pre-formatted parent chain string (from format_parent_chain)
        author: Reddit username of comment author
        author_trust: Historical trust score (0.0-1.0)
        comment_body: The comment text to analyze
        market_context: Pre-formatted market context string (None if flat day or unavailable)

    Returns:
        Formatted user prompt string ready for OpenAI API call
    """
    parent_context = parent_chain_formatted

    # Build prompt with conditional image context
    prompt_parts = [
        f'Analyze this WSB comment:\n\nPost: "{post_title}"'
    ]

    # Include market context if available (only on volatile days)
    if market_context:
        prompt_parts.append(f'\n{market_context}')

    # Only include image context if available
    if image_description:
        prompt_parts.append(f'\nPost Image Context (if available): "{image_description}"')

    # Add parent chain if exists
    if parent_context:
        prompt_parts.append(f'\nParent context (if reply):\n{parent_context}')

    # Add author and comment
    prompt_parts.append(
        f'\nComment by {author} (trust score: {author_trust:.2f}):\n"{comment_body}"'
    )

    # Add JSON response structure (PRD E.3)
    prompt_parts.append("""
Respond with this exact JSON structure:
{
  "tickers": ["TICKER1", "TICKER2"],
  "ticker_sentiments": ["bullish|bearish|neutral", "bullish|bearish|neutral"],
  "sentiment": "bullish|bearish|neutral",
  "sarcasm_detected": true|false,
  "has_reasoning": true|false,
  "confidence": 0.0-1.0,
  "reasoning_summary": "string or null"
}

Rules:
- ticker_sentiments is a flat array of sentiment strings, parallel to tickers (one per ticker)
- sentiment is the overall comment direction (for single-ticker, matches ticker_sentiments[0])
- reasoning_summary is null if has_reasoning is false""")

    return "\n".join(prompt_parts)
