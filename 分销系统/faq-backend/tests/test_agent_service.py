from app.services.agent import HiAgentService


def test_should_process_stream_event_without_outer_event():
    assert HiAgentService._should_process_stream_event(None, "message") is True


def test_should_skip_terminal_or_error_stream_events():
    assert HiAgentService._should_process_stream_event("error", "message") is False
    assert HiAgentService._should_process_stream_event("text", "done") is False


def test_extract_stream_delta_supports_cumulative_answer_without_event_prefix():
    delta, next_answer = HiAgentService._extract_stream_delta(
        {"event": "message", "Answer": "\u4f60"},
        "",
    )
    assert delta == "\u4f60"
    assert next_answer == "\u4f60"

    delta, next_answer = HiAgentService._extract_stream_delta(
        {"event": "message", "Answer": "\u4f60\u597d"},
        next_answer,
    )
    assert delta == "\u597d"
    assert next_answer == "\u4f60\u597d"


def test_extract_stream_delta_supports_incremental_answer_field():
    delta, next_answer = HiAgentService._extract_stream_delta(
        {"event": "message", "answer": "\u4f60"},
        "",
    )
    assert delta == "\u4f60"
    assert next_answer == "\u4f60"

    delta, next_answer = HiAgentService._extract_stream_delta(
        {"event": "message", "answer": "\u597d"},
        next_answer,
    )
    assert delta == "\u597d"
    assert next_answer == "\u4f60\u597d"


def test_normalize_agent_error_reply_hides_raw_workflow_errors():
    raw_error = (
        "agent execution failed. error: run workflow failed, status: failed, "
        'msg: Exception: Query request failed, msg: {"ResponseMetadata": {"RequestId": "x"}}'
    )

    assert (
        HiAgentService._normalize_agent_error_reply(raw_error)
        == "\u7f51\u7edc\u9519\u8bef\uff0c\u8bf7\u91cd\u8bd5"
    )


def test_normalize_agent_error_reply_hides_authorization_or_input_failures():
    raw_error = "agent \u6267\u884c\u51fa\u9519\uff1a\u5de5\u5177\u672a\u6388\u6743\u6216\u5165\u53c2\u9519\u8bef"

    assert (
        HiAgentService._normalize_agent_error_reply(raw_error)
        == "\u7f51\u7edc\u9519\u8bef\uff0c\u8bf7\u91cd\u8bd5"
    )


def test_normalize_agent_error_reply_keeps_normal_answer():
    assert HiAgentService._normalize_agent_error_reply("normal answer") == "normal answer"
