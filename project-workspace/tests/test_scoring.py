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
