"""ModelRouter birim testleri — heuristik tier seçimini doğrular."""

from __future__ import annotations

from hackeragent.core.router import ModelRouter, ModelTiers


def _tiers() -> ModelTiers:
    return ModelTiers(cheap="CHEAP", standard="STD", premium="PREM")


def test_disabled_router_always_returns_standard():
    r = ModelRouter(_tiers(), enabled=False)
    msgs = [{"role": "user", "content": "exploit yaz bana"}]
    assert r.pick(msgs) == "STD"


def test_premium_triggered_by_exploit_keyword():
    r = ModelRouter(_tiers())
    msgs = [{"role": "user", "content": "bu SQLi için exploit PoC yaz"}]
    assert r.pick(msgs) == "PREM"


def test_premium_triggered_by_report_keyword():
    r = ModelRouter(_tiers())
    msgs = [{"role": "user", "content": "HackerOne raporu yazabilir misin"}]
    assert r.pick(msgs) == "PREM"


def test_cheap_for_short_greeting_first_turn():
    r = ModelRouter(_tiers())
    msgs = [{"role": "user", "content": "merhaba"}]
    assert r.pick(msgs, iteration=0) == "CHEAP"


def test_cheap_for_short_input_no_tool():
    r = ModelRouter(_tiers())
    msgs = [{"role": "user", "content": "tools listele"}]
    assert r.pick(msgs, iteration=0) == "CHEAP"


def test_standard_default_for_normal_task():
    r = ModelRouter(_tiers())
    # "listele" gibi cheap keyword YOK + uzun görev → standard
    msgs = [{"role": "user",
             "content": "10.10.10.10 adresinde servisleri tara, açık portları "
                        "bulduktan sonra en ilgi çekici olanı derinleştir ve "
                        "potansiyel zafiyetleri analiz et"}]
    assert r.pick(msgs, iteration=0) == "STD"


def test_long_context_forces_standard_not_premium():
    # Tool sonucu çok büyük bağlam var → premium pahalı olur, standard dön
    r = ModelRouter(_tiers())
    big_tool = "x" * 9000
    msgs = [
        {"role": "user", "content": "devam et"},
        {"role": "tool", "content": big_tool},
    ]
    # "exploit" yok → premium yok, bağlam büyük → standard (cheap değil)
    assert r.pick(msgs, iteration=2) == "STD"


def test_from_config_fallback_when_cheap_premium_empty():
    cfg = {"orchestrator": "qwen/q3", "exploit_gen": "hermes/4"}
    t = ModelTiers.from_config(cfg)
    assert t.standard == "qwen/q3"
    assert t.cheap == "qwen/q3"  # fallback to standard
    assert t.premium == "hermes/4"  # fallback to exploit_gen


def test_from_config_explicit_tiers():
    cfg = {
        "orchestrator": "std-model",
        "exploit_gen": "hermes",
        "cheap": "tiny-model",
        "premium": "big-model",
    }
    t = ModelTiers.from_config(cfg)
    assert t.cheap == "tiny-model"
    assert t.standard == "std-model"
    assert t.premium == "big-model"


def test_short_tool_result_triggers_cheap():
    r = ModelRouter(_tiers())
    msgs = [
        {"role": "user", "content": "portları kontrol et"},
        {"role": "assistant", "content": ""},
        {"role": "tool", "content": "port 22 açık"},
    ]
    assert r.pick(msgs, iteration=1) == "CHEAP"
