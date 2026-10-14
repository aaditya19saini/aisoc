import pytest
from pydantic import BaseModel

from app import llm


class Out(BaseModel):
    answer: int


@pytest.mark.parametrize(
    "raw",
    ['{"answer": 1}', '```json\n{"answer": 1}\n```', 'Sure! Here it is: {"answer": 1} hope that helps'],
)
def test_extract_json(raw):
    assert llm.extract_json(raw) == {"answer": 1}


def test_get_json_retries_once_on_bad_output(fake_llm):
    fake_llm["replies"] = ["not json", '{"answer": 42}']
    cfg = llm.ModelConfig("openai", "gpt-x")
    assert llm.get_json(cfg, "sys", "prompt", Out).answer == 42


def test_get_json_gives_up_after_retry(fake_llm):
    fake_llm["replies"] = ["nope", '{"answer": "x"}']
    with pytest.raises(llm.LLMError):
        llm.get_json(llm.ModelConfig("openai", "gpt-x"), "sys", "prompt", Out)


def test_model_config_defaults_and_overrides():
    from app.db import SessionLocal
    from app.store import set_setting

    db = SessionLocal()
    assert llm.get_model_config(db, "writer").provider == "anthropic"
    set_setting(db, "llm.writer.provider", "ollama")
    set_setting(db, "llm.writer.model", "llama3.1")
    set_setting(db, "llm.writer.api_key", "sk-secret", secret=True)
    cfg = llm.get_model_config(db, "writer")
    assert cfg.litellm_model == "ollama/llama3.1"
    assert cfg.api_key == "sk-secret"
