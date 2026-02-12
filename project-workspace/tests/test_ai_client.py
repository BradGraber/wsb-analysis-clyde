"""
Tests for OpenAI client with cost tracking (story-003-001).

Behavioral tests verifying OpenAI API integration, error handling,
and monthly cost tracking with $60 threshold warnings.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import os


class TestOpenAIClientInit:
    """Test OpenAI client initialization."""

    def test_client_requires_api_key_from_env(self):
        """OPENAI_API_KEY required from env; missing raises ValueError at init."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='OPENAI_API_KEY'):
                OpenAIClient()

    def test_client_initializes_with_valid_api_key(self):
        """Client initializes successfully with valid API key."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key-123'}):
            client = OpenAIClient()
            assert client is not None


class TestChatCompletionRequests:
    """Test chat completion API calls."""

    @pytest.mark.asyncio
    async def test_send_chat_completion_to_gpt4o_mini(self):
        """Sends to POST /v1/chat/completions with gpt-4o-mini."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = 'Test response'
                mock_response.usage.total_tokens = 150
                mock_response.usage.prompt_tokens = 100
                mock_response.usage.completion_tokens = 50

                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                client = OpenAIClient()
                result = await client.send_chat_completion(
                    system_prompt="You are a helpful assistant",
                    user_prompt="Test question"
                )

                # Verify called with correct model
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs['model'] == 'gpt-4o-mini'

    @pytest.mark.asyncio
    async def test_returns_raw_content_and_token_usage(self):
        """Returns raw response content + token usage."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = 'Response text'
                mock_response.usage.total_tokens = 200
                mock_response.usage.prompt_tokens = 120
                mock_response.usage.completion_tokens = 80

                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                client = OpenAIClient()
                result = await client.send_chat_completion("System", "User")

                assert result['content'] == 'Response text'
                assert result['usage']['total_tokens'] == 200
                assert result['usage']['prompt_tokens'] == 120
                assert result['usage']['completion_tokens'] == 80

    @pytest.mark.asyncio
    async def test_api_errors_caught_and_logged(self):
        """API errors caught and logged via structlog."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = Exception("API Error")
                mock_openai.return_value = mock_client

                with patch('structlog.get_logger') as mock_logger:
                    logger_instance = MagicMock()
                    mock_logger.return_value = logger_instance

                    client = OpenAIClient()

                    with pytest.raises(Exception):
                        await client.send_chat_completion("System", "User")

                    # Should log error
                    logger_instance.error.assert_called_once()


class TestCostTracking:
    """Test token usage and cost tracking."""

    @pytest.mark.asyncio
    async def test_token_usage_logged_per_call(self):
        """Token usage logged per API call."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = 'Response'
                mock_response.usage.total_tokens = 1000
                mock_response.usage.prompt_tokens = 600
                mock_response.usage.completion_tokens = 400

                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                with patch('structlog.get_logger') as mock_logger:
                    logger_instance = MagicMock()
                    mock_logger.return_value = logger_instance

                    client = OpenAIClient()
                    await client.send_chat_completion("System", "User")

                    # Should log token usage
                    assert logger_instance.info.called

    @pytest.mark.asyncio
    async def test_monthly_total_tracked(self):
        """Monthly total token usage tracked."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = 'Response'
                mock_response.usage.total_tokens = 5000

                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                client = OpenAIClient()

                # Make multiple calls
                await client.send_chat_completion("System", "User 1")
                await client.send_chat_completion("System", "User 2")

                # Should track cumulative usage
                assert client.monthly_tokens >= 10000

    @pytest.mark.asyncio
    async def test_warning_above_60_dollars(self):
        """Warning logged when monthly cost exceeds $60."""
        from src.ai_client import OpenAIClient

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = 'Response'
                # Massive token usage to exceed $60 (200M input @ $0.15/1M + 50M output @ $0.60/1M = $60.00)
                mock_response.usage.total_tokens = 250_000_000
                mock_response.usage.prompt_tokens = 200_000_000
                mock_response.usage.completion_tokens = 50_000_000

                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                with patch('structlog.get_logger') as mock_logger:
                    logger_instance = MagicMock()
                    mock_logger.return_value = logger_instance

                    client = OpenAIClient()
                    await client.send_chat_completion("System", "User")

                    # Should log warning about cost
                    logger_instance.warning.assert_called()

    @pytest.mark.asyncio
    async def test_monthly_reset_on_calendar_month_change(self):
        """Monthly total resets on calendar month change."""
        from src.ai_client import OpenAIClient
        from datetime import datetime

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = 'Response'
                mock_response.usage.total_tokens = 1000

                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                client = OpenAIClient()
                client.monthly_tokens = 10000
                client.current_month = (2026, 1)  # January

                # Simulate month change
                with patch('src.ai_client.datetime') as mock_dt:
                    mock_dt.now.return_value = datetime(2026, 2, 1)  # February

                    await client.send_chat_completion("System", "User")

                    # Should reset to just current call's tokens
                    assert client.monthly_tokens < 10000
