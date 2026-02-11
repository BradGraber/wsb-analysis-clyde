# PRAW (Python Reddit API Wrapper) Reference

This document covers the PRAW library features needed for fetching Reddit posts and comments from r/wallstreetbets using OAuth2 authentication.

**PRAW Version:** 7.7.1
**Documentation:** https://praw.readthedocs.io/en/stable/

---

## 1. Authentication Setup

### Reddit Instance with OAuth2

Create a Reddit instance using OAuth2 credentials obtained from Reddit's developer portal.

**Required Parameters:**
- `client_id` (str): Your application's unique identifier (14+ character string from Reddit app preferences)
- `client_secret` (str): Your application's secret key (27+ character string)
- `user_agent` (str): Descriptive identifier for your application (format: "appname by u/username")
- `username` (str): Reddit account username (optional for read-only access)
- `password` (str): Reddit account password (optional for read-only access)

**Example:**
```python
import praw

reddit = praw.Reddit(
    client_id="SI8pN3DSbt0zor",
    client_secret="xaxkj7HNh8kwg8e5t4m6KvSrbTI",
    user_agent="testscript by u/fakebot3",
    username="fakebot3",
    password="your_password"
)

# Verify authentication
print(reddit.user.me())
```

**Read-Only Access (No User Context):**
```python
reddit = praw.Reddit(
    client_id="your_client_id",
    client_secret="your_client_secret",
    user_agent="wsb-analyzer by u/yourname"
)
```

**Using Refresh Tokens (Recommended for Production):**
```python
reddit = praw.Reddit(
    client_id="SI8pN3DSbt0zor",
    client_secret="xaxkj7HNh8kwg8e5t4m6KvSrbTI",
    refresh_token="WeheY7PwgeCZj4S3QgUcLhKE5S2s4eAYdxM",
    user_agent="testscript by u/fakebot3"
)
```

---

## 2. Fetching Hot Posts from a Subreddit

### Subreddit.hot()

Retrieves a listing generator for hot posts from a subreddit, ordered by current popularity.

**Method Signature:**
```python
subreddit.hot(**generator_kwargs: str | int | Dict[str, str]) → Iterator[Submission]
```

**Parameters:**
- `limit` (int, optional): Maximum number of submissions to return. Default is 100. Use `None` for unlimited.
- Additional pagination parameters supported by `ListingGenerator`

**Return Type:** `ListingGenerator` - An iterator that yields `Submission` objects

**Examples:**
```python
# Fetch top 25 hot posts from r/wallstreetbets
subreddit = reddit.subreddit("wallstreetbets")
for submission in subreddit.hot(limit=25):
    print(submission.title)

# Fetch all hot posts (careful with API rate limits)
for submission in subreddit.hot(limit=None):
    print(submission.title)

# Access specific subreddit
reddit.subreddit("wallstreetbets").hot(limit=50)
```

---

## 3. Submission Model

Represents a Reddit post. Key attributes for post metadata:

### Core Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | str | The title of the submission |
| `selftext` | str | The submission's body text (empty string for link posts) |
| `url` | str | The URL the submission links to, or permalink if a self-post |
| `score` | int | Net voting score (upvotes minus downvotes) |
| `num_comments` | int | Total count of comments on the submission |
| `created_utc` | int | Unix timestamp when the submission was created |

### Additional Useful Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | str | The submission's unique identifier |
| `author` | Redditor | The submission's author (or None if deleted) |
| `permalink` | str | Reddit-relative URL for the submission |
| `comments` | CommentForest | The submission's comment forest |

**Example:**
```python
for submission in subreddit.hot(limit=10):
    print(f"Title: {submission.title}")
    print(f"Score: {submission.score}")
    print(f"Comments: {submission.num_comments}")
    print(f"URL: {submission.url}")
    print(f"Posted: {submission.created_utc}")
    print(f"Body: {submission.selftext[:100]}")  # First 100 chars
    print("---")
```

---

## 4. Comment Model

Represents a Reddit comment. Key attributes for comment metadata:

### Core Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `body` | str | The comment's content in Markdown format |
| `author` | Redditor | The comment's author (or None if deleted) |
| `score` | int | Net voting score (upvotes minus downvotes) |
| `created_utc` | int | Unix timestamp when the comment was created |
| `parent_id` | str | ID of parent comment (prefixed with `t1_`) or submission (prefixed with `t3_`) for top-level comments |
| `depth` | int | Nesting level in the comment tree (0 for top-level) |

### Additional Useful Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | str | The comment's unique identifier |
| `permalink` | str | Reddit-relative URL for the comment |
| `replies` | CommentForest | Nested replies to this comment |
| `is_submitter` | bool | Whether the author is the submission author (OP) |

**Example:**
```python
submission = reddit.submission(id="abc123")
for comment in submission.comments.list():
    print(f"Author: {comment.author}")
    print(f"Score: {comment.score}")
    print(f"Depth: {comment.depth}")
    print(f"Body: {comment.body[:100]}")
    print(f"Posted: {comment.created_utc}")
    print(f"Parent: {comment.parent_id}")
    print("---")
```

---

## 5. CommentForest - Flattening and Traversing Comments

The `CommentForest` class manages hierarchical comment structures. Access it via `submission.comments`.

### replace_more()

Resolves `MoreComments` placeholders by fetching additional comments. Must be called before accessing all comments.

**Method Signature:**
```python
replace_more(*, limit: int | None = 32, threshold: int = 0) → List[MoreComments]
```

**Parameters:**
- `limit` (int or None): Maximum `MoreComments` instances to resolve (default: 32)
  - `0`: Remove all `MoreComments` without fetching
  - `None`: Replace all `MoreComments` until none remain
  - `32`: Default limit per call
- `threshold` (int): Minimum child count required to replace a `MoreComments` instance (default: 0)

**Returns:** List of unresolved `MoreComments` instances

**Important Notes:**
- Each replacement triggers an API call (rate limit considerations)
- Each replacement discovers at most 100 new comments
- Raises `prawcore.TooManyRequests` when called concurrently
- Calling again after refresh raises `DuplicateReplaceException`

**Examples:**
```python
# Replace up to 32 MoreComments instances (default)
submission.comments.replace_more()

# Replace all MoreComments (may take many API calls)
submission.comments.replace_more(limit=None)

# Remove all MoreComments without fetching
submission.comments.replace_more(limit=0)

# Only replace MoreComments with 10+ children
submission.comments.replace_more(limit=None, threshold=10)
```

### list()

Returns a flattened list of all comments in the forest.

**Method Signature:**
```python
list() → List[Comment | MoreComments]
```

**Return Type:** List containing `Comment` and potentially `MoreComments` objects

**Important Notes:**
- May include `MoreComments` instances if `replace_more()` hasn't been called
- Converts tree structure into a flat list
- Preserves comment order (breadth-first traversal)

**Example:**
```python
# Flatten comment tree
submission.comments.replace_more(limit=None)
all_comments = submission.comments.list()

print(f"Total comments: {len(all_comments)}")
for comment in all_comments:
    print(f"[Depth {comment.depth}] {comment.body[:50]}")
```

---

## 6. Common Patterns

### Fetching Top Comments by Score

```python
# Get submission
submission = reddit.submission(id="abc123")

# Replace MoreComments
submission.comments.replace_more(limit=0)  # Fast: remove without fetching

# Flatten and sort by score
all_comments = submission.comments.list()
top_comments = sorted(all_comments, key=lambda c: c.score, reverse=True)

# Get top 10
for comment in top_comments[:10]:
    print(f"Score: {comment.score} | {comment.body[:100]}")
```

### Iterating Comments with Depth Limit

```python
submission.comments.replace_more(limit=None)

for comment in submission.comments.list():
    if comment.depth <= 2:  # Only top-level and first-level replies
        indent = "  " * comment.depth
        print(f"{indent}[{comment.score}] {comment.body[:50]}")
```

### Breadth-First Manual Traversal

```python
# Replace MoreComments first
submission.comments.replace_more(limit=None)

# Manual BFS traversal
comment_queue = submission.comments[:]  # Top-level comments
while comment_queue:
    comment = comment_queue.pop(0)
    print(f"[Depth {comment.depth}] {comment.body[:50]}")
    comment_queue.extend(comment.replies)  # Add child comments
```

### Handling Deleted/Removed Comments

```python
submission.comments.replace_more(limit=0)

for comment in submission.comments.list():
    author_name = comment.author.name if comment.author else "[deleted]"
    print(f"{author_name}: {comment.body[:50]}")
```

### Batch Processing Hot Posts

```python
subreddit = reddit.subreddit("wallstreetbets")

for submission in subreddit.hot(limit=25):
    print(f"\n=== {submission.title} ===")
    print(f"Score: {submission.score}, Comments: {submission.num_comments}")

    # Fetch comments efficiently
    submission.comments.replace_more(limit=0)
    comments = submission.comments.list()

    # Get top 5 comments by score
    top_5 = sorted(comments, key=lambda c: c.score, reverse=True)[:5]
    for i, comment in enumerate(top_5, 1):
        print(f"  {i}. [{comment.score}] {comment.body[:80]}")
```

### Filtering by Comment Characteristics

```python
# Get comments with high engagement (score > 100)
high_engagement = [c for c in all_comments if c.score > 100]

# Get top-level comments only
top_level = [c for c in all_comments if c.depth == 0]

# Get OP (original poster) comments
op_comments = [c for c in all_comments if c.is_submitter]

# Get comments from specific time range (last 24 hours)
import time
day_ago = time.time() - 86400
recent = [c for c in all_comments if c.created_utc > day_ago]
```

---

## Performance Considerations

1. **API Rate Limits**: Reddit's API has rate limits (60 requests per minute for OAuth2)
2. **replace_more() Cost**: Each call makes an API request. Use `limit=0` for faster operation at the cost of missing nested comments
3. **Large Threads**: Threads with thousands of comments can take significant time to fetch
4. **Caching**: Consider caching fetched data to minimize API calls
5. **Deleted Content**: `num_comments` may exceed actual fetched comments due to deleted/removed content

---

## Error Handling

```python
import prawcore

try:
    submission = reddit.submission(id="abc123")
    submission.comments.replace_more(limit=None)
except prawcore.exceptions.TooManyRequests:
    print("Rate limit exceeded. Wait before retrying.")
except prawcore.exceptions.NotFound:
    print("Submission not found.")
except prawcore.exceptions.Forbidden:
    print("Access forbidden (private/quarantined subreddit).")
```

---

## References

- Official Documentation: https://praw.readthedocs.io/en/stable/
- Authentication Guide: https://praw.readthedocs.io/en/stable/getting_started/authentication.html
- Submission Model: https://praw.readthedocs.io/en/stable/code_overview/models/submission.html
- Comment Model: https://praw.readthedocs.io/en/stable/code_overview/models/comment.html
- CommentForest: https://praw.readthedocs.io/en/stable/code_overview/other/commentforest.html
- Comment Tutorial: https://praw.readthedocs.io/en/stable/tutorials/comments.html
