import json
import subprocess
import sys

from conftest import SCRIPTS

DEVICES = ("desktop", "mobile")


def appeared(dev, scenario, kind, text, **extra):
    return {"scenario": scenario, "device": dev, "event": "appeared", "t_s": 8.0, "kind": kind, "vendor": extra.pop("vendor", None),
            "text": text, "has_email": extra.pop("has_email", kind == "capture_form"), "has_tel": False,
            "inputs": ["email"] if kind == "capture_form" else [], "after_exit_attempt": extra.pop("after_exit", False),
            "screenshot": f"{dev}_{scenario}_{kind}.jpg", **extra}


def exit_tried(dev, scenario):
    return {"scenario": scenario, "device": dev, "event": "exit_intent_simulated"}


def judge(tmp_path, events, pages=None, plan=None):
    devices = {d: {"pages": (pages or {}).get(d, {"home": {}}), "events": [e for e in events if e["device"] == d],
                   "shots": [], "errors": []} for d in DEVICES}
    walk = {"site": "https://store.test", "requested": "https://store.test", "started_utc": "2026-11-20 10:00",
            "minutes": 3.0, "plan": plan or {}, "devices": devices}
    (tmp_path / "walk.json").write_text(json.dumps(walk, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPTS / "prejudge.py"), "--out", str(tmp_path)], check=True, capture_output=True)
    draft = json.loads((tmp_path / "draft.json").read_text(encoding="utf-8"))
    return {i["id"]: i for i in draft["items"]}


def test_ukrainian_sale_wording_in_the_form(tmp_path):
    events = [appeared(d, "home_new", "capture_form", "Чорна п'ятниця: −15% для нових клієнтів") for d in DEVICES]
    assert judge(tmp_path, events)["H3"]["status"] == "done"


def test_cyrillic_forms_are_told_apart(tmp_path):
    events = [appeared("mobile", "home_new", "capture_form", "Знижка −15% для нових клієнтів"),
              appeared("mobile", "browse_exit", "capture_form", "Не йдіть: безкоштовна доставка", after_exit=True)]
    items = judge(tmp_path, events)
    assert items["F1"]["status"] == "done"
    assert items["E5"]["status"] == "done"


def test_empty_cart_is_not_a_missing_exit_form_or_consent_box(tmp_path):
    events = [exit_tried(d, "exit_cart") for d in DEVICES]
    pages = {d: {"home": {}, "add_to_cart": "failed", "checkout": {"checkboxes": [], "text": "Кошик порожній"}} for d in DEVICES}
    items = judge(tmp_path, events, pages)
    assert items["E4"]["status"] == "cannot_verify"
    assert items["D4"]["status"] == "cannot_verify"


def test_ukrainian_marketing_consent_at_checkout(tmp_path):
    box = {"label": "Підписатися на розсилку новин та акцій", "checked": False}
    pages = {d: {"home": {}, "add_to_cart": "button", "checkout": {"checkboxes": [box], "text": ""}} for d in DEVICES}
    assert judge(tmp_path, [], pages)["D4"]["status"] == "done"


def test_two_step_form_is_multi_step(tmp_path):
    events = [appeared("mobile", "home_new", "capture_form", "Хочу знижку", two_step=True, next_step_text="Ваш email")]
    assert "yes" in judge(tmp_path, events)["I1"]["evidence"]


def test_untranslated_teaser_on_the_other_language(tmp_path):
    events = [appeared("desktop", "home_new", "teaser", "Знижка −15%"), appeared("desktop", "lang", "teaser", "Знижка −15%")]
    plan = {"other_language": {"lang": "ru-UA", "href": "https://store.test/ru/"}}
    pages = {"desktop": {"home": {"lang": "uk"}}, "mobile": {"home": {}}}
    assert judge(tmp_path, events, pages, plan)["M1"]["status"] == "missing"


def test_fieldless_vendor_layer_is_left_for_review_not_missing(tmp_path):
    events = [appeared("mobile", "home_new", "vendor_overlay", "Знижка −15% для нових клієнтів Хочу знижку", vendor="claspo")]
    e1 = judge(tmp_path, events)["E1"]
    assert e1["status"] is None
    assert "mobile_home_new_vendor_overlay.jpg" in e1["screenshots_to_view"]


def test_ukrainian_cart_drawer_is_not_a_popup_without_a_form(tmp_path):
    events = [appeared("mobile", "home_new", "other_overlay", "Кошик порожній. Оформити замовлення")]
    assert judge(tmp_path, events)["L1"]["evidence"] == "None seen."
