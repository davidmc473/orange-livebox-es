"""Tests del parser de CGI JavaScript (T021)."""

from __future__ import annotations

from custom_components.orange_livebox_es.api.jsparse import parse_js, uri_decode


def test_scalars_and_quotes() -> None:
    doc = parse_js(
        "var a='uno';\nvar b=\"dos\";\nvar c=42;\nvar d=-18.5;\nvar e=null;\n"
        "var f=true;\nvar g='con \\'escape\\' y \\n salto';\n"
    )
    assert doc.vars == {
        "a": "uno",
        "b": "dos",
        "c": 42,
        "d": -18.5,
        "e": None,
        "f": True,
        "g": "con 'escape' y \n salto",
    }


def test_arrays_objects_unquoted_keys_and_trailing_null() -> None:
    doc = parse_js(
        "var lst=[['1','up','1G','FD'],null];\n"
        "var leds=[ {'internet':['white','on']},{'wifi':['green','off']}];\n"
        "var sec={'legacy':[{t:'WPA2',v:'wpa2'},],n:1};\n"
        "var multi=[ 'a','b'\n,'c'\n];\n"
    )
    assert doc.vars["lst"] == [["1", "up", "1G", "FD"], None]
    assert doc.vars["leds"][1] == {"wifi": ["green", "off"]}
    assert doc.vars["sec"] == {"legacy": [{"t": "WPA2", "v": "wpa2"}], "n": 1}
    assert doc.vars["multi"] == ["a", "b", "c"]


def test_non_literals_are_ignored() -> None:
    doc = parse_js(
        "var x=parseInt('0'+'',10);\nvar y=foo.bar;\nvar z='ok';\n"
        'uptime=(uptime!="")?parseInt(uptime):0;\nvar i=0,len=1;\n'
    )
    assert doc.vars == {"z": "ok"}


def test_reassignment_without_var_overrides() -> None:
    doc = parse_js('var st={};\nvar p=\'x\';\nst={"phy_link":1,"rx":"-18.1"};\n')
    assert doc.vars["st"] == {"phy_link": 1, "rx": "-18.1"}


def test_assignments_inside_functions_are_ignored() -> None:
    doc = parse_js(
        "var keep='top';\n"
        "(function(){\nkeep='inner';\nvar local=[1];\n})();\n"
        "function f(){\nif(a){\nother='x';}}\n"
    )
    assert doc.vars == {"keep": "top"}


def test_braces_inside_strings_do_not_break_depth() -> None:
    doc = parse_js("var s='{{{';\nvar t=\"}\";\nvar u=1;\n")
    assert doc.vars == {"s": "{{{", "t": "}", "u": 1}


def test_addcfg_entries_and_uri_decoding() -> None:
    doc = parse_js(
        'addCfg("wl_ssid24G", "196672001000", "Mi%20WiFi%20%C3%B1");\n'
        'addCfg("empty", "1", "");\n'
        'addCfg("enc", "2", "%aa%bb", 1);\n'
        'addCfg("bad", "3", someVar);\n'
        'function frmHead(){addCfg("gui_cehck_token", "983272000000", "2031700051");}\n'
    )
    assert doc.cfg["wl_ssid24G"].id == "196672001000"
    assert doc.cfg_value("wl_ssid24G") == "Mi WiFi ñ"
    assert doc.cfg_value("empty") == ""
    assert doc.cfg["enc"].encrypted is True
    assert "bad" not in doc.cfg
    assert doc.cfg_value("gui_cehck_token") == "2031700051"
    assert doc.cfg_value("missing", "def") == "def"


def test_uri_decode_fallbacks() -> None:
    assert uri_decode("100%") == "100%"
    assert uri_decode("%zz") == "%zz"
    assert uri_decode("%ff%fe") == "%ff%fe"  # UTF-8 inválido → original
    assert uri_decode("a+b") == "a+b"  # decodeURIComponent no convierte '+'


def test_real_fixtures_parse(fixture_docs: dict) -> None:
    clients = fixture_docs["clients"]
    assert len(clients.vars["online_client"]) == 7
    assert len(clients.vars["station_info"]["stations"]) == 4
    assert clients.vars["topology_info"]["nodes"][0]["sta_num"] == "4"
    # la reasignación de dentro del IIFE no pisa la variable de nivel superior
    assert clients.vars["client_list"] == []
    ftth = fixture_docs["infoFtth"]
    assert ftth.vars["traciver_status"]["rx_power"] == "-18.181"
