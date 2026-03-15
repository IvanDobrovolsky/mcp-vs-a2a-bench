"""Tests for hallucination detection."""

import pytest
from benchmark.hallucination_detector import (
    Claim,
    GroundTruth,
    extract_claims,
    verify_claim,
    _find_nearest_project,
)


class TestClaimExtraction:
    def test_extract_stars(self):
        text = "React has 220,000 stars on GitHub."
        claims = extract_claims(text, ["react"])
        star_claims = [c for c in claims if c.metric == "stars"]
        assert len(star_claims) >= 1
        assert star_claims[0].claimed_value == 220000

    def test_extract_downloads(self):
        text = "Express has 30 million weekly downloads."
        claims = extract_claims(text, ["express"])
        dl_claims = [c for c in claims if c.metric == "downloads"]
        assert len(dl_claims) >= 1
        assert dl_claims[0].claimed_value == 30_000_000

    def test_extract_vulnerabilities(self):
        text = "Lodash has 5 known vulnerabilities."
        claims = extract_claims(text, ["lodash"])
        vuln_claims = [c for c in claims if c.metric == "vulnerabilities"]
        assert len(vuln_claims) >= 1
        assert vuln_claims[0].claimed_value == 5

    def test_extract_forks(self):
        text = "Vue has 6,200 forks."
        claims = extract_claims(text, ["vue"])
        fork_claims = [c for c in claims if c.metric == "forks"]
        assert len(fork_claims) >= 1
        assert fork_claims[0].claimed_value == 6200

    def test_no_claims_in_prose(self):
        text = "React is a popular JavaScript library for building user interfaces."
        claims = extract_claims(text, ["react"])
        assert len(claims) == 0

    def test_multiple_projects(self):
        text = "React has 220,000 stars. Vue has 45,000 stars."
        claims = extract_claims(text, ["react", "vue"])
        star_claims = [c for c in claims if c.metric == "stars"]
        assert len(star_claims) >= 2


class TestNearestProject:
    def test_finds_nearest(self):
        text = "React has 220,000 stars. Vue has 45,000 stars."
        # Position of "220,000" is roughly 10
        result = _find_nearest_project(text, 10, ["react", "vue"])
        assert result == "react"

    def test_no_match(self):
        text = "Some random text with numbers 12345"
        result = _find_nearest_project(text, 30, ["react", "vue"])
        assert result is None


class TestClaimVerification:
    def test_verified_exact(self):
        claim = Claim(metric="stars", project="react", claimed_value=220000, source_context="")
        gt = GroundTruth(project="react", github={"stars": 220000})
        result = verify_claim(claim, gt)
        assert result["status"] == "verified"

    def test_verified_within_tolerance(self):
        claim = Claim(metric="stars", project="react", claimed_value=225000, source_context="")
        gt = GroundTruth(project="react", github={"stars": 220000})
        result = verify_claim(claim, gt)
        # 225000 vs 220000 = 2.3% error, within 10% tolerance
        assert result["status"] == "verified"

    def test_hallucinated(self):
        claim = Claim(metric="stars", project="react", claimed_value=500000, source_context="")
        gt = GroundTruth(project="react", github={"stars": 220000})
        result = verify_claim(claim, gt)
        # 500000 vs 220000 = 127% error
        assert result["status"] == "hallucinated"

    def test_unverified_no_ground_truth(self):
        claim = Claim(metric="stars", project="react", claimed_value=220000, source_context="")
        gt = GroundTruth(project="react")  # No github data
        result = verify_claim(claim, gt)
        assert result["status"] == "unverified"

    def test_vulnerability_exact_match_required(self):
        claim = Claim(metric="vulnerabilities", project="lodash", claimed_value=5, source_context="")
        gt = GroundTruth(project="lodash", osv={"total_vulnerabilities": 5})
        result = verify_claim(claim, gt)
        assert result["status"] == "verified"

    def test_vulnerability_off_by_one_is_hallucination(self):
        claim = Claim(metric="vulnerabilities", project="lodash", claimed_value=6, source_context="")
        gt = GroundTruth(project="lodash", osv={"total_vulnerabilities": 5})
        result = verify_claim(claim, gt)
        assert result["status"] == "hallucinated"

    def test_downloads_higher_tolerance(self):
        claim = Claim(metric="downloads", project="react", claimed_value=22_000_000, source_context="")
        gt = GroundTruth(project="react", npm={"weekly_downloads": 20_000_000})
        result = verify_claim(claim, gt)
        # 22M vs 20M = 10% error, within 20% tolerance
        assert result["status"] == "verified"
