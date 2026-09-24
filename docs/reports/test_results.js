window.WAVI_TEST_RESULTS = {
  "timestamp": "2026-09-24 20:08:12",
  "duration": 0.19,
  "total": 59,
  "passed": 59,
  "failed": 0,
  "skipped": 0,
  "exit_code": 0,
  "tests": [
    {
      "doc": "DPR=1: sin escala. Bubble centro crop_y=362, HEADER=60 → bvy=422.",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr1_direct_match",
      "outcome": "passed",
      "duration": 0.000397,
      "longrepr": null
    },
    {
      "doc": "DPR=2 (Retina). Bubble crop_y=586, h=136 → center=654. bvy_css = (654 + 60) / 2 = 357. Botón real a vy=354 → distancia=3px < tolerancia 80px.",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr2_retina_match",
      "outcome": "passed",
      "duration": 0.000166,
      "longrepr": null
    },
    {
      "doc": "Si no se pasa DPR=2 para datos Retina, la misma burbuja NO matchea el botón correcto (demostrando por qué el fix importa).",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr1_would_fail_on_retina_data",
      "outcome": "passed",
      "duration": 0.000151,
      "longrepr": null
    },
    {
      "doc": "Verifica la conversión crop-physical → CSS-viewport con DPR variable. Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_picks_nearest_of_multiple_buttons",
      "outcome": "passed",
      "duration": 0.00015,
      "longrepr": null
    },
    {
      "doc": "Verifica la conversión crop-physical → CSS-viewport con DPR variable. Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_no_match_beyond_tolerance",
      "outcome": "passed",
      "duration": 0.000139,
      "longrepr": null
    },
    {
      "doc": "Verifica la conversión crop-physical → CSS-viewport con DPR variable. Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_empty_buttons_returns_none",
      "outcome": "passed",
      "duration": 0.000145,
      "longrepr": null
    },
    {
      "doc": "Burbuja alta (reply + audio, h=261): el centro se usa para el match.",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_tall_bubble_center_used",
      "outcome": "passed",
      "duration": 0.000284,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_runner.py::TestInstallBlobMonitor::test_calls_evaluate_with_init_script",
      "outcome": "passed",
      "duration": 0.001214,
      "longrepr": null
    },
    {
      "doc": "El script tiene el guard __wavi_installed para no instalar dos veces.",
      "nodeid": "tests/test_runner.py::TestInstallBlobMonitor::test_script_contains_guard",
      "outcome": "passed",
      "duration": 0.000506,
      "longrepr": null
    },
    {
      "doc": "Real bug, 2026-08-26: the mouse cursor left resting over a message's reaction badge (from a prior click — e.g. an audio play button) can trigger WA's hover tooltip ('N reacciones' + who reacted), which then gets captured in the screenshot and corrupts classification of the real messages underneath it — one outgoing message vanished entirely, another got misclassified as incoming with truncated OCR text. Parking the cursor away from the chat before every classification screenshot prevents the tooltip from ever appearing.",
      "nodeid": "tests/test_runner.py::TestGetBubblesParksMouse::test_moves_mouse_away_before_screenshot",
      "outcome": "passed",
      "duration": 0.004402,
      "longrepr": null
    },
    {
      "doc": "Real bug, 2026-08-26: the mouse cursor left resting over a message's reaction badge (from a prior click — e.g. an audio play button) can trigger WA's hover tooltip ('N reacciones' + who reacted), which then gets captured in the screenshot and corrupts classification of the real messages underneath it — one outgoing message vanished entirely, another got misclassified as incoming with truncated OCR text. Parking the cursor away from the chat before every classification screenshot prevents the tooltip from ever appearing.",
      "nodeid": "tests/test_runner.py::TestGetBubblesParksMouse::test_mouse_move_happens_before_screenshot_not_after",
      "outcome": "passed",
      "duration": 0.002735,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_runner.py::TestGetDpr::test_returns_page_device_pixel_ratio",
      "outcome": "passed",
      "duration": 0.000967,
      "longrepr": null
    },
    {
      "doc": "El historial completo tiene IDs 1..N sin huecos ni duplicados (1=newest, N=oldest).",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_ids_sequential_and_unique",
      "outcome": "passed",
      "duration": 0.00209,
      "longrepr": null
    },
    {
      "doc": "Mensajes de scroll-ups más profundos (más antiguos) aparecen antes.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_chronological_order",
      "outcome": "passed",
      "duration": 0.002173,
      "longrepr": null
    },
    {
      "doc": "screen_id mantiene el ID local de la pantalla, aunque id se reasigne globalmente.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_screen_id_preserved",
      "outcome": "passed",
      "duration": 0.002141,
      "longrepr": null
    },
    {
      "doc": "Burbuja en zona de solapamiento entre iteraciones se incluye una sola vez.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_overlap_counted_once",
      "outcome": "passed",
      "duration": 0.001704,
      "longrepr": null
    },
    {
      "doc": "Si el scroll produce una iteración donde todos los candidatos son overlap (no hay mensajes nuevos), el resultado no tiene duplicados ni cambia el orden.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_empty_iteration_is_noop",
      "outcome": "passed",
      "duration": 0.001765,
      "longrepr": null
    },
    {
      "doc": "Dos mensajes con texto idéntico pero timestamp diferente deben contarse ambos. Cubre el riesgo de colisión en el content-key dedup.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_identical_text_different_timestamp_both_survive",
      "outcome": "passed",
      "duration": 0.00282,
      "longrepr": null
    },
    {
      "doc": "_assign_dom_ids asigna el dom_id al bubble más cercano en y.",
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_matches_by_y",
      "outcome": "passed",
      "duration": 0.000234,
      "longrepr": null
    },
    {
      "doc": "No asigna dom_id si está fuera del rango de tolerancia.",
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_no_match_beyond_tolerance",
      "outcome": "passed",
      "duration": 0.000163,
      "longrepr": null
    },
    {
      "doc": "Si dom_msgs está vacío, no asigna nada.",
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_empty_dom_msgs_noop",
      "outcome": "passed",
      "duration": 0.000159,
      "longrepr": null
    },
    {
      "doc": "When anchor has dom_id, finds it in new_bubbles by dom_id regardless of OCR.",
      "nodeid": "tests/test_runner.py::TestAnchorMatchingStrategy::test_anchor_found_by_dom_id_even_if_ocr_differs",
      "outcome": "passed",
      "duration": 0.000135,
      "longrepr": null
    },
    {
      "doc": "When anchor has no dom_id, falls back to bubble_key OCR matching.",
      "nodeid": "tests/test_runner.py::TestAnchorMatchingStrategy::test_anchor_falls_back_to_ocr_when_no_dom_id",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "doc": "Same dom_id → same key, even if OCR text differs.",
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_dom_id_takes_priority_over_ocr",
      "outcome": "passed",
      "duration": 0.000138,
      "longrepr": null
    },
    {
      "doc": "Two identical texts with different dom_ids are distinct messages.",
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_different_dom_ids_not_deduped",
      "outcome": "passed",
      "duration": 0.000125,
      "longrepr": null
    },
    {
      "doc": "Without dom_id, falls back to OCR-based key.",
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_fallback_to_ocr_when_no_dom_id",
      "outcome": "passed",
      "duration": 0.000131,
      "longrepr": null
    },
    {
      "doc": "Normal path: two iterations then scrollTop reaches bottom.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_reaches_bottom",
      "outcome": "passed",
      "duration": 0.00133,
      "longrepr": null
    },
    {
      "doc": "Empty extract_visible_contacts is retried; loop continues after non-empty retry.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_empty_visible_retried",
      "outcome": "passed",
      "duration": 0.001932,
      "longrepr": null
    },
    {
      "doc": "If all retries return empty, loop breaks and returns whatever was collected.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_empty_visible_all_retries_exhausted_breaks",
      "outcome": "passed",
      "duration": 0.00113,
      "longrepr": null
    },
    {
      "doc": "A single stall does not stop the loop; extra wait is added and scroll continues.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_stall_waits_then_continues",
      "outcome": "passed",
      "duration": 0.001816,
      "longrepr": null
    },
    {
      "doc": "Three consecutive stalls stop the scroll even if not at bottom.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_three_consecutive_stalls_stops",
      "outcome": "passed",
      "duration": 0.001432,
      "longrepr": null
    },
    {
      "doc": "list_contacts() with no assets_dir returns contacts, screenshot=None.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_returns_contacts",
      "outcome": "passed",
      "duration": 0.001348,
      "longrepr": null
    },
    {
      "doc": "list_contacts() saves screenshot.png + contacts_list.json to assets_dir.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_with_assets_dir",
      "outcome": "passed",
      "duration": 0.003654,
      "longrepr": null
    },
    {
      "doc": "list_contacts() calls session.close() even if _scroll_all_contacts fails.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_closes_on_error",
      "outcome": "passed",
      "duration": 0.00122,
      "longrepr": null
    },
    {
      "doc": "list_contacts() raises RuntimeError when session is not authenticated.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_raises_if_not_authenticated",
      "outcome": "passed",
      "duration": 0.00113,
      "longrepr": null
    },
    {
      "doc": "Si no hay burbujas de audio, devuelve lista vacía.",
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_returns_empty_for_no_audio_bubbles",
      "outcome": "passed",
      "duration": 0.000751,
      "longrepr": null
    },
    {
      "doc": "Procesa solo audio_bubbles, ignora text y file.",
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_filters_out_non_audio_bubbles",
      "outcome": "passed",
      "duration": 0.001374,
      "longrepr": null
    },
    {
      "doc": "Bubble with dom_id already in downloaded_ids is skipped.",
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_skips_already_downloaded_dom_id",
      "outcome": "passed",
      "duration": 0.00117,
      "longrepr": null
    },
    {
      "doc": "Given existing JSON with some bubbles, newest=True stops at first duplicate.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_stops_at_first_duplicate",
      "outcome": "passed",
      "duration": 0.003134,
      "longrepr": null
    },
    {
      "doc": "If no history_bubbles.json exists, newest=True falls back to normal full capture.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_falls_back_when_no_json",
      "outcome": "passed",
      "duration": 0.002748,
      "longrepr": null
    },
    {
      "doc": "After merge, id=1 should be newest; ids should be sequential 1..N.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_merges_and_renumbers",
      "outcome": "passed",
      "duration": 0.003063,
      "longrepr": null
    },
    {
      "doc": "Regression test for the bug where fast-forward reached scrollTop<20 WITHOUT finding the anchor (because WA recycled the DOM id), and incorrectly returned [] with completed=True — skipping messages that were actually visible at the top. Fix: when scrollTop<20 is hit before anchor is found, break (don't return []) and fall through to dedup scan from that position.",
      "nodeid": "tests/test_runner.py::TestGrowFastForwardAnchorRecycled::test_captures_old_messages_when_anchor_dom_id_recycled",
      "outcome": "passed",
      "duration": 0.003878,
      "longrepr": null
    },
    {
      "doc": "No updates.json → status first_run regardless of sidebar content.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_first_run_no_previous_state",
      "outcome": "passed",
      "duration": 0.00301,
      "longrepr": null
    },
    {
      "doc": "reset=True → first_run even when updates.json exists.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_reset_forces_first_run",
      "outcome": "passed",
      "duration": 0.002133,
      "longrepr": null
    },
    {
      "doc": "Same last_message on every row → no_updates.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_no_updates_when_sidebar_unchanged",
      "outcome": "passed",
      "duration": 0.002162,
      "longrepr": null
    },
    {
      "doc": "One inbound last_message change → updates with that contact.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_detects_single_new_inbound",
      "outcome": "passed",
      "duration": 0.00311,
      "longrepr": null
    },
    {
      "doc": "Multiple chats with new inbound messages → all reported.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_detects_multiple_new_inbound",
      "outcome": "passed",
      "duration": 0.002477,
      "longrepr": null
    },
    {
      "doc": "A changed last_message with direction=outbound is NOT an update.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_outbound_change_not_reported",
      "outcome": "passed",
      "duration": 0.002559,
      "longrepr": null
    },
    {
      "doc": "Mixed sidebar: only inbound changes reported, outbound silently ignored.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_only_inbound_reported_among_mixed",
      "outcome": "passed",
      "duration": 0.002094,
      "longrepr": null
    },
    {
      "doc": "A contact not in previous state with inbound direction → reported.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_new_contact_inbound_reported",
      "outcome": "passed",
      "duration": 0.002629,
      "longrepr": null
    },
    {
      "doc": "Una sola convención para history_bubbles.json, la escriba quien la escriba: orden newest → oldest, id=1 el más nuevo. Antes la captura fresca escribía oldest-first y --newest asumía newest-first: un --newest sobre una captura fresca dejaba el archivo con una costura en el medio y sin orden global (caso real: javier_lurgo, 336 burbujas).",
      "nodeid": "tests/test_runner.py::TestHistoryFileOrder::test_fresh_capture_writes_newest_first",
      "outcome": "passed",
      "duration": 0.002807,
      "longrepr": null
    },
    {
      "doc": "Una sola convención para history_bubbles.json, la escriba quien la escriba: orden newest → oldest, id=1 el más nuevo. Antes la captura fresca escribía oldest-first y --newest asumía newest-first: un --newest sobre una captura fresca dejaba el archivo con una costura en el medio y sin orden global (caso real: javier_lurgo, 336 burbujas).",
      "nodeid": "tests/test_runner.py::TestHistoryFileOrder::test_normalize_flips_legacy_ascending_file",
      "outcome": "passed",
      "duration": 0.000176,
      "longrepr": null
    },
    {
      "doc": "Una sola convención para history_bubbles.json, la escriba quien la escriba: orden newest → oldest, id=1 el más nuevo. Antes la captura fresca escribía oldest-first y --newest asumía newest-first: un --newest sobre una captura fresca dejaba el archivo con una costura en el medio y sin orden global (caso real: javier_lurgo, 336 burbujas).",
      "nodeid": "tests/test_runner.py::TestHistoryFileOrder::test_normalize_keeps_newest_first_file",
      "outcome": "passed",
      "duration": 0.000154,
      "longrepr": null
    },
    {
      "doc": "Un --newest viejo sobre una captura fresca vieja dejaba dos tramos ascendentes pegados: [nuevo asc][viejo asc]. Los extremos engañan (el primero es más nuevo que el último), así que hay que ordenar de verdad, y las burbujas sin fecha viajan pegadas a su vecina anterior.",
      "nodeid": "tests/test_runner.py::TestHistoryFileOrder::test_normalize_repairs_file_with_a_seam",
      "outcome": "passed",
      "duration": 0.000152,
      "longrepr": null
    },
    {
      "doc": "Una sola convención para history_bubbles.json, la escriba quien la escriba: orden newest → oldest, id=1 el más nuevo. Antes la captura fresca escribía oldest-first y --newest asumía newest-first: un --newest sobre una captura fresca dejaba el archivo con una costura en el medio y sin orden global (caso real: javier_lurgo, 336 burbujas).",
      "nodeid": "tests/test_runner.py::TestHistoryFileOrder::test_normalize_leaves_undated_file_alone",
      "outcome": "passed",
      "duration": 0.000192,
      "longrepr": null
    },
    {
      "doc": "Una burbuja queda con 'HH:MM' pelado cuando su captura no mostró la pastilla de día. Hereda el día del vecino con fecha más cercano; en empate gana el más viejo (la pastilla que la gobierna está arriba).",
      "nodeid": "tests/test_runner.py::TestFillMissingDates::test_bare_time_takes_nearest_dated_neighbour",
      "outcome": "passed",
      "duration": 0.000158,
      "longrepr": null
    },
    {
      "doc": "Una burbuja queda con 'HH:MM' pelado cuando su captura no mostró la pastilla de día. Hereda el día del vecino con fecha más cercano; en empate gana el más viejo (la pastilla que la gobierna está arriba).",
      "nodeid": "tests/test_runner.py::TestFillMissingDates::test_tie_prefers_older_neighbour",
      "outcome": "passed",
      "duration": 0.000128,
      "longrepr": null
    },
    {
      "doc": "Una burbuja queda con 'HH:MM' pelado cuando su captura no mostró la pastilla de día. Hereda el día del vecino con fecha más cercano; en empate gana el más viejo (la pastilla que la gobierna está arriba).",
      "nodeid": "tests/test_runner.py::TestFillMissingDates::test_none_and_full_timestamps_untouched",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "doc": "Una burbuja queda con 'HH:MM' pelado cuando su captura no mostró la pastilla de día. Hereda el día del vecino con fecha más cercano; en empate gana el más viejo (la pastilla que la gobierna está arriba).",
      "nodeid": "tests/test_runner.py::TestFillMissingDates::test_nothing_to_anchor_on",
      "outcome": "passed",
      "duration": 0.000327,
      "longrepr": null
    }
  ]
};
