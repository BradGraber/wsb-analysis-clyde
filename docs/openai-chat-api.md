# OpenAI Chat Completions API - Python SDK Reference

Focused reference for the OpenAI Python SDK covering chat completions, vision capabilities, JSON mode, and response handling.

## Table of Contents
- [Client Setup](#client-setup)
- [Chat Completions API](#chat-completions-api)
- [Message Format](#message-format)
- [Vision / Image Input](#vision--image-input)
- [Response Object Structure](#response-object-structure)
- [JSON Mode / Structured Output](#json-mode--structured-output)
- [Error Handling](#error-handling)
- [Token Usage Tracking](#token-usage-tracking)

---

## Client Setup

### Installation
```bash
pip install openai
```

### Initialize Client
```python
from openai import OpenAI

# Initialize with API key from environment variable OPENAI_API_KEY
client = OpenAI()

# Or explicitly pass API key
client = OpenAI(api_key="your-api-key-here")
```

**Environment Variable:**
```bash
export OPENAI_API_KEY="your-api-key-here"
```

---

## Chat Completions API

### Method: `client.chat.completions.create()`

Creates a model response for the given chat conversation.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model` | `str` | Yes | - | Model ID (e.g., `"gpt-4o-mini"`, `"gpt-4o"`) |
| `messages` | `list[dict]` | Yes | - | List of message objects with `role` and `content` |
| `temperature` | `float` | No | `1.0` | Sampling temperature (0.0 to 2.0). Higher = more random |
| `max_tokens` | `int` | No | `inf` | Maximum tokens to generate in the response |
| `response_format` | `dict` | No | `None` | Output format specification (see JSON Mode section) |
| `top_p` | `float` | No | `1.0` | Nucleus sampling parameter (0.0 to 1.0) |
| `n` | `int` | No | `1` | Number of chat completion choices to generate |
| `stop` | `str | list[str]` | No | `None` | Sequences where the API will stop generating tokens |
| `presence_penalty` | `float` | No | `0.0` | Penalty for new tokens based on presence (-2.0 to 2.0) |
| `frequency_penalty` | `float` | No | `0.0` | Penalty for new tokens based on frequency (-2.0 to 2.0) |

### Basic Example
```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"}
    ],
    temperature=0.7,
    max_tokens=150
)

print(response.choices[0].message.content)
```

---

## Message Format

Messages are represented as dictionaries with `role` and `content` keys.

### Roles

| Role | Description | Usage |
|------|-------------|-------|
| `system` | System instructions | Sets behavior/personality of the assistant |
| `user` | User message | Input from the end user |
| `assistant` | Assistant message | Previous responses or example responses |
| `developer` | Developer instructions | Alternative to system role (newer models) |

### Message Structure

**Text Message:**
```python
{
    "role": "user",
    "content": "Explain quantum computing in simple terms."
}
```

**Multi-part Content (for images):**
```python
{
    "role": "user",
    "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image_url", "image_url": {"url": "https://..."}}
    ]
}
```

### Example Conversation
```python
messages = [
    {"role": "system", "content": "You are a helpful coding assistant."},
    {"role": "user", "content": "How do I reverse a list in Python?"},
    {"role": "assistant", "content": "You can use list.reverse() or list[::-1]"},
    {"role": "user", "content": "Which is faster?"}
]

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages
)
```

---

## Vision / Image Input

GPT-4o and GPT-4o-mini models support image analysis. Images can be provided as URLs or base64-encoded data.

### Image URL Format

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image.jpg",
                        "detail": "high"  # or "low" or "auto"
                    }
                }
            ]
        }
    ]
)
```

### Base64 Encoded Images

```python
import base64

# Read and encode image
with open("image.jpg", "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

# Create message with base64 image
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image in detail."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high"
                    }
                }
            ]
        }
    ]
)
```

### Detail Parameter

The `detail` parameter controls image processing quality:

| Value | Description | Token Budget | Resolution |
|-------|-------------|--------------|------------|
| `"low"` | Fast, low-detail processing | 85 tokens | 512×512px |
| `"high"` | Detailed image understanding | Variable (higher) | Full resolution tiles |
| `"auto"` | Model decides based on image | Variable | Adaptive |

**Default:** `"auto"` if not specified

### Supported Image Formats
- JPEG
- PNG
- GIF
- WebP

**Maximum file size:** 20 MB

---

## Response Object Structure

### Response Type
`ChatCompletion` object

### Key Fields

```python
response = client.chat.completions.create(...)

# Access response fields
response.id                    # str: Unique completion ID
response.object                # str: "chat.completion"
response.created               # int: Unix timestamp
response.model                 # str: Model used
response.choices               # list[Choice]: Completion choices
response.usage                 # CompletionUsage: Token usage stats
```

### Choice Object

```python
choice = response.choices[0]

choice.index                   # int: Choice index (0 if n=1)
choice.message                 # ChatCompletionMessage: The message
choice.finish_reason           # str: Why generation stopped
choice.logprobs                # dict | None: Log probability info
```

### Message Object

```python
message = response.choices[0].message

message.role                   # str: "assistant"
message.content                # str: The response text
message.tool_calls             # list | None: Tool/function calls
message.function_call          # dict | None: (Deprecated)
```

### Finish Reasons

| Reason | Description |
|--------|-------------|
| `"stop"` | Natural stop point or stop sequence reached |
| `"length"` | Max tokens limit reached |
| `"tool_calls"` | Model called a tool/function |
| `"content_filter"` | Content filtered due to policy |
| `"function_call"` | (Deprecated) Function called |

### Complete Example

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say hello"}],
    max_tokens=50
)

# Extract content
content = response.choices[0].message.content
print(f"Response: {content}")

# Check finish reason
finish_reason = response.choices[0].finish_reason
if finish_reason == "length":
    print("Warning: Response truncated due to max_tokens limit")

# Check token usage
print(f"Tokens used: {response.usage.total_tokens}")
```

---

## JSON Mode / Structured Output

OpenAI supports two approaches for JSON responses: JSON mode and Structured Outputs with JSON Schema.

### JSON Mode (Simple)

Use `response_format` with `type: "json_object"` to ensure valid JSON output.

**Note:** You must include "JSON" in your system or user message prompt.

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant. Respond in JSON format."},
        {"role": "user", "content": "Analyze the sentiment of: 'I love this product!'"}
    ],
    response_format={"type": "json_object"}
)

# Parse JSON response
import json
result = json.loads(response.choices[0].message.content)
print(result)  # e.g., {"sentiment": "positive", "confidence": 0.95}
```

### Structured Outputs with JSON Schema

**Supported models:** `gpt-4o-mini`, `gpt-4o-mini-2024-07-18`, `gpt-4o-2024-08-06` and later

Use Pydantic models for type-safe structured outputs:

```python
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI()

class SentimentAnalysis(BaseModel):
    sentiment: str  # e.g., "positive", "negative", "neutral"
    confidence: float
    key_phrases: list[str]

# Use parse method for automatic JSON schema conversion
completion = client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "Analyze sentiment of user input."},
        {"role": "user", "content": "I love this product!"}
    ],
    response_format=SentimentAnalysis
)

# Access parsed object directly
result = completion.choices[0].message.parsed
print(f"Sentiment: {result.sentiment}")
print(f"Confidence: {result.confidence}")
print(f"Key phrases: {result.key_phrases}")
```

### Manual JSON Schema (Advanced)

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Analyze: 'Great product!'"}
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "sentiment_analysis",
            "schema": {
                "type": "object",
                "properties": {
                    "sentiment": {"type": "string"},
                    "confidence": {"type": "number"},
                    "key_phrases": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["sentiment", "confidence"],
                "additionalProperties": False
            },
            "strict": True
        }
    }
)
```

**Benefits of Structured Outputs:**
- Guaranteed schema adherence
- No hallucinated fields or invalid enum values
- Type safety with Pydantic
- Automatic parsing

---

## Error Handling

### Common Exception Classes

All errors inherit from `openai.APIError`.

| Exception | Status Code | Description |
|-----------|-------------|-------------|
| `AuthenticationError` | 401 | Invalid, expired, or revoked API key |
| `PermissionDeniedError` | 403 | Insufficient permissions |
| `NotFoundError` | 404 | Resource not found |
| `UnprocessableEntityError` | 422 | Invalid request parameters |
| `RateLimitError` | 429 | Rate limit exceeded (too many requests/tokens) |
| `InternalServerError` | 500+ | Server-side error |
| `APIConnectionError` | N/A | Network/connection failure |
| `APIError` | Any | Base class for all API errors |

### Error Handling Example

```python
from openai import OpenAI, APIError, RateLimitError, AuthenticationError

client = OpenAI()

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}]
    )
    print(response.choices[0].message.content)

except AuthenticationError as e:
    print(f"Authentication failed: {e}")
    # Check API key configuration

except RateLimitError as e:
    print(f"Rate limit exceeded: {e}")
    # Implement exponential backoff or reduce request rate

except APIConnectionError as e:
    print(f"Connection error: {e}")
    # Check network connectivity

except APIError as e:
    print(f"API error: {e}")
    # Handle general API errors

except Exception as e:
    print(f"Unexpected error: {e}")
```

### Retry Logic with Exponential Backoff

```python
import time
from openai import RateLimitError

def create_completion_with_retry(client, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"Rate limited. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise  # Re-raise on final attempt

# Usage
response = create_completion_with_retry(client, [
    {"role": "user", "content": "Hello"}
])
```

---

## Token Usage Tracking

### Usage Object

The `usage` field in the response provides token consumption details.

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Explain machine learning"}]
)

usage = response.usage

usage.prompt_tokens        # int: Tokens in input messages
usage.completion_tokens    # int: Tokens in generated response
usage.total_tokens         # int: Total tokens used (prompt + completion)
```

### Example: Track Token Usage

```python
def analyze_with_tracking(client, text):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Analyze sentiment."},
            {"role": "user", "content": text}
        ]
    )

    # Extract usage
    usage = response.usage
    print(f"Prompt tokens: {usage.prompt_tokens}")
    print(f"Completion tokens: {usage.completion_tokens}")
    print(f"Total tokens: {usage.total_tokens}")

    # Calculate cost (example pricing for gpt-4o-mini)
    # Input: $0.15 per 1M tokens, Output: $0.60 per 1M tokens
    input_cost = (usage.prompt_tokens / 1_000_000) * 0.15
    output_cost = (usage.completion_tokens / 1_000_000) * 0.60
    total_cost = input_cost + output_cost

    print(f"Estimated cost: ${total_cost:.6f}")

    return response.choices[0].message.content

# Usage
result = analyze_with_tracking(client, "I love this product!")
```

### Batch Tracking

```python
class TokenTracker:
    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def track_response(self, response):
        self.total_prompt_tokens += response.usage.prompt_tokens
        self.total_completion_tokens += response.usage.completion_tokens

    @property
    def total_tokens(self):
        return self.total_prompt_tokens + self.total_completion_tokens

    def report(self):
        print(f"Total prompt tokens: {self.total_prompt_tokens}")
        print(f"Total completion tokens: {self.total_completion_tokens}")
        print(f"Total tokens: {self.total_tokens}")

# Usage
tracker = TokenTracker()

for comment in comments:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": comment}]
    )
    tracker.track_response(response)

tracker.report()
```

---

## Complete Working Example

Putting it all together: analyze sentiment with vision, JSON output, error handling, and token tracking.

```python
import base64
import json
from openai import OpenAI, APIError, RateLimitError
from pydantic import BaseModel

# Initialize client
client = OpenAI()

# Define structured output
class SentimentResult(BaseModel):
    sentiment: str
    confidence: float
    key_elements: list[str]

def analyze_image_sentiment(image_path: str) -> dict:
    """Analyze sentiment from an image with robust error handling."""

    try:
        # Read and encode image
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Create chat completion with vision
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Analyze the sentiment conveyed in images. Return JSON."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What sentiment does this image convey?"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.7
        )

        # Extract and parse response
        content = response.choices[0].message.content
        result = json.loads(content)

        # Track token usage
        usage = response.usage
        print(f"Tokens used: {usage.total_tokens} "
              f"(prompt: {usage.prompt_tokens}, "
              f"completion: {usage.completion_tokens})")

        return result

    except RateLimitError:
        print("Rate limit exceeded. Please try again later.")
        return {"error": "rate_limit"}

    except APIError as e:
        print(f"API error: {e}")
        return {"error": "api_error"}

    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"error": "unknown"}

# Usage
result = analyze_image_sentiment("product_image.jpg")
print(json.dumps(result, indent=2))
```

---

## Reference Links

- [Chat Completions API Reference](https://platform.openai.com/docs/api-reference/chat)
- [Images and Vision Guide](https://platform.openai.com/docs/guides/images-vision)
- [Structured Outputs Guide](https://platform.openai.com/docs/guides/structured-outputs)
- [Error Codes Reference](https://platform.openai.com/docs/guides/error-codes)
- [OpenAI Python SDK (GitHub)](https://github.com/openai/openai-python)

---

*This reference covers the core features needed for chat completions with vision, JSON parsing, and production error handling. For complete API documentation, visit the official OpenAI platform documentation.*
