import pytest

from pages import (COUNTRY_PICKER_UNDER_CONSENT, FOREIGN_CL_CLASSES, HIDDEN_CART_DRAWER, HIDDEN_CART_DRAWER_NO_POINTER,
                   claspo_box, claspo_launcher, page)


def overlays(run_js, html):
    return run_js(html, "detect")["overlays"]


def only(found):
    assert len(found) == 1, found
    return found[0]


def test_claspo_first_step_is_seen_with_its_text(run_js):
    o = only(overlays(run_js, page(claspo_box("Get 10% off your first order", "Get 10%"))))
    assert o["vendor"] == "claspo"
    assert o["coverage_pct"] == 24.6
    assert "Get 10% off your first order" in o["text"]
    assert o["kind"] == "vendor_overlay"
    assert o["has_email"] is False


def test_email_field_two_shadow_roots_deep_makes_a_capture_form(run_js):
    html = page(claspo_box("Get 10% off your first order", "Get 10%")).replace(
        "root.innerHTML = '<div><x-text", "root.innerHTML = '<div><x-email></x-email><x-text", 1)
    o = only(overlays(run_js, html))
    assert o["has_email"] is True
    assert o["kind"] == "capture_form"


def test_claspo_launcher_is_a_teaser(run_js):
    found = overlays(run_js, page(claspo_launcher("Get 10%")))
    assert [(o["kind"], o["vendor"]) for o in found] == [("teaser", "claspo")]
    assert "Get 10%" in found[0]["text"]


def test_ukrainian_text_survives(run_js):
    o = only(overlays(run_js, page(claspo_box("Знижка −15% для нових клієнтів", "Хочу знижку"), lang="uk")))
    assert "Знижка −15% для нових клієнтів" in o["text"]
    assert "Хочу знижку" in o["text"]


@pytest.mark.parametrize("drawer", [HIDDEN_CART_DRAWER, HIDDEN_CART_DRAWER_NO_POINTER])
def test_fixed_drawer_behind_the_page_is_not_a_popup(run_js, drawer):
    assert overlays(run_js, page(drawer)) == []


def test_layer_covered_by_another_layer_still_counts(run_js):
    kinds = sorted(o["kind"] for o in overlays(run_js, page(COUNTRY_PICKER_UNDER_CONSENT)))
    assert kinds == ["cookie_banner", "geo_notice"]


def test_other_cl_prefixed_classes_are_not_claspo(run_js):
    found = overlays(run_js, page(FOREIGN_CL_CLASSES))
    assert [o["vendor"] for o in found] == [None]


@pytest.mark.parametrize("label", ["Loading...", "Завантаження...", "Загрузка…"])
def test_loading_mask_is_not_a_popup(run_js, label):
    mask = f"<div style='position:fixed;inset:0;z-index:999;background:rgba(255,255,255,.6)'><p>{label}</p></div>"
    assert overlays(run_js, page(mask)) == []
