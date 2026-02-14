"""
Tests for scoring functions (stories 002-004 through 002-007).

Behavioral tests for financial keyword scoring, author trust lookup,
engagement/depth scoring, and priority score calculation.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestFinancialKeywordScoring:
    """Test financial keyword scoring (story-002-004)."""

    @pytest.mark.parametrize('text,expected_score', [
        # Zero keywords
        ('This is a random comment about weather', 0.0),
        # Single keyword
        ('I bought some calls yesterday', 0.1),  # 1 keyword, ~10 words = 1/10 * 10 = 1.0, clamped
        # Multiple keywords
        ('calls and puts both have high IV', 0.3),
        # Max score (clamped at 1.0)
        ('calls puts options strike expiry DD earnings revenue P/E market cap', 1.0),
        # Case insensitive
        ('CALLS PUTS OPTIONS', 0.3),
        # Empty/whitespace
        ('', 0.0),
        ('   ', 0.0),
    ])
    def test_financial_keyword_scoring(self, text, expected_score):
        """Financial keyword scoring with scaling factor 10.0."""
        from src.scoring import score_financial_keywords

        score = score_financial_keywords(text)

        # Allow small floating point tolerance
        assert abs(score - expected_score) < 0.15

    def test_keyword_case_insensitive(self):
        """Keywords matched case-insensitively."""
        from src.scoring import score_financial_keywords

        text_lower = 'i bought calls and puts'
        text_upper = 'I BOUGHT CALLS AND PUTS'
        text_mixed = 'I bought CaLLs and PuTs'

        score_lower = score_financial_keywords(text_lower)
        score_upper = score_financial_keywords(text_upper)
        score_mixed = score_financial_keywords(text_mixed)

        assert score_lower == score_upper == score_mixed
        assert score_lower > 0

    def test_keyword_word_boundary_matching(self):
        """Keywords use word boundary matching."""
        from src.scoring import score_financial_keywords

        # "call" in "called" should NOT match "calls"
        no_match = score_financial_keywords('I called my broker')
        # Actual keyword should match
        match = score_financial_keywords('I bought calls')

        assert match > no_match

    def test_multi_word_keywords_as_phrases(self):
        """Multi-word keywords matched as phrases."""
        from src.scoring import score_financial_keywords

        # "due diligence" should match as phrase
        text = 'Here is my due diligence on AAPL'
        score = score_financial_keywords(text)

        assert score > 0

    def test_zero_keywords_returns_zero(self):
        """Zero keywords returns 0.0."""
        from src.scoring import score_financial_keywords

        text = 'Just talking about random stuff'
        score = score_financial_keywords(text)

        assert score == 0.0

    def test_empty_body_returns_zero(self):
        """Empty or whitespace body returns 0.0."""
        from src.scoring import score_financial_keywords

        assert score_financial_keywords('') == 0.0
        assert score_financial_keywords('   ') == 0.0
        assert score_financial_keywords('\n\t') == 0.0


class TestAuthorTrustLookup:
    """Test author trust score lookup (story-002-005)."""

    def test_batch_query_authors_table(self, seeded_db):
        """Batch query authors table for trust_score."""
        from src.scoring import lookup_author_trust_scores

        # Insert test authors
        seeded_db.execute("""
            INSERT INTO authors (username, total_comments, high_quality_comments,
                               avg_sentiment_accuracy, first_seen, last_active)
            VALUES
                ('user1', 100, 80, 0.75, datetime('now'), datetime('now')),
                ('user2', 50, 30, 0.60, datetime('now', '-10 days'), datetime('now')),
                ('user3', 10, 2, 0.20, datetime('now', '-5 days'), datetime('now'))
        """)
        seeded_db.commit()

        authors = ['user1', 'user2', 'user3', 'unknown_user']
        scores = lookup_author_trust_scores(seeded_db, authors)

        # Should return dict with all authors
        assert len(scores) == 4
        assert 'user1' in scores
        assert 'user2' in scores
        assert 'user3' in scores
        assert 'unknown_user' in scores

    def test_author_not_found_defaults_to_0_5(self, seeded_db):
        """Author not found defaults to 0.5."""
        from src.scoring import lookup_author_trust_scores

        scores = lookup_author_trust_scores(seeded_db, ['nonexistent_user'])

        assert scores['nonexistent_user'] == 0.5

    def test_deleted_author_defaults_to_0_5(self, seeded_db):
        """[deleted] authors default to 0.5."""
        from src.scoring import lookup_author_trust_scores

        scores = lookup_author_trust_scores(seeded_db, ['[deleted]'])

        assert scores['[deleted]'] == 0.5

    def test_efficient_batch_lookup(self, seeded_db):
        """Efficient batch lookup for all unique authors."""
        from src.scoring import lookup_author_trust_scores

        # Insert one known author
        seeded_db.execute("""
            INSERT INTO authors (username, total_comments, high_quality_comments,
                               avg_sentiment_accuracy, first_seen, last_active)
            VALUES ('known_user', 100, 90, 0.85, datetime('now'), datetime('now'))
        """)
        seeded_db.commit()

        # Lookup batch with duplicates
        authors = ['known_user', 'unknown1', 'unknown2', 'known_user']
        scores = lookup_author_trust_scores(seeded_db, authors)

        # Should deduplicate and return 3 unique results
        assert len(scores) == 3
        assert 'known_user' in scores
        assert scores['unknown1'] == 0.5
        assert scores['unknown2'] == 0.5


class TestEngagementAndDepthScoring:
    """Test engagement and depth scoring (story-002-006)."""

    def test_engagement_score_calculation(self):
        """Engagement score = log(upvotes + 1) × reply_count."""
        from src.scoring import calculate_engagement
        import math

        upvotes = 100
        reply_count = 5

        engagement = calculate_engagement(upvotes, reply_count)

        expected = math.log(upvotes + 1) * reply_count
        assert abs(engagement - expected) < 0.001

    def test_zero_upvotes_returns_zero(self):
        """Zero upvotes returns 0.0."""
        from src.scoring import calculate_engagement

        engagement = calculate_engagement(0, 10)

        # log(0 + 1) * 10 = 0 * 10 = 0
        assert engagement == 0.0

    def test_zero_replies_returns_zero(self):
        """Zero replies returns 0.0."""
        from src.scoring import calculate_engagement

        engagement = calculate_engagement(100, 0)

        assert engagement == 0.0

    def test_depth_penalty_calculation(self):
        """Depth penalty = min(0.3, depth × 0.05)."""
        from src.scoring import calculate_depth_penalty

        assert calculate_depth_penalty(0) == 0.0
        assert calculate_depth_penalty(1) == 0.05
        assert calculate_depth_penalty(3) == 0.15
        assert calculate_depth_penalty(6) == 0.3  # Capped
        assert calculate_depth_penalty(10) == 0.3  # Capped

    def test_engagement_normalized_to_0_1_range(self):
        """Engagement normalized to 0-1 range via min-max."""
        from src.scoring import normalize_engagement_scores

        comments = [
            {'engagement': 10.0},
            {'engagement': 50.0},
            {'engagement': 100.0},
        ]

        normalized = normalize_engagement_scores(comments)

        # Min-max normalization
        assert normalized[0]['engagement_normalized'] == 0.0  # Min
        assert normalized[2]['engagement_normalized'] == 1.0  # Max
        assert 0.0 < normalized[1]['engagement_normalized'] < 1.0

    def test_equal_scores_normalized_to_zero(self):
        """Equal scores normalized to 0.0 to avoid division by zero."""
        from src.scoring import normalize_engagement_scores

        comments = [
            {'engagement': 42.0},
            {'engagement': 42.0},
            {'engagement': 42.0},
        ]

        normalized = normalize_engagement_scores(comments)

        # All equal -> all 0.0
        assert all(c['engagement_normalized'] == 0.0 for c in normalized)


class TestPriorityScoringAndSelection:
    """Test priority scoring and top-50 selection (story-002-007)."""

    def test_priority_score_formula(self):
        """priority_score = (financial × 0.4) + (trust × 0.3) + (engagement × 0.3) - depth_penalty."""
        from src.scoring import calculate_priority_score

        financial_score = 0.8
        author_trust = 0.6
        engagement_normalized = 0.7
        depth_penalty = 0.15

        priority = calculate_priority_score(
            financial_score, author_trust, engagement_normalized, depth_penalty
        )

        expected = (0.8 * 0.4) + (0.6 * 0.3) + (0.7 * 0.3) - 0.15
        assert abs(priority - expected) < 0.001

    def test_priority_score_clamped_to_min_zero(self):
        """priority_score clamped to minimum 0.0."""
        from src.scoring import calculate_priority_score

        # Negative result before clamping
        priority = calculate_priority_score(0.0, 0.0, 0.0, 0.5)

        assert priority == 0.0

    def test_select_top_50_per_post(self):
        """Select top 50 comments per post."""
        from src.scoring import select_top_comments

        # Create 100 comments with varying priority scores
        comments = []
        for i in range(100):
            comments.append({
                'id': f'comment_{i}',
                'priority_score': i / 100.0,  # 0.0 to 0.99
                'parent_chain': []
            })

        selected = select_top_comments(comments, top_n=50)

        assert len(selected) == 50
        # Should be top 50 (highest scores)
        assert selected[0]['priority_score'] > selected[-1]['priority_score']

    def test_fewer_than_50_keeps_all(self):
        """Fewer than 50 comments keeps all."""
        from src.scoring import select_top_comments

        comments = [
            {'id': 'c1', 'priority_score': 0.5, 'parent_chain': []},
            {'id': 'c2', 'priority_score': 0.3, 'parent_chain': []},
        ]

        selected = select_top_comments(comments, top_n=50)

        assert len(selected) == 2

    def test_parent_chains_preserved_on_selected(self):
        """Parent chains preserved on selected comments."""
        from src.scoring import select_top_comments

        parent_chain = [
            {'id': 'parent1', 'body': 'Parent text', 'depth': 0, 'author': 'user1'}
        ]

        comments = [
            {'id': 'c1', 'priority_score': 0.9, 'parent_chain': parent_chain},
            {'id': 'c2', 'priority_score': 0.1, 'parent_chain': []},
        ]

        selected = select_top_comments(comments, top_n=1)

        assert len(selected) == 1
        assert selected[0]['parent_chain'] == parent_chain

    def test_non_selected_discarded(self):
        """Non-selected comments are discarded."""
        from src.scoring import select_top_comments

        comments = [
            {'id': 'high', 'priority_score': 0.9, 'parent_chain': []},
            {'id': 'low', 'priority_score': 0.1, 'parent_chain': []},
        ]

        selected = select_top_comments(comments, top_n=1)

        assert len(selected) == 1
        assert selected[0]['id'] == 'high'
        # 'low' should be discarded
        assert all(c['id'] != 'low' for c in selected)

    def test_priority_score_with_length_bonus(self):
        """Length bonus adds to priority score."""
        from src.scoring import calculate_priority_score

        base = calculate_priority_score(0.8, 0.6, 0.7, 0.15)
        with_bonus = calculate_priority_score(0.8, 0.6, 0.7, 0.15, length_bonus=0.2)

        assert with_bonus == base + 0.2


class TestLengthBonus:
    """Test length bonus calculation."""

    def test_at_min_word_count_returns_zero(self):
        """Comments at MIN_WORD_COUNT get no bonus."""
        from src.scoring import calculate_length_bonus, MIN_WORD_COUNT

        assert calculate_length_bonus(MIN_WORD_COUNT) == 0.0

    def test_below_min_word_count_returns_zero(self):
        """Comments below MIN_WORD_COUNT get no bonus."""
        from src.scoring import calculate_length_bonus

        assert calculate_length_bonus(0) == 0.0
        assert calculate_length_bonus(3) == 0.0

    def test_scales_linearly(self):
        """Bonus scales linearly between MIN_WORD_COUNT and 100."""
        from src.scoring import calculate_length_bonus

        b50 = calculate_length_bonus(50)
        b75 = calculate_length_bonus(75)
        b100 = calculate_length_bonus(100)

        assert 0.0 < b50 < b75 < b100

    def test_caps_at_max_bonus(self):
        """Bonus caps at max_bonus for 100+ words."""
        from src.scoring import calculate_length_bonus

        assert calculate_length_bonus(100) == 0.2
        assert calculate_length_bonus(200) == 0.2
        assert calculate_length_bonus(500) == 0.2

    def test_custom_max_bonus(self):
        """Custom max_bonus parameter works."""
        from src.scoring import calculate_length_bonus

        bonus = calculate_length_bonus(100, max_bonus=0.5)
        assert bonus == 0.5


class TestMinWordFilter:
    """Test minimum word count filter with keyword exemption."""

    def _make_comment(self, body, financial_score=0.0, author_trust_score=0.5,
                      depth=0, score=1, engagement_normalized=0.0):
        """Create a mock ProcessedComment-like object."""
        from dataclasses import dataclass, field

        @dataclass
        class MockComment:
            reddit_id: str = 'test'
            post_id: str = 'p1'
            author: str = 'testuser'
            body: str = ''
            score: int = 1
            depth: int = 0
            created_utc: int = 1234567890
            financial_score: float = 0.0
            author_trust_score: float = 0.5
            priority_score: float = 0.0
            engagement_normalized: float = 0.0
            parent_chain: list = field(default_factory=list)

        return MockComment(
            body=body,
            financial_score=financial_score,
            author_trust_score=author_trust_score,
            depth=depth,
            score=score,
            engagement_normalized=engagement_normalized,
        )

    def _make_post(self, comments):
        """Create a mock ProcessedPost-like object."""
        from dataclasses import dataclass, field

        @dataclass
        class MockPost:
            reddit_id: str = 'p1'
            title: str = 'Test Post'
            selftext: str = ''
            upvotes: int = 100
            total_comments: int = 0
            comments: list = field(default_factory=list)

        return MockPost(comments=comments, total_comments=len(comments))

    def test_short_comment_no_keywords_filtered(self):
        """Short comments without financial keywords are filtered out."""
        from src.scoring import score_and_select_comments

        comments = [
            self._make_comment('Nice'),
            self._make_comment('This is a longer comment about the market today and stuff'),
        ]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts)

        assert len(result[0].comments) == 1
        assert 'longer comment' in result[0].comments[0].body

    def test_short_comment_with_keywords_kept(self):
        """Short comments with financial keywords are kept (keyword exemption)."""
        from src.scoring import score_and_select_comments

        comments = [
            self._make_comment('More spy puts', financial_score=0.1),
            self._make_comment('Nice'),
        ]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts)

        assert len(result[0].comments) == 1
        assert 'puts' in result[0].comments[0].body

    def test_exact_min_words_kept(self):
        """Comments with exactly MIN_WORD_COUNT words are kept."""
        from src.scoring import score_and_select_comments, MIN_WORD_COUNT

        body = ' '.join(['word'] * MIN_WORD_COUNT)
        comments = [self._make_comment(body)]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts)

        assert len(result[0].comments) == 1

    def test_url_only_filtered(self):
        """URL-only comments (1 word, no keywords) are filtered."""
        from src.scoring import score_and_select_comments

        comments = [
            self._make_comment('https://preview.redd.it/some-image.jpeg?width=800'),
        ]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts)

        assert len(result[0].comments) == 0

    def test_custom_min_words(self):
        """Custom min_words parameter overrides default."""
        from src.scoring import score_and_select_comments

        comments = [
            self._make_comment('one two three'),
            self._make_comment('one two three four five six seven'),
        ]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts, min_words=3)

        assert len(result[0].comments) == 2

    def test_filter_before_top_n(self):
        """Filtered comments don't consume top-N slots."""
        from src.scoring import score_and_select_comments

        # 3 good comments + 2 junk
        comments = [
            self._make_comment('This is a substantive comment about trading strategies'),
            self._make_comment('Another good comment about market analysis today'),
            self._make_comment('A third decent comment with some thoughts on positions'),
            self._make_comment('Lol'),
            self._make_comment('Nice'),
        ]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts, top_n=2)

        # Should have 2 (top_n), not affected by filtered junk
        assert len(result[0].comments) == 2
        for c in result[0].comments:
            assert len(c.body.split()) >= 5

    def test_longer_comment_scores_higher(self):
        """Longer comment with same base scores ranks higher due to length bonus."""
        from src.scoring import score_and_select_comments

        short_body = 'I like this stock here today'  # 6 words
        long_body = ' '.join(['word'] * 100)  # 100 words

        comments = [
            self._make_comment(short_body, financial_score=0.5, author_trust_score=0.5),
            self._make_comment(long_body, financial_score=0.5, author_trust_score=0.5),
        ]
        posts = [self._make_post(comments)]

        result = score_and_select_comments(posts)

        # Longer comment should have higher priority score
        short_c = next(c for c in result[0].comments if len(c.body.split()) == 6)
        long_c = next(c for c in result[0].comments if len(c.body.split()) == 100)
        assert long_c.priority_score > short_c.priority_score
