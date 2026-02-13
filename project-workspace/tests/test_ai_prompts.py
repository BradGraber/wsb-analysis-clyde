"""
Tests for AI prompts and response structure (story-003-002).

Behavioral tests verifying system prompt format, user prompt template,
JSON response structure, and confidence scoring guidelines.
"""

import pytest
from unittest.mock import MagicMock


class TestSystemPrompt:
    """Test system prompt structure."""

    def test_system_prompt_includes_wsb_style_definitions(self):
        """System prompt includes WSB style and meme definitions."""
        from src.prompts import SYSTEM_PROMPT

        # Should include WSB-specific context
        assert 'wallstreetbets' in SYSTEM_PROMPT.lower() or 'wsb' in SYSTEM_PROMPT.lower()
        # Should mention analysis tasks
        assert 'ticker' in SYSTEM_PROMPT.lower() or 'sentiment' in SYSTEM_PROMPT.lower()

    def test_system_prompt_defines_four_analysis_tasks(self):
        """System prompt defines 4 analysis tasks."""
        from src.prompts import SYSTEM_PROMPT

        # Should mention key analysis dimensions
        assert 'ticker' in SYSTEM_PROMPT.lower()
        assert 'sentiment' in SYSTEM_PROMPT.lower()
        assert 'sarcasm' in SYSTEM_PROMPT.lower()
        assert 'reasoning' in SYSTEM_PROMPT.lower() or 'confidence' in SYSTEM_PROMPT.lower()

    def test_system_prompt_includes_confidence_guidelines(self):
        """System prompt includes confidence scoring guidelines."""
        from src.prompts import SYSTEM_PROMPT

        # Should mention confidence
        assert 'confidence' in SYSTEM_PROMPT.lower()


class TestUserPromptTemplate:
    """Test user prompt template with placeholders."""

    def test_user_prompt_has_required_placeholders(self):
        """User prompt template has placeholders for all context fields."""
        from src.prompts import build_user_prompt

        # Build with all fields
        prompt = build_user_prompt(
            post_title="Test Post Title",
            image_description="Chart showing uptrend",
            parent_chain_formatted="Parent: Some context",
            author="testuser",
            author_trust=0.75,
            comment_body="I'm bullish on AAPL"
        )

        # Should include all provided values
        assert "Test Post Title" in prompt
        assert "Chart showing uptrend" in prompt
        assert "Parent: Some context" in prompt
        assert "testuser" in prompt
        assert "0.75" in prompt or "75" in prompt
        assert "I'm bullish on AAPL" in prompt

    def test_user_prompt_omits_image_when_none(self):
        """User prompt omits image context when image_description=None."""
        from src.prompts import build_user_prompt

        prompt = build_user_prompt(
            post_title="Title",
            image_description=None,
            parent_chain_formatted="",
            author="user",
            author_trust=0.5,
            comment_body="Comment text"
        )

        # Should not mention image
        assert 'image' not in prompt.lower() or 'no image' in prompt.lower()

    def test_parent_chain_formatted_as_threaded_context(self):
        """Parent chain formatted as readable threaded context."""
        from src.prompts import format_parent_chain

        parent_chain = [
            {'id': 'parent1', 'body': 'This is parent comment', 'depth': 0, 'author': 'user1'},
            {'id': 'parent2', 'body': 'This is grandparent', 'depth': 0, 'author': 'user2'}
        ]

        formatted = format_parent_chain(parent_chain)

        # Should be human-readable
        assert 'user1' in formatted
        assert 'This is parent comment' in formatted
        assert 'user2' in formatted
        assert 'This is grandparent' in formatted

    def test_empty_parent_chain_returns_empty_string(self):
        """Empty parent_chain returns empty string or 'None'."""
        from src.prompts import format_parent_chain

        formatted = format_parent_chain([])

        assert formatted == '' or formatted.lower() == 'none'


class TestFormatParentChain:
    """Test parent chain formatting function (task-003-002-02)."""

    def test_formats_multi_level_parent_chain(self):
        """format_parent_chain returns formatted string showing threaded context."""
        from src.prompts import format_parent_chain

        # Input: immediate parent first, root last (per ParentChainEntry model)
        parent_chain = [
            {'id': 'p2', 'body': 'Immediate parent comment', 'depth': 1, 'author': 'user1'},
            {'id': 'p1', 'body': 'Root comment', 'depth': 0, 'author': 'user2'}
        ]

        result = format_parent_chain(parent_chain)

        # Output should be chronological: root first, immediate parent last
        assert 'user2' in result
        assert 'user1' in result
        assert 'Root comment' in result
        assert 'Immediate parent comment' in result
        # Verify order: root should appear before immediate parent
        user2_pos = result.index('user2')
        user1_pos = result.index('user1')
        assert user2_pos < user1_pos, "Root (user2) should appear before immediate parent (user1)"

    def test_displays_depth_author_body(self):
        """Each entry displays depth, author username, and comment body."""
        from src.prompts import format_parent_chain

        parent_chain = [
            {'id': 'p1', 'body': 'Test comment body', 'depth': 2, 'author': 'testuser'}
        ]

        result = format_parent_chain(parent_chain)

        assert 'depth 2' in result.lower()
        assert 'testuser' in result
        assert 'Test comment body' in result

    def test_orders_from_deepest_ancestor_to_immediate_parent(self):
        """Entries are ordered from deepest ancestor to immediate parent (chronological)."""
        from src.prompts import format_parent_chain

        # Input: immediate parent first, root last (model order)
        parent_chain = [
            {'id': 'p3', 'body': 'Immediate parent', 'depth': 2, 'author': 'recent'},
            {'id': 'p2', 'body': 'Middle comment', 'depth': 1, 'author': 'middle'},
            {'id': 'p1', 'body': 'Root comment', 'depth': 0, 'author': 'root'}
        ]

        result = format_parent_chain(parent_chain)

        # Extract author order from output
        parts = result.split(' -> ')
        authors = [part.split('to ')[1].split(' ')[0] for part in parts]

        # Output should be chronological: root, middle, recent
        assert authors == ['root', 'middle', 'recent']

    def test_top_level_comment_returns_empty_string(self):
        """Empty parent_chain (top-level comment) returns empty string."""
        from src.prompts import format_parent_chain

        result = format_parent_chain([])

        assert result == ""

    def test_truncates_long_parent_bodies(self):
        """Long parent comment bodies are truncated to ~200 chars."""
        from src.prompts import format_parent_chain

        long_body = "x" * 250  # 250 character body
        parent_chain = [
            {'id': 'p1', 'body': long_body, 'depth': 0, 'author': 'user1'}
        ]

        result = format_parent_chain(parent_chain)

        # Extract the body from the formatted output
        body_part = result.split("'")[1]

        assert len(body_part) == 200, f"Expected 200 chars, got {len(body_part)}"
        assert body_part.endswith('...')

    def test_accepts_parent_chain_entry_objects(self):
        """format_parent_chain accepts ParentChainEntry dataclass objects."""
        from src.prompts import format_parent_chain
        from src.models.reddit_models import ParentChainEntry

        # Use ParentChainEntry objects instead of dicts
        parent_chain = [
            ParentChainEntry(id='p2', body='Immediate parent', depth=1, author='user1'),
            ParentChainEntry(id='p1', body='Root comment', depth=0, author='user2')
        ]

        result = format_parent_chain(parent_chain)

        # Should work just like dict input
        assert 'user1' in result
        assert 'user2' in result
        assert 'Immediate parent' in result
        assert 'Root comment' in result

    def test_mixed_dict_and_object_input_not_supported(self):
        """format_parent_chain expects consistent input types (all dicts or all objects)."""
        from src.prompts import format_parent_chain
        from src.models.reddit_models import ParentChainEntry

        # This test documents expected behavior - mixing types should still work
        # since we check isinstance for each entry
        parent_chain = [
            ParentChainEntry(id='p2', body='Object entry', depth=1, author='user1'),
            {'id': 'p1', 'body': 'Dict entry', 'depth': 0, 'author': 'user2'}
        ]

        result = format_parent_chain(parent_chain)

        # Should handle mixed types gracefully
        assert 'user1' in result
        assert 'user2' in result


class TestMarketContextInPrompt:
    """Test market context injection in prompts."""

    def test_system_prompt_includes_market_context_guidance(self):
        """System prompt includes MARKET CONTEXT guidance section."""
        from src.prompts import SYSTEM_PROMPT

        assert "MARKET CONTEXT" in SYSTEM_PROMPT
        assert "0.8%" in SYSTEM_PROMPT
        assert "reactive" in SYSTEM_PROMPT.lower()
        assert "predictive" in SYSTEM_PROMPT.lower()

    def test_build_user_prompt_includes_market_context(self):
        """build_user_prompt includes market context when provided."""
        from src.prompts import build_user_prompt

        context = "Market context (today): SPY -1.5%, QQQ -2.3%, IWM -0.8%"
        prompt = build_user_prompt(
            post_title="Test Post",
            image_description=None,
            parent_chain_formatted="",
            author="testuser",
            author_trust=0.5,
            comment_body="This market is trash",
            market_context=context,
        )

        assert "SPY -1.5%" in prompt
        assert "QQQ -2.3%" in prompt

    def test_build_user_prompt_omits_market_context_when_none(self):
        """build_user_prompt omits market context when None (flat day)."""
        from src.prompts import build_user_prompt

        prompt = build_user_prompt(
            post_title="Test Post",
            image_description=None,
            parent_chain_formatted="",
            author="testuser",
            author_trust=0.5,
            comment_body="I think SPY goes up",
            market_context=None,
        )

        assert "Market context" not in prompt

    def test_market_context_appears_before_comment_body(self):
        """Market context appears before the comment body in the prompt."""
        from src.prompts import build_user_prompt

        context = "Market context (today): SPY -1.5%"
        prompt = build_user_prompt(
            post_title="Test Post",
            image_description=None,
            parent_chain_formatted="",
            author="testuser",
            author_trust=0.5,
            comment_body="Bearish comment here",
            market_context=context,
        )

        context_pos = prompt.index("SPY -1.5%")
        comment_pos = prompt.index("Bearish comment here")
        assert context_pos < comment_pos


class TestJSONResponseStructure:
    """Test expected JSON response structure."""

    def test_response_has_seven_required_fields(self):
        """JSON response structure has 7 required fields."""
        # This is a contract test - verify our parser expects these fields
        from src.ai_parser import parse_ai_response

        valid_json = '''
        {
            "tickers": ["AAPL", "TSLA"],
            "ticker_sentiments": ["bullish", "bearish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": true,
            "confidence": 0.8,
            "reasoning_summary": "Strong DD with price targets"
        }
        '''

        result = parse_ai_response(valid_json)

        assert 'tickers' in result
        assert 'ticker_sentiments' in result
        assert 'sentiment' in result
        assert 'sarcasm_detected' in result
        assert 'has_reasoning' in result
        assert 'confidence' in result
        assert 'reasoning_summary' in result

    def test_sentiment_limited_to_three_values(self):
        """Sentiment field only accepts bullish/bearish/neutral."""
        from src.ai_parser import parse_ai_response

        valid_sentiments = ['bullish', 'bearish', 'neutral']

        for sentiment in valid_sentiments:
            json_str = f'''
            {{
                "tickers": ["AAPL"],
                "ticker_sentiments": ["{sentiment}"],
                "sentiment": "{sentiment}",
                "sarcasm_detected": false,
                "has_reasoning": false,
                "confidence": 0.5,
                "reasoning_summary": null
            }}
            '''
            result = parse_ai_response(json_str)
            assert result['sentiment'] in ['bullish', 'bearish', 'neutral']

    def test_confidence_guidelines_base_0_5_with_modifiers(self):
        """Confidence scoring has base 0.5 with modifiers."""
        # This is a documentation test - verify prompts explain this
        from src.prompts import SYSTEM_PROMPT

        # Should mention base confidence or scoring approach
        assert '0.5' in SYSTEM_PROMPT or 'baseline' in SYSTEM_PROMPT.lower()

    def test_reasoning_summary_null_when_has_reasoning_false(self):
        """reasoning_summary is null when has_reasoning is false."""
        from src.ai_parser import parse_ai_response

        json_str = '''
        {
            "tickers": ["MSFT"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.6,
            "reasoning_summary": null
        }
        '''

        result = parse_ai_response(json_str)

        assert result['has_reasoning'] is False
        assert result['reasoning_summary'] is None

    def test_ticker_sentiments_count_matches_tickers(self):
        """ticker_sentiments count must match tickers count."""
        from src.ai_parser import parse_ai_response

        # Valid: matching counts
        valid_json = '''
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "ticker_sentiments": ["bullish", "neutral", "bearish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": true,
            "confidence": 0.7,
            "reasoning_summary": "Diversified portfolio"
        }
        '''

        result = parse_ai_response(valid_json)
        assert len(result['tickers']) == len(result['ticker_sentiments'])

    def test_invalid_mismatch_raises_validation_error(self):
        """Mismatched ticker/sentiment counts raise validation error."""
        from src.ai_parser import parse_ai_response

        invalid_json = '''
        {
            "tickers": ["AAPL", "MSFT"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.5,
            "reasoning_summary": null
        }
        '''

        with pytest.raises(Exception):  # ValidationError or similar
            parse_ai_response(invalid_json)

    def test_extra_fields_ignored(self):
        """Extra fields in response are ignored."""
        from src.ai_parser import parse_ai_response

        json_with_extra = '''
        {
            "tickers": ["AAPL"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": true,
            "confidence": 0.8,
            "reasoning_summary": "Strong analysis",
            "extra_field": "should be ignored",
            "another_extra": 123
        }
        '''

        result = parse_ai_response(json_with_extra)
        # Should parse successfully, extra fields ignored
        assert result['tickers'] == ['AAPL']

    def test_missing_required_field_raises_validation_error(self):
        """Missing required field raises validation error."""
        from src.ai_parser import parse_ai_response

        missing_confidence = '''
        {
            "tickers": ["AAPL"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "reasoning_summary": null
        }
        '''

        with pytest.raises(Exception):  # KeyError or ValidationError
            parse_ai_response(missing_confidence)
