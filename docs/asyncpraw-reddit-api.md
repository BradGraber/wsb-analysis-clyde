# Async PRAW (asyncpraw) — Python Reddit API Wrapper

**Version:** 7.8.1 | **Type:** Async/Await Library

> This is the **asynchronous variant** of PRAW. For synchronous operations, see `praw-reddit-api.md`. All network requests in asyncpraw require `await` and use `aiohttp` under the hood.

## Table of Contents

1. [Installation](#installation)
2. [Reddit Instance Creation](#reddit-instance-creation)
3. [Subreddit Methods](#subreddit-methods)
4. [Submission Model](#submission-model)
5. [Comment Model](#comment-model)
6. [CommentForest Operations](#commentforest-operations)
7. [Async Patterns](#async-patterns)
8. [Key Differences from Synchronous PRAW](#key-differences-from-synchronous-praw)

---

## Installation

```bash
pip install asyncpraw
```

**Dependencies:** Requires Python 3.8+ for async/await support.

---

## Reddit Instance Creation

### Basic Authentication

```python
import asyncpraw

reddit = asyncpraw.Reddit(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    user_agent="YOUR_USER_AGENT",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD"
)
```

### Required Parameters

Three parameters are **mandatory**:
- `client_id` — Reddit application ID
- `client_secret` — Application secret (set to `None` for installed apps)
- `user_agent` — Descriptive identifier for your application

### Context Manager Pattern (Recommended)

Always use async context managers for automatic resource cleanup:

```python
async with asyncpraw.Reddit(
    client_id="CLIENT_ID",
    client_secret="CLIENT_SECRET",
    user_agent="my-app/1.0",
    username="username",
    password="password"
) as reddit:
    subreddit = await reddit.subreddit("python")
    async for submission in subreddit.hot(limit=10):
        print(submission.title)
```

### Manual Resource Management

If not using a context manager, explicitly close the session:

```python
reddit = asyncpraw.Reddit(...)
# ... use reddit ...
await reddit.close()
```

### Configuration Options

**Load from `praw.ini` file:**
```python
reddit = asyncpraw.Reddit(site_name="my_bot")  # Loads [my_bot] section
```

**Environment Variables:**
- Set `praw_site` environment variable to specify the config section

**Additional Parameters:**
- `requestor_class` — Custom requestor for debugging/caching
- `requestor_kwargs` — Additional arguments for requestor initialization
- `token_manager` — Manages refresh tokens via callbacks

---

## Subreddit Methods

All methods return `ListingGenerator` objects that support async iteration.

### hot()

Returns hot submissions in the subreddit.

```python
subreddit = await reddit.subreddit("wallstreetbets")

# Get 25 hot posts
async for submission in subreddit.hot(limit=25):
    print(submission.title, submission.score)
```

**Parameters:**
- `limit` (int) — Maximum number of items to yield (default: 100)

### new()

Returns newest submissions.

```python
async for submission in subreddit.new(limit=50):
    print(submission.title, submission.created_utc)
```

### top()

Returns top-performing submissions within a time period.

```python
# Top posts of the week
async for submission in subreddit.top(time_filter="week", limit=10):
    print(submission.title, submission.score)
```

**Parameters:**
- `time_filter` (str) — One of: `"all"`, `"day"`, `"hour"`, `"month"`, `"week"`, `"year"` (default: `"all"`)
- `limit` (int) — Maximum items to yield

### controversial()

Returns controversial submissions within a time period.

```python
async for submission in subreddit.controversial(time_filter="month", limit=20):
    print(submission.title, submission.upvote_ratio)
```

**Parameters:** Same as `top()`

### Other Methods

**rising()** — Rising submissions
```python
async for submission in subreddit.rising(limit=10):
    ...
```

**gilded()** — Gilded/awarded submissions
```python
async for submission in subreddit.gilded(limit=10):
    ...
```

**random_rising()** — Random selection from rising submissions

---

## Submission Model

Represents a Reddit post. Submissions are **fully fetched by default** (not lazy-loaded).

### Key Attributes

**Content:**
- `title` (str) — Post title
- `selftext` (str) — Text body (empty for link posts)
- `url` (str) — Link URL (for link posts) or Reddit URL (for self posts)

**Engagement Metrics:**
- `score` (int) — Net upvotes (upvotes - downvotes)
- `num_comments` (int) — Total comment count
- `upvote_ratio` (float) — Ratio of upvotes to total votes (0.0-1.0)

**Metadata:**
- `id` (str) — Unique submission ID
- `created_utc` (float) — Unix timestamp of creation
- `author` (Redditor) — Post author object
- `subreddit` (Subreddit) — Parent subreddit object

**Status Flags:**
- `edited` (bool or float) — False or timestamp of last edit
- `locked` (bool) — Whether comments are locked
- `stickied` (bool) — Whether post is pinned
- `spoiler` (bool) — Spoiler tag status
- `over_18` (bool) — NSFW flag
- `is_self` (bool) — True for text posts

**User Interaction:**
- `clicked` (bool) — Whether current user clicked the link
- `saved` (bool) — Whether current user saved the post

### Creating Submission Objects

**By ID:**
```python
submission = await reddit.submission("2gmzqe")
```

**By URL:**
```python
submission = await reddit.submission(url="https://redd.it/2gmzqe")
```

**Deferred Loading (for batch operations):**
```python
submission = await reddit.submission("2gmzqe", fetch=False)
await submission.load()  # Explicitly fetch data
```

### Common Methods

**Voting:**
```python
await submission.upvote()
await submission.downvote()
await submission.clear_vote()
```

**Replying:**
```python
comment = await submission.reply("This is my reply")
```

**Editing (for own submissions):**
```python
await submission.edit("Updated post text")
```

**Crossposting:**
```python
await submission.crosspost(subreddit="another_subreddit", title="Crosspost Title")
```

**Awarding:**
```python
await submission.award(gild_type="gold")  # Requires Reddit Coins
```

**Other Actions:**
```python
await submission.save(category="finance")
await submission.unsave()
await submission.hide()
await submission.unhide()
await submission.report(reason="Spam")
```

### Accessing Comments

```python
submission = await reddit.submission("2gmzqe")
comments = await submission.comments()  # Returns CommentForest
```

---

## Comment Model

Represents a Reddit comment. Comments are **fully fetched by default**.

### Key Attributes

**Content:**
- `body` (str) — Comment text (Markdown format)
- `body_html` (str) — HTML-rendered comment text

**Engagement:**
- `score` (int) — Net upvotes
- `replies` (CommentForest) — Nested child comments

**Metadata:**
- `id` (str) — Unique comment ID
- `created_utc` (float) — Unix timestamp
- `edited` (bool or float) — False or timestamp of last edit
- `author` (Redditor) — Comment author

**Relationships:**
- `parent_id` (str) — ID of parent (t3_xxx for submissions, t1_xxx for comments)
- `submission` (Submission) — Parent submission
- `subreddit` (Subreddit) — Parent subreddit
- `depth` (int) — Nesting level (0 = top-level)

**Status:**
- `distinguished` (str or None) — "moderator", "admin", or None
- `stickied` (bool) — Whether pinned
- `is_submitter` (bool) — Whether author is the OP
- `saved` (bool) — Whether current user saved it

### Creating Comment Objects

**By ID:**
```python
comment = await reddit.comment("abc123")
```

**Lazy Loading:**
```python
comment = await reddit.comment("abc123", fetch=False)
await comment.refresh()  # Loads data + nested replies
```

### Common Methods

**Replying:**
```python
reply = await comment.reply("Thanks for sharing!")
```

**Editing (for own comments):**
```python
await comment.edit("Updated comment text")
```

**Deleting:**
```python
await comment.delete()
```

**Voting:**
```python
await comment.upvote()
await comment.downvote()
await comment.clear_vote()
```

**Navigation:**
```python
parent = await comment.parent()  # Returns Comment or Submission
await comment.refresh()  # Reload from Reddit
```

**Inbox Operations:**
```python
await comment.mark_read()
await comment.mark_unread()
await comment.block()  # Block author
```

**Other Actions:**
```python
await comment.save(category="interesting")
await comment.award(gild_type="silver")
await comment.collapse()
await comment.report(reason="Spam")
```

---

## CommentForest Operations

`CommentForest` represents the hierarchical structure of comments under a submission.

### Handling MoreComments Objects

Reddit's API initially returns only top-level comments. "Load more comments" links are represented as `MoreComments` objects.

### replace_more()

Fetches additional comments by replacing `MoreComments` objects.

```python
submission = await reddit.submission("2gmzqe")
comments = await submission.comments()

# Replace all MoreComments objects (can be slow for large threads)
await comments.replace_more(limit=None)
```

**Parameters:**
- `limit` (int or None) — Maximum number of `MoreComments` to replace
  - `limit=0` — Remove all MoreComments without fetching (fastest)
  - `limit=None` — Replace all MoreComments (slowest, most complete)
  - `limit=5` — Replace up to 5 MoreComments objects
- `threshold` (int) — Only replace MoreComments with at least this many comments

**Important:** `replace_more()` is destructive. Calling it multiple times has no effect.

### list()

Flattens the comment tree into a single list (breadth-first traversal).

```python
submission = await reddit.submission("2gmzqe")
comments = await submission.comments()
await comments.replace_more(limit=0)  # Remove MoreComments

# Get flattened list of all comments
all_comments = comments.list()
for comment in all_comments:
    print(f"{comment.author}: {comment.body}")
```

**Returns:** List of all Comment objects (no async iteration needed after this step)

### Extracting All Comments (Common Pattern)

```python
async def get_all_comments(submission_id):
    submission = await reddit.submission(submission_id)
    comments = await submission.comments()

    # Option 1: Remove MoreComments without fetching (fast)
    await comments.replace_more(limit=0)

    # Option 2: Fetch all comments (slow for large threads)
    # await comments.replace_more(limit=None)

    return comments.list()

# Usage
all_comments = await get_all_comments("2gmzqe")
print(f"Extracted {len(all_comments)} comments")
```

### Notes

- `submission.num_comments` may differ from extracted count (includes deleted/removed comments)
- Large threads can contain thousands of comments — use `limit=0` for quick keyword analysis
- For deep analysis, use `limit=None` but expect slower performance

---

## Async Patterns

### Basic Async Iteration

```python
async with asyncpraw.Reddit(...) as reddit:
    subreddit = await reddit.subreddit("python")

    async for submission in subreddit.hot(limit=10):
        print(submission.title)
```

### Gathering Multiple Subreddits

```python
import asyncio

async def fetch_hot_posts(subreddit_name):
    async with asyncpraw.Reddit(...) as reddit:
        subreddit = await reddit.subreddit(subreddit_name)
        posts = []
        async for submission in subreddit.hot(limit=5):
            posts.append(submission)
        return posts

# Fetch from multiple subreddits in parallel
results = await asyncio.gather(
    fetch_hot_posts("python"),
    fetch_hot_posts("programming"),
    fetch_hot_posts("learnpython")
)
```

### Processing Comments with Async For

```python
submission = await reddit.submission("2gmzqe")
comments = await submission.comments()
await comments.replace_more(limit=0)

for comment in comments.list():
    # Process each comment
    if "keyword" in comment.body.lower():
        print(f"Found in comment {comment.id}: {comment.body[:50]}")
```

### Handling Lazy-Loaded Attributes

Some objects (Subreddit, Redditor) are lazy-loaded by default:

```python
# Lazy-loaded subreddit
subreddit = await reddit.subreddit("python", fetch=False)
print(subreddit.display_name)  # Available without fetch

# Need full data
await subreddit.load()
print(subreddit.subscribers)  # Now available
```

### Error Handling

```python
from asyncpraw.exceptions import RedditAPIException

try:
    async for submission in subreddit.hot(limit=10):
        await submission.upvote()
except RedditAPIException as e:
    print(f"API Error: {e}")
```

---

## Key Differences from Synchronous PRAW

### 1. All Network Requests Require `await`

**Synchronous PRAW:**
```python
submission = reddit.submission("2gmzqe")
print(submission.title)
```

**Async PRAW:**
```python
submission = await reddit.submission("2gmzqe")
print(submission.title)
```

### 2. Context Manager is Async

**Synchronous PRAW:**
```python
with praw.Reddit(...) as reddit:
    ...
```

**Async PRAW:**
```python
async with asyncpraw.Reddit(...) as reddit:
    ...
```

### 3. Iteration is Async

**Synchronous PRAW:**
```python
for submission in subreddit.hot(limit=10):
    print(submission.title)
```

**Async PRAW:**
```python
async for submission in subreddit.hot(limit=10):
    print(submission.title)
```

### 4. Lazy Loading Inverted for Some Objects

**Fully Fetched by Default (asyncpraw):**
- Comment, Submission, WikiPage, Rule, RemovalReason, Emoji, LiveUpdate, Preferences, Collection

**Still Lazy-Loaded by Default:**
- Subreddit, Redditor, LiveThread, Multireddit

**Override with `fetch` parameter:**
```python
submission = await reddit.submission("2gmzqe", fetch=False)  # Lazy
subreddit = await reddit.subreddit("python", fetch=True)    # Eager
```

### 5. String Indexing No Longer Works

**Synchronous PRAW:**
```python
page = subreddit.wiki["page_name"]
```

**Async PRAW:**
```python
page = await subreddit.wiki.get_page("page_name")
```

### 6. Manual Refresh for Lazy Objects

**Async PRAW:**
```python
comment = await reddit.comment("abc123", fetch=False)
await comment.refresh()  # Now loads data + nested replies
```

---

## Common Use Cases

### Fetch Top Posts and Comments

```python
async with asyncpraw.Reddit(...) as reddit:
    subreddit = await reddit.subreddit("wallstreetbets")

    async for submission in subreddit.hot(limit=5):
        print(f"\n{submission.title} ({submission.score} points)")

        comments = await submission.comments()
        await comments.replace_more(limit=0)

        for comment in comments.list()[:10]:
            print(f"  - {comment.author}: {comment.body[:60]}")
```

### Keyword Analysis Across Comments

```python
async def analyze_keywords(submission_id, keywords):
    submission = await reddit.submission(submission_id)
    comments = await submission.comments()
    await comments.replace_more(limit=0)

    matches = []
    for comment in comments.list():
        for keyword in keywords:
            if keyword.lower() in comment.body.lower():
                matches.append({
                    "comment_id": comment.id,
                    "author": str(comment.author),
                    "score": comment.score,
                    "keyword": keyword
                })
    return matches

# Usage
results = await analyze_keywords("2gmzqe", ["python", "async", "await"])
print(f"Found {len(results)} keyword matches")
```

### Monitor New Submissions

```python
async def monitor_new(subreddit_name):
    async with asyncpraw.Reddit(...) as reddit:
        subreddit = await reddit.subreddit(subreddit_name)

        seen_ids = set()
        while True:
            async for submission in subreddit.new(limit=10):
                if submission.id not in seen_ids:
                    print(f"New post: {submission.title}")
                    seen_ids.add(submission.id)

            await asyncio.sleep(60)  # Check every minute
```

---

## Additional Resources

- **Official Documentation:** https://asyncpraw.readthedocs.io/
- **GitHub Repository:** https://github.com/praw-dev/asyncpraw
- **Migration Guide:** https://asyncpraw.readthedocs.io/en/stable/package_info/asyncpraw_migration.html
- **Synchronous PRAW Comparison:** See `praw-reddit-api.md` in this directory

---

## Version Notes

This document covers **asyncpraw 7.8.1**. Always check the official documentation for the latest API changes and deprecations.
