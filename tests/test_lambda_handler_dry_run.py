"""
Dry-run test for the Lambda handler -- proves event parsing, the
run_episode() call, and both success/error response shapes, without
touching real AWS (Secrets Manager, Bedrock) or CockroachDB.
"""
from __future__ import annotations

from unittest.mock import patch

from src.agent.config import EpisodeResult


def fake_episode_result() -> EpisodeResult:
    return EpisodeResult(
        episode_id="11111111-1111-1111-1111-111111111111",
        project="crynux", query="test query", strategy_summary="test strategy",
        claims=[], lessons=[], final_answer="Test answer.", status="completed",
    )


def test_direct_invoke_payload_returns_200():
    from src.agent import lambda_handler

    with patch("src.agent.lambda_handler._load_config", lambda: object()), \
         patch("src.agent.lambda_handler.run_episode", lambda *a, **k: fake_episode_result()):
        response = lambda_handler.handler({"project": "crynux", "query": "test query"}, context=None)

    import json
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["episode_id"] == "11111111-1111-1111-1111-111111111111"
    assert body["final_answer"] == "Test answer."
    print("OK: direct invoke payload handled correctly")


def test_api_gateway_proxy_payload_returns_200():
    from src.agent import lambda_handler
    import json

    event = {"body": json.dumps({"project": "crynux", "query": "test query"})}

    with patch("src.agent.lambda_handler._load_config", lambda: object()), \
         patch("src.agent.lambda_handler.run_episode", lambda *a, **k: fake_episode_result()):
        response = lambda_handler.handler(event, context=None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["final_answer"] == "Test answer."
    print("OK: API Gateway proxy-integration payload handled correctly")


def test_missing_required_field_returns_400():
    from src.agent import lambda_handler

    response = lambda_handler.handler({"project": "crynux"}, context=None)  # no query

    assert response["statusCode"] == 400
    print("OK: missing 'query' rejected with 400, no Bedrock/DB call attempted")


def test_episode_exception_returns_500_not_a_crash():
    from src.agent import lambda_handler

    def boom(*a, **k):
        raise RuntimeError("simulated Bedrock failure")

    with patch("src.agent.lambda_handler._load_config", lambda: object()), \
         patch("src.agent.lambda_handler.run_episode", boom):
        response = lambda_handler.handler({"project": "crynux", "query": "test query"}, context=None)

    assert response["statusCode"] == 500
    print("OK: an exception inside run_episode is caught and returned as a readable 500, not an unhandled crash")


def test_options_preflight_returns_204_with_cors_headers():
    from src.agent import lambda_handler

    event = {"requestContext": {"http": {"method": "OPTIONS"}}}
    response = lambda_handler.handler(event, context=None)

    assert response["statusCode"] == 204
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"
    print("OK: CORS preflight handled without touching config/Bedrock/DB")


def test_memory_trace_action_returns_trace_data():
    from src.agent import lambda_handler
    import json

    fake_trace = {
        "project": "crynux",
        "sources": [{"domain": "docs.crynux.io", "reliability_score": 0.35}],
        "episodes": [], "lessons": [], "contradictions": [],
    }

    with patch("src.agent.lambda_handler._load_config", lambda: object()), \
         patch("src.agent.lambda_handler.get_memory_trace", lambda config, project: fake_trace):
        response = lambda_handler.handler({"action": "memory_trace", "project": "crynux"}, context=None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["sources"][0]["domain"] == "docs.crynux.io"
    print("OK: memory_trace action routes correctly and returns trace data")


def test_memory_trace_missing_project_returns_400():
    from src.agent import lambda_handler

    response = lambda_handler.handler({"action": "memory_trace"}, context=None)
    assert response["statusCode"] == 400
    print("OK: memory_trace without a project rejected with 400")


if __name__ == "__main__":
    test_direct_invoke_payload_returns_200()
    test_api_gateway_proxy_payload_returns_200()
    test_missing_required_field_returns_400()
    test_episode_exception_returns_500_not_a_crash()
    test_options_preflight_returns_204_with_cors_headers()
    test_memory_trace_action_returns_trace_data()
    test_memory_trace_missing_project_returns_400()
    print("\nAll Lambda handler dry-run checks passed.")
