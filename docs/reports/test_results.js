window.WAVI_TEST_RESULTS = {
  "timestamp": "2026-09-18 19:35:52",
  "duration": 162.23,
  "total": 21,
  "passed": 21,
  "failed": 0,
  "skipped": 0,
  "exit_code": 0,
  "tests": [
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_compose_area[gracias_rodo_reaction]",
      "outcome": "passed",
      "duration": 34.354877,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_compose_area[lurgo_000]",
      "outcome": "passed",
      "duration": 25.868967,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_compose_area[lurgo_001]",
      "outcome": "passed",
      "duration": 26.951063,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_compose_area[lurgo_002]",
      "outcome": "passed",
      "duration": 20.774665,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_compose_area[sidebar_full_000]",
      "outcome": "passed",
      "duration": 9.958872,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_compose_area[tireless_000]",
      "outcome": "passed",
      "duration": 18.345149,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_sidebar_rows[gracias_rodo_reaction]",
      "outcome": "passed",
      "duration": 3.452136,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_sidebar_rows[lurgo_000]",
      "outcome": "passed",
      "duration": 3.957295,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_sidebar_rows[lurgo_001]",
      "outcome": "passed",
      "duration": 3.529799,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_sidebar_rows[lurgo_002]",
      "outcome": "passed",
      "duration": 3.677571,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_sidebar_rows[sidebar_full_000]",
      "outcome": "passed",
      "duration": 4.284474,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_sidebar_rows[tireless_000]",
      "outcome": "passed",
      "duration": 1.260999,
      "longrepr": null
    },
    {
      "doc": "First validation of parse_contacts_panel_rows against real OCR — until now it only had synthetic unit coverage (see its docstring in wavi/vision_grounding.py). Same smoke-check shape as test_parse_sidebar_rows (row count + bbox + name-majority), minus the timestamp check: contacts panel rows never carry one by design (name + subtitle only).",
      "nodeid": "tests/test_corpus_grounding.py::test_parse_contacts_panel_rows[nuevo_chat_panel_000]",
      "outcome": "passed",
      "duration": 0.952547,
      "longrepr": null
    },
    {
      "doc": "`direction` validated against real OCR + real tick icons, not just the synthetic mocks in tests/test_vision_grounding.py. Only asserts the rows a human hand-reviewed and marked unambiguous in expected_direction.json (`outbound_rows`) — this heuristic has known false positives/negatives (see _detect_row_direction's docstring), so this deliberately does NOT assert on every row like test_parse_sidebar_rows does for name/timestamp; existence of ground truth beats broad but noisy coverage here.",
      "nodeid": "tests/test_corpus_grounding.py::test_sidebar_direction_matches_ground_truth[sidebar_full_000]",
      "outcome": "passed",
      "duration": 4.379256,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[gracias_rodo_reaction]",
      "outcome": "passed",
      "duration": 0.064535,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[lurgo_000]",
      "outcome": "passed",
      "duration": 0.065664,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[lurgo_001]",
      "outcome": "passed",
      "duration": 0.060854,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[lurgo_002]",
      "outcome": "passed",
      "duration": 0.062658,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[nuevo_chat_panel_000]",
      "outcome": "passed",
      "duration": 0.053364,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[sidebar_full_000]",
      "outcome": "passed",
      "duration": 0.05427,
      "longrepr": null
    },
    {
      "doc": "locate_new_chat_button() validated against real screenshots, both positive (the button is there and green) and negative — including two corpus cases (lurgo_000, tireless_000) that predate this exact WA redesign and show the *old* header (a monochrome \"archive\" icon, no green button at all), confirmed by eye while building this test. That the function correctly returns None for those, not just for nuevo_chat_panel_000 (a different screen entirely), is real evidence for this migration's premise: WA's UI drifts under us, and a color+shape vision signal tracks that drift better than a DOM selector tied to one specific icon.",
      "nodeid": "tests/test_corpus_grounding.py::test_locate_new_chat_button_matches_ground_truth[tireless_000]",
      "outcome": "passed",
      "duration": 0.060447,
      "longrepr": null
    }
  ]
};
