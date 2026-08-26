window.WAVI_TEST_RESULTS = {
  "timestamp": "2026-08-26 17:05:34",
  "duration": 1.0,
  "total": 212,
  "passed": 207,
  "failed": 0,
  "skipped": 5,
  "exit_code": 0,
  "tests": [
    {
      "doc": "Vision pipeline metrics on one golden screenshot must meet thresholds.",
      "nodeid": "tests/test_corpus.py::test_corpus_case[gracias_rodo_reaction]",
      "outcome": "skipped",
      "duration": 0.000247,
      "longrepr": "('/Users/josetabuyo/Development/wavi/tests/test_corpus.py', 53, 'Skipped: corpus eval is slow (real OCR) — set WAVI_CORPUS=1 or run `make corpus`')"
    },
    {
      "doc": "Vision pipeline metrics on one golden screenshot must meet thresholds.",
      "nodeid": "tests/test_corpus.py::test_corpus_case[lurgo_000]",
      "outcome": "skipped",
      "duration": 0.000689,
      "longrepr": "('/Users/josetabuyo/Development/wavi/tests/test_corpus.py', 53, 'Skipped: corpus eval is slow (real OCR) — set WAVI_CORPUS=1 or run `make corpus`')"
    },
    {
      "doc": "Vision pipeline metrics on one golden screenshot must meet thresholds.",
      "nodeid": "tests/test_corpus.py::test_corpus_case[lurgo_001]",
      "outcome": "skipped",
      "duration": 0.000318,
      "longrepr": "('/Users/josetabuyo/Development/wavi/tests/test_corpus.py', 53, 'Skipped: corpus eval is slow (real OCR) — set WAVI_CORPUS=1 or run `make corpus`')"
    },
    {
      "doc": "Vision pipeline metrics on one golden screenshot must meet thresholds.",
      "nodeid": "tests/test_corpus.py::test_corpus_case[lurgo_002]",
      "outcome": "skipped",
      "duration": 0.000221,
      "longrepr": "('/Users/josetabuyo/Development/wavi/tests/test_corpus.py', 53, 'Skipped: corpus eval is slow (real OCR) — set WAVI_CORPUS=1 or run `make corpus`')"
    },
    {
      "doc": "Vision pipeline metrics on one golden screenshot must meet thresholds.",
      "nodeid": "tests/test_corpus.py::test_corpus_case[tireless_000]",
      "outcome": "skipped",
      "duration": 0.000109,
      "longrepr": "('/Users/josetabuyo/Development/wavi/tests/test_corpus.py', 53, 'Skipped: corpus eval is slow (real OCR) — set WAVI_CORPUS=1 or run `make corpus`')"
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_events.py::test_log_event_writes_valid_json_line",
      "outcome": "passed",
      "duration": 0.007182,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_events.py::test_log_event_appends_not_overwrites",
      "outcome": "passed",
      "duration": 0.001189,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_events.py::test_log_event_never_raises_on_bad_dir",
      "outcome": "passed",
      "duration": 0.000651,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_events.py::test_read_events_filters_by_session",
      "outcome": "passed",
      "duration": 0.000773,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_events.py::test_read_events_respects_limit",
      "outcome": "passed",
      "duration": 0.001538,
      "longrepr": null
    },
    {
      "doc": "The type of the None singleton.",
      "nodeid": "tests/test_events.py::test_read_events_returns_empty_list_when_no_log",
      "outcome": "passed",
      "duration": 0.000523,
      "longrepr": null
    },
    {
      "doc": "El evento más crítico del ADR-009: cuando --new archiva un perfil existente en vez de borrarlo, debe quedar registrado con el nombre del archivo destino.",
      "nodeid": "tests/test_events.py::test_critical_profile_archived_event_is_logged",
      "outcome": "passed",
      "duration": 0.000594,
      "longrepr": null
    },
    {
      "doc": "If daemon was already running, _stop_daemon_for_profile is never called.",
      "nodeid": "tests/test_lazy_session.py::TestLazySessionAlreadyRunning::test_no_stop_when_daemon_was_running",
      "outcome": "passed",
      "duration": 0.001225,
      "longrepr": null
    },
    {
      "doc": "If daemon was NOT running before, and command left a PID file, stop it.",
      "nodeid": "tests/test_lazy_session.py::TestLazyInvocationStopsDaemon::test_stops_daemon_started_by_command",
      "outcome": "passed",
      "duration": 0.001377,
      "longrepr": null
    },
    {
      "doc": "If daemon wasn't running and command left no PID file, no stop called.",
      "nodeid": "tests/test_lazy_session.py::TestLazyInvocationStopsDaemon::test_no_stop_if_command_left_no_pid_file",
      "outcome": "passed",
      "duration": 0.00114,
      "longrepr": null
    },
    {
      "doc": "Cleanup errors in finally block must not propagate.",
      "nodeid": "tests/test_lazy_session.py::TestLazyInvocationStopsDaemon::test_stop_exception_is_swallowed",
      "outcome": "passed",
      "duration": 0.001422,
      "longrepr": null
    },
    {
      "doc": "wa-session-guard: el capturador de QR bajo demanda nunca debe navegar ni recargar la tab — solo lee su estado actual vía CDP.",
      "nodeid": "tests/test_qr_server.py::TestNeverNavigates::test_fetch_qr_never_calls_goto",
      "outcome": "passed",
      "duration": 0.000909,
      "longrepr": null
    },
    {
      "doc": "wa-session-guard: el capturador de QR bajo demanda nunca debe navegar ni recargar la tab — solo lee su estado actual vía CDP.",
      "nodeid": "tests/test_qr_server.py::TestNeverNavigates::test_check_status_never_calls_goto",
      "outcome": "passed",
      "duration": 0.00039,
      "longrepr": null
    },
    {
      "doc": "wa-session-guard: el capturador de QR bajo demanda nunca debe navegar ni recargar la tab — solo lee su estado actual vía CDP.",
      "nodeid": "tests/test_qr_server.py::TestNeverNavigates::test_fetch_qr_never_calls_reload",
      "outcome": "passed",
      "duration": 0.000482,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_qr_server.py::TestFetchQr::test_returns_restored_when_authenticated",
      "outcome": "passed",
      "duration": 0.002137,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_qr_server.py::TestFetchQr::test_returns_qr_b64_and_ref_when_qr_needed",
      "outcome": "passed",
      "duration": 0.001425,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_qr_server.py::TestFetchQr::test_returns_error_dict_on_exception",
      "outcome": "passed",
      "duration": 0.000724,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_qr_server.py::TestCheckStatus::test_restored_when_auth_selector_present",
      "outcome": "passed",
      "duration": 0.001827,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_qr_server.py::TestCheckStatus::test_expired_when_ref_changed",
      "outcome": "passed",
      "duration": 0.001945,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_qr_server.py::TestCheckStatus::test_waiting_when_ref_unchanged",
      "outcome": "passed",
      "duration": 0.001438,
      "longrepr": null
    },
    {
      "doc": "`kill <pid>` sends SIGTERM, which does NOT raise KeyboardInterrupt — only Ctrl-C (SIGINT) does. Without an explicit SIGTERM handler, serve()'s finally block (which releases the port) never runs, leaking a GHOST registration in 'las ports audit' forever. Found 2026-08-21 when three 'wavi qr' processes killed via `kill` left three orphaned claims.",
      "nodeid": "tests/test_qr_server.py::TestPortReleasedOnSigterm::test_serve_installs_a_sigterm_handler",
      "outcome": "passed",
      "duration": 0.000387,
      "longrepr": null
    },
    {
      "doc": "ADR-008 / .agent.json: cualquier puerto que este proceso escuche debe pasar por el registry de la Local Agent Society, para que 'las ports audit' lo vea — nunca un bind directo e invisible.",
      "nodeid": "tests/test_qr_server.py::TestPortClaimedFromSociety::test_claim_port_hits_society_registry_first",
      "outcome": "passed",
      "duration": 0.007923,
      "longrepr": null
    },
    {
      "doc": "ADR-008 / .agent.json: cualquier puerto que este proceso escuche debe pasar por el registry de la Local Agent Society, para que 'las ports audit' lo vea — nunca un bind directo e invisible.",
      "nodeid": "tests/test_qr_server.py::TestPortClaimedFromSociety::test_claim_port_falls_back_to_os_ephemeral_if_society_down",
      "outcome": "passed",
      "duration": 0.000315,
      "longrepr": null
    },
    {
      "doc": "El usuario pidió explícitamente señales sonoras al cargar la web.",
      "nodeid": "tests/test_qr_server.py::TestPageHasSoundCues::test_page_beeps_on_load",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "doc": "El usuario pidió explícitamente señales sonoras al cargar la web.",
      "nodeid": "tests/test_qr_server.py::TestPageHasSoundCues::test_page_uses_web_audio_no_external_assets",
      "outcome": "passed",
      "duration": 0.000133,
      "longrepr": null
    },
    {
      "doc": "El usuario pidió que apretar 'Buscar QR' sea el único paso — que arranque el daemon si hace falta, sin exigir 'wavi connect' antes.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_ensure_daemon_reuses_existing_daemon_without_relaunching",
      "outcome": "passed",
      "duration": 0.001085,
      "longrepr": null
    },
    {
      "doc": "A reused daemon might be sitting at about:blank from a previous run — _check_session_status (which navigates to WA) must run either way, not just on a fresh launch.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_ensure_daemon_navigates_even_when_reusing_daemon",
      "outcome": "passed",
      "duration": 0.001604,
      "longrepr": null
    },
    {
      "doc": "El usuario pidió que apretar 'Buscar QR' sea el único paso — que arranque el daemon si hace falta, sin exigir 'wavi connect' antes.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_ensure_daemon_launches_when_not_alive",
      "outcome": "passed",
      "duration": 0.002281,
      "longrepr": null
    },
    {
      "doc": "El usuario pidió que apretar 'Buscar QR' sea el único paso — que arranque el daemon si hace falta, sin exigir 'wavi connect' antes.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_ensure_daemon_reports_error_if_cdp_never_comes_up",
      "outcome": "passed",
      "duration": 0.001701,
      "longrepr": null
    },
    {
      "doc": "La regresión concreta: 'wavi qr' ya no debe cortar con sys.exit si el daemon está parado — eso ahora lo maneja el botón.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_qr_cmd_does_not_require_daemon_alive_upfront",
      "outcome": "passed",
      "duration": 0.001135,
      "longrepr": null
    },
    {
      "doc": "El usuario aceptó window.close() como intento best-effort, con cierre manual como fallback aceptable si el navegador lo bloquea.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_page_closes_itself_on_success",
      "outcome": "passed",
      "duration": 0.000185,
      "longrepr": null
    },
    {
      "doc": "El usuario pidió que apretar 'Buscar QR' sea el único paso — que arranque el daemon si hace falta, sin exigir 'wavi connect' antes.",
      "nodeid": "tests/test_qr_server.py::TestSelfContainedEntryPoint::test_handler_source_sets_shutdown_event_on_restored",
      "outcome": "passed",
      "duration": 0.000504,
      "longrepr": null
    },
    {
      "doc": "DPR=1: sin escala. Bubble centro crop_y=362, HEADER=60 → bvy=422.",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr1_direct_match",
      "outcome": "passed",
      "duration": 0.000197,
      "longrepr": null
    },
    {
      "doc": "DPR=2 (Retina). Bubble crop_y=586, h=136 → center=654. bvy_css = (654 + 60) / 2 = 357. Botón real a vy=354 → distancia=3px < tolerancia 80px.",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr2_retina_match",
      "outcome": "passed",
      "duration": 0.000155,
      "longrepr": null
    },
    {
      "doc": "Si no se pasa DPR=2 para datos Retina, la misma burbuja NO matchea el botón correcto (demostrando por qué el fix importa).",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr1_would_fail_on_retina_data",
      "outcome": "passed",
      "duration": 0.000148,
      "longrepr": null
    },
    {
      "doc": "Verifica la conversión crop-physical → CSS-viewport con DPR variable. Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_picks_nearest_of_multiple_buttons",
      "outcome": "passed",
      "duration": 0.000143,
      "longrepr": null
    },
    {
      "doc": "Verifica la conversión crop-physical → CSS-viewport con DPR variable. Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_no_match_beyond_tolerance",
      "outcome": "passed",
      "duration": 0.000142,
      "longrepr": null
    },
    {
      "doc": "Verifica la conversión crop-physical → CSS-viewport con DPR variable. Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_empty_buttons_returns_none",
      "outcome": "passed",
      "duration": 0.000148,
      "longrepr": null
    },
    {
      "doc": "Burbuja alta (reply + audio, h=261): el centro se usa para el match.",
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_tall_bubble_center_used",
      "outcome": "passed",
      "duration": 0.000151,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_runner.py::TestInstallBlobMonitor::test_calls_evaluate_with_init_script",
      "outcome": "passed",
      "duration": 0.001135,
      "longrepr": null
    },
    {
      "doc": "El script tiene el guard __wavi_installed para no instalar dos veces.",
      "nodeid": "tests/test_runner.py::TestInstallBlobMonitor::test_script_contains_guard",
      "outcome": "passed",
      "duration": 0.0007,
      "longrepr": null
    },
    {
      "doc": "Real bug, 2026-08-26: the mouse cursor left resting over a message's reaction badge (from a prior click — e.g. an audio play button) can trigger WA's hover tooltip ('N reacciones' + who reacted), which then gets captured in the screenshot and corrupts classification of the real messages underneath it — one outgoing message vanished entirely, another got misclassified as incoming with truncated OCR text. Parking the cursor away from the chat before every classification screenshot prevents the tooltip from ever appearing.",
      "nodeid": "tests/test_runner.py::TestGetBubblesParksMouse::test_moves_mouse_away_before_screenshot",
      "outcome": "passed",
      "duration": 0.00288,
      "longrepr": null
    },
    {
      "doc": "Real bug, 2026-08-26: the mouse cursor left resting over a message's reaction badge (from a prior click — e.g. an audio play button) can trigger WA's hover tooltip ('N reacciones' + who reacted), which then gets captured in the screenshot and corrupts classification of the real messages underneath it — one outgoing message vanished entirely, another got misclassified as incoming with truncated OCR text. Parking the cursor away from the chat before every classification screenshot prevents the tooltip from ever appearing.",
      "nodeid": "tests/test_runner.py::TestGetBubblesParksMouse::test_mouse_move_happens_before_screenshot_not_after",
      "outcome": "passed",
      "duration": 0.003701,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_runner.py::TestGetDpr::test_returns_page_device_pixel_ratio",
      "outcome": "passed",
      "duration": 0.001094,
      "longrepr": null
    },
    {
      "doc": "El historial completo tiene IDs 1..N sin huecos ni duplicados (1=newest, N=oldest).",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_ids_sequential_and_unique",
      "outcome": "passed",
      "duration": 0.002295,
      "longrepr": null
    },
    {
      "doc": "Mensajes de scroll-ups más profundos (más antiguos) aparecen antes.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_chronological_order",
      "outcome": "passed",
      "duration": 0.003289,
      "longrepr": null
    },
    {
      "doc": "screen_id mantiene el ID local de la pantalla, aunque id se reasigne globalmente.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_screen_id_preserved",
      "outcome": "passed",
      "duration": 0.002099,
      "longrepr": null
    },
    {
      "doc": "Burbuja en zona de solapamiento entre iteraciones se incluye una sola vez.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_overlap_counted_once",
      "outcome": "passed",
      "duration": 0.002036,
      "longrepr": null
    },
    {
      "doc": "Si el scroll produce una iteración donde todos los candidatos son overlap (no hay mensajes nuevos), el resultado no tiene duplicados ni cambia el orden.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_empty_iteration_is_noop",
      "outcome": "passed",
      "duration": 0.002808,
      "longrepr": null
    },
    {
      "doc": "Dos mensajes con texto idéntico pero timestamp diferente deben contarse ambos. Cubre el riesgo de colisión en el content-key dedup.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_identical_text_different_timestamp_both_survive",
      "outcome": "passed",
      "duration": 0.002166,
      "longrepr": null
    },
    {
      "doc": "_assign_dom_ids asigna el dom_id al bubble más cercano en y.",
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_matches_by_y",
      "outcome": "passed",
      "duration": 0.000221,
      "longrepr": null
    },
    {
      "doc": "No asigna dom_id si está fuera del rango de tolerancia.",
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_no_match_beyond_tolerance",
      "outcome": "passed",
      "duration": 0.000177,
      "longrepr": null
    },
    {
      "doc": "Si dom_msgs está vacío, no asigna nada.",
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_empty_dom_msgs_noop",
      "outcome": "passed",
      "duration": 0.000165,
      "longrepr": null
    },
    {
      "doc": "When anchor has dom_id, finds it in new_bubbles by dom_id regardless of OCR.",
      "nodeid": "tests/test_runner.py::TestAnchorMatchingStrategy::test_anchor_found_by_dom_id_even_if_ocr_differs",
      "outcome": "passed",
      "duration": 0.000159,
      "longrepr": null
    },
    {
      "doc": "When anchor has no dom_id, falls back to bubble_key OCR matching.",
      "nodeid": "tests/test_runner.py::TestAnchorMatchingStrategy::test_anchor_falls_back_to_ocr_when_no_dom_id",
      "outcome": "passed",
      "duration": 0.000144,
      "longrepr": null
    },
    {
      "doc": "Same dom_id → same key, even if OCR text differs.",
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_dom_id_takes_priority_over_ocr",
      "outcome": "passed",
      "duration": 0.000141,
      "longrepr": null
    },
    {
      "doc": "Two identical texts with different dom_ids are distinct messages.",
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_different_dom_ids_not_deduped",
      "outcome": "passed",
      "duration": 0.000138,
      "longrepr": null
    },
    {
      "doc": "Without dom_id, falls back to OCR-based key.",
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_fallback_to_ocr_when_no_dom_id",
      "outcome": "passed",
      "duration": 0.000133,
      "longrepr": null
    },
    {
      "doc": "Normal path: two iterations then scrollTop reaches bottom.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_reaches_bottom",
      "outcome": "passed",
      "duration": 0.001967,
      "longrepr": null
    },
    {
      "doc": "Empty extract_visible_contacts is retried; loop continues after non-empty retry.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_empty_visible_retried",
      "outcome": "passed",
      "duration": 0.001787,
      "longrepr": null
    },
    {
      "doc": "If all retries return empty, loop breaks and returns whatever was collected.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_empty_visible_all_retries_exhausted_breaks",
      "outcome": "passed",
      "duration": 0.004364,
      "longrepr": null
    },
    {
      "doc": "A single stall does not stop the loop; extra wait is added and scroll continues.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_stall_waits_then_continues",
      "outcome": "passed",
      "duration": 0.003374,
      "longrepr": null
    },
    {
      "doc": "Three consecutive stalls stop the scroll even if not at bottom.",
      "nodeid": "tests/test_runner.py::TestScrollAllContacts::test_three_consecutive_stalls_stops",
      "outcome": "passed",
      "duration": 0.002308,
      "longrepr": null
    },
    {
      "doc": "list_contacts() with no assets_dir returns contacts, screenshot=None.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_returns_contacts",
      "outcome": "passed",
      "duration": 0.001998,
      "longrepr": null
    },
    {
      "doc": "list_contacts() saves screenshot.png + contacts_list.json to assets_dir.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_with_assets_dir",
      "outcome": "passed",
      "duration": 0.002879,
      "longrepr": null
    },
    {
      "doc": "list_contacts() calls session.close() even if _scroll_all_contacts fails.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_closes_on_error",
      "outcome": "passed",
      "duration": 0.001572,
      "longrepr": null
    },
    {
      "doc": "list_contacts() raises RuntimeError when session is not authenticated.",
      "nodeid": "tests/test_runner.py::TestListContacts::test_list_contacts_raises_if_not_authenticated",
      "outcome": "passed",
      "duration": 0.00141,
      "longrepr": null
    },
    {
      "doc": "Si no hay burbujas de audio, devuelve lista vacía.",
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_returns_empty_for_no_audio_bubbles",
      "outcome": "passed",
      "duration": 0.001266,
      "longrepr": null
    },
    {
      "doc": "Procesa solo audio_bubbles, ignora text y file.",
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_filters_out_non_audio_bubbles",
      "outcome": "passed",
      "duration": 0.0016,
      "longrepr": null
    },
    {
      "doc": "Bubble with dom_id already in downloaded_ids is skipped.",
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_skips_already_downloaded_dom_id",
      "outcome": "passed",
      "duration": 0.001252,
      "longrepr": null
    },
    {
      "doc": "Given existing JSON with some bubbles, newest=True stops at first duplicate.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_stops_at_first_duplicate",
      "outcome": "passed",
      "duration": 0.003572,
      "longrepr": null
    },
    {
      "doc": "If no history_bubbles.json exists, newest=True falls back to normal full capture.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_falls_back_when_no_json",
      "outcome": "passed",
      "duration": 0.003551,
      "longrepr": null
    },
    {
      "doc": "After merge, id=1 should be newest; ids should be sequential 1..N.",
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_merges_and_renumbers",
      "outcome": "passed",
      "duration": 0.00364,
      "longrepr": null
    },
    {
      "doc": "Regression test for the bug where fast-forward reached scrollTop<20 WITHOUT finding the anchor (because WA recycled the DOM id), and incorrectly returned [] with completed=True — skipping messages that were actually visible at the top. Fix: when scrollTop<20 is hit before anchor is found, break (don't return []) and fall through to dedup scan from that position.",
      "nodeid": "tests/test_runner.py::TestGrowFastForwardAnchorRecycled::test_captures_old_messages_when_anchor_dom_id_recycled",
      "outcome": "passed",
      "duration": 0.003379,
      "longrepr": null
    },
    {
      "doc": "No updates.json → status first_run regardless of sidebar content.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_first_run_no_previous_state",
      "outcome": "passed",
      "duration": 0.002796,
      "longrepr": null
    },
    {
      "doc": "reset=True → first_run even when updates.json exists.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_reset_forces_first_run",
      "outcome": "passed",
      "duration": 0.003634,
      "longrepr": null
    },
    {
      "doc": "Same last_message on every row → no_updates.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_no_updates_when_sidebar_unchanged",
      "outcome": "passed",
      "duration": 0.003282,
      "longrepr": null
    },
    {
      "doc": "One inbound last_message change → updates with that contact.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_detects_single_new_inbound",
      "outcome": "passed",
      "duration": 0.004275,
      "longrepr": null
    },
    {
      "doc": "Multiple chats with new inbound messages → all reported.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_detects_multiple_new_inbound",
      "outcome": "passed",
      "duration": 0.002727,
      "longrepr": null
    },
    {
      "doc": "A changed last_message with direction=outbound is NOT an update.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_outbound_change_not_reported",
      "outcome": "passed",
      "duration": 0.00336,
      "longrepr": null
    },
    {
      "doc": "Mixed sidebar: only inbound changes reported, outbound silently ignored.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_only_inbound_reported_among_mixed",
      "outcome": "passed",
      "duration": 0.002719,
      "longrepr": null
    },
    {
      "doc": "A contact not in previous state with inbound direction → reported.",
      "nodeid": "tests/test_runner.py::TestCheckUpdates::test_new_contact_inbound_reported",
      "outcome": "passed",
      "duration": 0.002653,
      "longrepr": null
    },
    {
      "doc": "search_contacts() owns the actual search-box interaction — clicking, clearing, typing — that navigate_to_contact used to do inline before ADR-010 added disambiguation.",
      "nodeid": "tests/test_session.py::TestSearchContacts::test_clicks_search_box_by_coordinate",
      "outcome": "passed",
      "duration": 0.002972,
      "longrepr": null
    },
    {
      "doc": "search_contacts() owns the actual search-box interaction — clicking, clearing, typing — that navigate_to_contact used to do inline before ADR-010 added disambiguation.",
      "nodeid": "tests/test_session.py::TestSearchContacts::test_clears_with_keyboard_not_dom",
      "outcome": "passed",
      "duration": 0.002415,
      "longrepr": null
    },
    {
      "doc": "search_contacts() owns the actual search-box interaction — clicking, clearing, typing — that navigate_to_contact used to do inline before ADR-010 added disambiguation.",
      "nodeid": "tests/test_session.py::TestSearchContacts::test_types_contact_name",
      "outcome": "passed",
      "duration": 0.002185,
      "longrepr": null
    },
    {
      "doc": "search_contacts() owns the actual search-box interaction — clicking, clearing, typing — that navigate_to_contact used to do inline before ADR-010 added disambiguation.",
      "nodeid": "tests/test_session.py::TestSearchContacts::test_never_uses_locator",
      "outcome": "passed",
      "duration": 0.002183,
      "longrepr": null
    },
    {
      "doc": "search_contacts() owns the actual search-box interaction — clicking, clearing, typing — that navigate_to_contact used to do inline before ADR-010 added disambiguation.",
      "nodeid": "tests/test_session.py::TestSearchContacts::test_returns_empty_list_when_no_results_appear",
      "outcome": "passed",
      "duration": 0.002211,
      "longrepr": null
    },
    {
      "doc": "search_contacts() owns the actual search-box interaction — clicking, clearing, typing — that navigate_to_contact used to do inline before ADR-010 added disambiguation.",
      "nodeid": "tests/test_session.py::TestSearchContacts::test_returns_candidates_from_page_evaluate",
      "outcome": "passed",
      "duration": 0.002243,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_single_match_auto_resolves_without_prompting",
      "outcome": "passed",
      "duration": 0.000876,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_dedupes_identical_name_and_subtitle_pairs",
      "outcome": "passed",
      "duration": 0.000678,
      "longrepr": null
    },
    {
      "doc": "Justo después de vincular por QR, la lista de chats puede seguir sincronizando desde el teléfono — la primera búsqueda puede no encontrar resultados todavía.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_refreshes_contact_list_when_nothing_found",
      "outcome": "passed",
      "duration": 0.000937,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_raises_if_nothing_found_even_after_refresh",
      "outcome": "passed",
      "duration": 0.002867,
      "longrepr": null
    },
    {
      "doc": "El bug real (2026-08-26): 'Rodolfo Prado' coincidía con un chat existente Y con 4 contactos distintos. Sin una terminal para preguntar, nunca debe elegir uno arbitrariamente.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_multiple_matches_without_tty_raises_instead_of_guessing",
      "outcome": "passed",
      "duration": 0.001118,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_multiple_matches_with_tty_prompts_and_uses_the_choice",
      "outcome": "passed",
      "duration": 0.00096,
      "longrepr": null
    },
    {
      "doc": "Real bug reported by Pulpo, 2026-08-26: searching 'Rodolfo Prado' also returned rows for groups they're merely a member of ('Blanca y sus pollitos', 'Grupo por mamá') — WA's own name-independent 'shared groups' search feature. Those must never be presented as if they were named 'Rodolfo Prado'.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_filters_out_unrelated_shared_groups",
      "outcome": "passed",
      "duration": 0.001093,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_raises_when_no_candidate_name_actually_matches",
      "outcome": "passed",
      "duration": 0.001718,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_accent_and_case_insensitive_match",
      "outcome": "passed",
      "duration": 0.000921,
      "longrepr": null
    },
    {
      "doc": "The user asked for matches to be ordered by last activity when several exist. WA already lists real chats by recency internally, so ranking 'has any activity at all' above 'never messaged' and keeping discovery order within each group achieves that without having to parse WA's date/time text ourselves.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_real_chats_ranked_above_bare_contacts",
      "outcome": "passed",
      "duration": 0.000767,
      "longrepr": null
    },
    {
      "doc": "--pick lets a script/agent resolve ambiguity non-interactively — no TTY required, no prompt.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_pick_selects_without_tty",
      "outcome": "passed",
      "duration": 0.000688,
      "longrepr": null
    },
    {
      "doc": "ADR-010: navigate_to_contact must never guess which contact was meant when the display name is ambiguous — a human decides, or it refuses outright when there's no TTY to ask.",
      "nodeid": "tests/test_session.py::TestResolveContact::test_pick_out_of_range_raises",
      "outcome": "passed",
      "duration": 0.000693,
      "longrepr": null
    },
    {
      "doc": "El resultado se abre haciendo clic en las coordenadas resueltas (ADR-010), nunca con ArrowDown/Enter a ciegas ni con page.click(selector).",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_opens_resolved_candidate_via_click_not_keyboard",
      "outcome": "passed",
      "duration": 0.002238,
      "longrepr": null
    },
    {
      "doc": "Después de cargar mensajes se ejecuta evaluate() para DOM scroll al fondo.",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_dom_scroll_to_bottom_called_after_load",
      "outcome": "passed",
      "duration": 0.002114,
      "longrepr": null
    },
    {
      "doc": "Si no hay botón de ir al fondo (evaluate devuelve False), el fallback hace evaluate con 999_999 para llevar scrollTop al máximo.",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_dom_scroll_fallback_uses_large_delta",
      "outcome": "passed",
      "duration": 0.015821,
      "longrepr": null
    },
    {
      "doc": "El scroll al fondo ocurre después de resolver y abrir el chat.",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_fires_after_resolution",
      "outcome": "passed",
      "duration": 0.002392,
      "longrepr": null
    },
    {
      "doc": "Si el clic no abrió el chat (p.ej. la fila se movió entre la búsqueda y el clic), se reintenta resolver + abrir una vez más antes de rendirse.",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_retries_resolution_once_if_click_did_not_open_a_chat",
      "outcome": "passed",
      "duration": 0.003245,
      "longrepr": null
    },
    {
      "doc": "Si nunca se pudo confirmar que el chat abrió, debe levantar RuntimeError y NUNCA intentar el scroll-to-bottom sobre un chat que no existe. Antes esto se tragaba en silencio y devolvía mensajes de la pantalla de bienvenida como si fueran del contacto (bug real, 2026-08-26: 'Rodolfo Prado' devolvió el banner de 'Llamadas y videollamadas ya están disponibles').",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_raises_and_never_scrolls_if_chat_never_opened",
      "outcome": "passed",
      "duration": 0.002712,
      "longrepr": null
    },
    {
      "doc": "Si get_chat_scroll_state muestra slack > 50px, el loop vuelve a intentar scroll-to-bottom. Simula la situación post-full-sync-enhanced donde el virtualizer restaura la posición anterior (top) en vez del fondo.",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_retries_if_not_at_bottom",
      "outcome": "passed",
      "duration": 0.001948,
      "longrepr": null
    },
    {
      "doc": "Si ya está en el fondo desde el primer check, no hace retries innecesarios.",
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_no_extra_retries_when_already_at_bottom",
      "outcome": "passed",
      "duration": 0.002627,
      "longrepr": null
    },
    {
      "doc": "Headless + about:blank: set_viewport_size fires first, then goto.",
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_headless_blank_calls_set_viewport_before_goto",
      "outcome": "passed",
      "duration": 0.001784,
      "longrepr": null
    },
    {
      "doc": "Viewport is set to exactly WINDOW_W × WINDOW_H.",
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_headless_blank_viewport_dimensions",
      "outcome": "passed",
      "duration": 0.001876,
      "longrepr": null
    },
    {
      "doc": "Headful mode (QR scan window) must not call set_viewport_size.",
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_headful_never_sets_viewport",
      "outcome": "passed",
      "duration": 0.002519,
      "longrepr": null
    },
    {
      "doc": "Daemon reconnect (WA already at WA_URL): no viewport change, no navigation.",
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_wa_already_loaded_skips_viewport_and_goto",
      "outcome": "passed",
      "duration": 0.001894,
      "longrepr": null
    },
    {
      "doc": "WINDOW_W debe ser 1280 — base calibrada de la fórmula del sidebar.",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_window_w_is_1280",
      "outcome": "passed",
      "duration": 0.000299,
      "longrepr": null
    },
    {
      "doc": "WINDOW_H debe ser 1920 — maximiza mensajes por screenshot (ADR-002).",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_window_h_is_1920",
      "outcome": "passed",
      "duration": 0.00015,
      "longrepr": null
    },
    {
      "doc": "--force-device-scale-factor=1 debe estar en los args de wavi connect. Sin este flag, macOS Retina (DPR=2) produce viewport de ~640×960 CSS en lugar de 1280×1920, dando imágenes 'enanas'.",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_cli_headless_args_include_force_dpr",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "doc": "--window-size=1280,1920 debe estar en los args de wavi connect.",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_cli_headless_args_include_window_size",
      "outcome": "passed",
      "duration": 0.000145,
      "longrepr": null
    },
    {
      "doc": "El fallback de WASession.connect() también debe tener --force-device-scale-factor=1. Este fallback se usa cuando 'wavi status' inicia Chrome sin un daemon previo. Si falta aquí, el daemon iniciado por 'wavi status' produce imágenes enanas.",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_session_fallback_args_include_force_dpr",
      "outcome": "passed",
      "duration": 0.001263,
      "longrepr": null
    },
    {
      "doc": "El fallback de WASession.connect() debe lanzar Chrome con --window-size usando las constantes WINDOW_W y WINDOW_H (verificado por su presencia en el source).",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_session_fallback_args_include_window_size",
      "outcome": "passed",
      "duration": 0.00055,
      "longrepr": null
    },
    {
      "doc": "Con DPR=1 y viewport correcto, screenshot debe ser WINDOW_W × WINDOW_H. Este test verifica que si alguien toma un screenshot mockeado, las dimensiones son las esperadas por el pipeline de visión.",
      "nodeid": "tests/test_session.py::TestViewportRegression::test_screenshot_dimensions_match_window_constants",
      "outcome": "passed",
      "duration": 0.000279,
      "longrepr": null
    },
    {
      "doc": "DPR=1: screenshot_w == WINDOW_W → sidebar_x == SIDEBAR_PX exactly.",
      "nodeid": "tests/test_session.py::TestWindowConstants::test_sidebar_formula_exact_at_dpr1",
      "outcome": "passed",
      "duration": 0.00031,
      "longrepr": null
    },
    {
      "doc": "DPR=2: screenshot_w == 2*WINDOW_W → sidebar_x == 2*SIDEBAR_PX (physical px).",
      "nodeid": "tests/test_session.py::TestWindowConstants::test_sidebar_formula_exact_at_dpr2",
      "outcome": "passed",
      "duration": 0.000231,
      "longrepr": null
    },
    {
      "doc": "navigate_to_new_chat() clicks button, waits for list, no error.",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_navigate_to_new_chat_success",
      "outcome": "passed",
      "duration": 0.003627,
      "longrepr": null
    },
    {
      "doc": "Real bug, 2026-08-26: _resolve_contact's refresh path calls this right after search_contacts() leaves text in the sidebar search box — with search active WA hides the pencil/new-chat button. Must clear that state before looking for the button.",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_navigate_to_new_chat_ensures_clean_sidebar_first",
      "outcome": "passed",
      "duration": 0.002047,
      "longrepr": null
    },
    {
      "doc": "navigate_to_new_chat() raises RuntimeError if button not found.",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_navigate_to_new_chat_not_found",
      "outcome": "passed",
      "duration": 0.002214,
      "longrepr": null
    },
    {
      "doc": "extract_contacts() evaluates JS and returns list of contact dicts.",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_extract_contacts_returns_list",
      "outcome": "passed",
      "duration": 0.001661,
      "longrepr": null
    },
    {
      "doc": "close_new_chat() uses back button when available.",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_close_new_chat_via_back_button",
      "outcome": "passed",
      "duration": 0.002325,
      "longrepr": null
    },
    {
      "doc": "close_new_chat() falls back to Escape if back button not found.",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_close_new_chat_fallback_escape",
      "outcome": "passed",
      "duration": 0.002103,
      "longrepr": null
    },
    {
      "doc": "navigate_to_new_chat() propagates wait_for_selector timeout (no swallowing).",
      "nodeid": "tests/test_session.py::TestNewChatPanel::test_navigate_to_new_chat_selector_timeout_propagates",
      "outcome": "passed",
      "duration": 0.002636,
      "longrepr": null
    },
    {
      "doc": "connect() no debe llamar shutil.rmtree bajo ninguna rama — la sesión existente se archiva (.rename), nunca se borra.",
      "nodeid": "tests/test_session.py::TestNeverDeleteSessionProfile::test_connect_source_never_calls_rmtree",
      "outcome": "passed",
      "duration": 0.001504,
      "longrepr": null
    },
    {
      "doc": "Cuando --new detecta un teléfono que ya tiene perfil, el perfil viejo debe seguir existiendo en disco después (archivado), nunca desaparecer.",
      "nodeid": "tests/test_session.py::TestNeverDeleteSessionProfile::test_connect_archives_existing_profile_on_collision",
      "outcome": "passed",
      "duration": 0.001292,
      "longrepr": null
    },
    {
      "doc": "_cleanup_crash_files() solo debe tocar metadata de recuperación de pestañas de Chrome, nunca IndexedDB (donde vive el auth de WA).",
      "nodeid": "tests/test_session.py::TestNeverDeleteSessionProfile::test_cleanup_crash_files_never_touches_indexeddb",
      "outcome": "passed",
      "duration": 0.000215,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_default_is_none",
      "outcome": "passed",
      "duration": 0.000138,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_absent_from_as_dict_when_none",
      "outcome": "passed",
      "duration": 0.000132,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_present_in_as_dict_when_set",
      "outcome": "passed",
      "duration": 0.000124,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_not_added_to_non_audio_bubble",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "doc": "Empty string is a valid transcript (silence), must be included.",
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_as_dict_does_not_include_empty_string_as_none",
      "outcome": "passed",
      "duration": 0.000139,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeGroqSuccess::test_returns_groq_text_on_success",
      "outcome": "passed",
      "duration": 0.170899,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeGroqSuccess::test_groq_called_with_correct_model_and_language",
      "outcome": "passed",
      "duration": 0.00243,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_returns_none_when_no_key_and_no_pywhispercpp",
      "outcome": "passed",
      "duration": 0.003008,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_falls_back_to_local_when_groq_fails",
      "outcome": "passed",
      "duration": 0.00254,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_returns_none_when_both_methods_fail",
      "outcome": "passed",
      "duration": 0.002873,
      "longrepr": null
    },
    {
      "doc": "Without GROQ_API_KEY, Groq must not be called at all (ValueError raised early).",
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_no_key_skips_groq_directly",
      "outcome": "passed",
      "duration": 0.002425,
      "longrepr": null
    },
    {
      "doc": "Transcription is deferred to a second pass after browser close. _download_audio_for_bubbles must NOT set bubble.transcript.",
      "nodeid": "tests/test_transcription.py::TestRunnerDownloadNoInlineTranscription::test_download_does_not_set_transcript",
      "outcome": "passed",
      "duration": 0.003442,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_adds_transcript_to_audio_bubbles",
      "outcome": "passed",
      "duration": 0.00221,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_skips_already_transcribed_bubbles",
      "outcome": "passed",
      "duration": 0.002298,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_raises_if_json_missing",
      "outcome": "passed",
      "duration": 0.001342,
      "longrepr": null
    },
    {
      "doc": "Bubble without audio_path (never downloaded) stays without transcript.",
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_skips_bubble_without_audio_path",
      "outcome": "passed",
      "duration": 0.001858,
      "longrepr": null
    },
    {
      "doc": "audio_path points directly to the file regardless of screen_id vs global_id.",
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_ogg_found_via_audio_path",
      "outcome": "passed",
      "duration": 0.002144,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_plain_text",
      "outcome": "passed",
      "duration": 0.000208,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_audio_by_duration",
      "outcome": "passed",
      "duration": 0.000157,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_audio_duration_not_confused_with_time",
      "outcome": "passed",
      "duration": 0.000139,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_audio_by_waveform_garbage",
      "outcome": "passed",
      "duration": 0.000134,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_file_by_extension",
      "outcome": "passed",
      "duration": 0.00014,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_file_by_size",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_file_takes_priority_over_audio",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_media_empty_text",
      "outcome": "passed",
      "duration": 0.00013,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_media_blank_blocks",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_multiline_text",
      "outcome": "passed",
      "duration": 0.000138,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_waveform_noise",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_waveform_pipe_heavy",
      "outcome": "passed",
      "duration": 0.000124,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_normal_text",
      "outcome": "passed",
      "duration": 0.000122,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_too_short",
      "outcome": "passed",
      "duration": 0.000123,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_mixed_but_below_threshold",
      "outcome": "passed",
      "duration": 0.000127,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_standalone_block",
      "outcome": "passed",
      "duration": 0.00013,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_embedded_at_end",
      "outcome": "passed",
      "duration": 0.000123,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_am_time",
      "outcome": "passed",
      "duration": 0.00012,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_no_timestamp",
      "outcome": "passed",
      "duration": 0.000123,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_duration_not_matched_as_timestamp",
      "outcome": "passed",
      "duration": 0.00012,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_prefers_standalone_over_embedded",
      "outcome": "passed",
      "duration": 0.000131,
      "longrepr": null
    },
    {
      "doc": "'р.' es OCR de 'p.' — el tiempo que precede a 'р.' es el timestamp.",
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_ocr_artifact_single_block",
      "outcome": "passed",
      "duration": 0.000128,
      "longrepr": null
    },
    {
      "doc": "Timestamp cirílico en bloque separado del duration.",
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_ocr_artifact_separate_block",
      "outcome": "passed",
      "duration": 0.000122,
      "longrepr": null
    },
    {
      "doc": "'0:19 р.' no matchea: el patrón requiere [1-9] como primer dígito.",
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_does_not_match_zero_duration",
      "outcome": "passed",
      "duration": 0.000124,
      "longrepr": null
    },
    {
      "doc": "Texto ruso normal sin 'X:YY р.' no dispara el fallback.",
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_does_not_match_plain_russian_text",
      "outcome": "passed",
      "duration": 0.000193,
      "longrepr": null
    },
    {
      "doc": "Audio de 1:30 min cuyo bloque OCR funde duration+timestamp como '1:30 р.': retorna '1:30' (best-effort). Caso raro en práctica ya que duration y timestamp están separados espacialmente en WA y suelen quedar en bloques distintos.",
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_long_duration_ambiguous_edge_case",
      "outcome": "passed",
      "duration": 0.000159,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsNoise::test_empty",
      "outcome": "passed",
      "duration": 0.000133,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsNoise::test_single_char",
      "outcome": "passed",
      "duration": 0.000175,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsNoise::test_plus_sign",
      "outcome": "passed",
      "duration": 0.000212,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsNoise::test_real_text",
      "outcome": "passed",
      "duration": 0.000601,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsNoise::test_audio_duration_kept",
      "outcome": "passed",
      "duration": 0.000303,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestIsNoise::test_cyrillic_filtered",
      "outcome": "passed",
      "duration": 0.000138,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_creates_file",
      "outcome": "passed",
      "duration": 0.027953,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_output_is_valid_image",
      "outcome": "passed",
      "duration": 0.002394,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_empty_bubbles",
      "outcome": "passed",
      "duration": 0.001708,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_box_drawn_changes_pixels",
      "outcome": "passed",
      "duration": 0.00808,
      "longrepr": null
    },
    {
      "doc": "Cross appears on audio/file bubbles; absent on text/media.",
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_drawn_only_on_audio_and_file",
      "outcome": "passed",
      "duration": 0.009177,
      "longrepr": null
    },
    {
      "doc": "'me' cross must be at x+93 (play btn position, calibrated from DOM 2026-05-30). 'other' cross must be at x+38 (play btn near left edge, calibrated from DOM). Old uncalibrated values (x+188, x+78) were Δx=95 and Δx=40 off respectively.",
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_me_vs_other_x_offset",
      "outcome": "passed",
      "duration": 0.006345,
      "longrepr": null
    },
    {
      "doc": "For tall bubbles (quoted reply on top + audio at bottom), the cross must land in the audio player row at the bottom — not at the vertical center of the whole bubble. h=136 is a standard audio-only bubble; h=261 simulates a quoted reply above it. Both must yield a cross 37px from the bottom edge (calibrated from DOM 2026-05-30).",
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_tall_bubble_bottom_anchored",
      "outcome": "passed",
      "duration": 0.008743,
      "longrepr": null
    },
    {
      "doc": "When play_positions are given, the cross is drawn at those coords, not estimated.",
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_uses_exact_play_position_when_provided",
      "outcome": "passed",
      "duration": 0.002646,
      "longrepr": null
    },
    {
      "doc": "Simulates a message with embedded image: - Green bubble body (y=10, h=60) - Image zone (y=70, h=100, non-uniform colors) - Green footer with timestamp (y=170, h=28) Should merge footer into bubble, resulting in single bubble with h=188.",
      "nodeid": "tests/test_vision.py::TestEmbeddedImageFooters::test_footer_below_image_is_merged",
      "outcome": "passed",
      "duration": 0.009444,
      "longrepr": null
    },
    {
      "doc": "Similar to above but with white bubble (received message).",
      "nodeid": "tests/test_vision.py::TestEmbeddedImageFooters::test_white_footer_below_image_is_merged",
      "outcome": "passed",
      "duration": 0.00562,
      "longrepr": null
    },
    {
      "doc": "Two bubbles with separate images should NOT be merged.",
      "nodeid": "tests/test_vision.py::TestEmbeddedImageFooters::test_two_bubbles_separate_images",
      "outcome": "passed",
      "duration": 0.009144,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractReaction::test_no_reaction_returns_text_unchanged",
      "outcome": "passed",
      "duration": 0.000158,
      "longrepr": null
    },
    {
      "doc": "Real capture: an audio bubble's own OCR text ('1:01' duration + stray digits) had a reaction badge mixed into it.",
      "nodeid": "tests/test_vision.py::TestExtractReaction::test_extracts_reaction_with_count_from_audio_duration_text",
      "outcome": "passed",
      "duration": 0.000179,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractReaction::test_extracts_plural_reacciones",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractReaction::test_extracts_reaction_without_leading_count",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractReaction::test_collapses_extra_whitespace_after_removal",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestExtractReaction::test_case_insensitive_and_accent_insensitive",
      "outcome": "passed",
      "duration": 0.000128,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestBubbleReactionField::test_reaction_omitted_when_none",
      "outcome": "passed",
      "duration": 0.000125,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestBubbleReactionField::test_reaction_included_when_present",
      "outcome": "passed",
      "duration": 0.000122,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestBubbleReactionField::test_has_reaction_omitted_when_false",
      "outcome": "passed",
      "duration": 0.000123,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestBubbleReactionField::test_has_reaction_and_image_included_when_present",
      "outcome": "passed",
      "duration": 0.000268,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestFindReactionBadge::test_no_badge_on_plain_wallpaper",
      "outcome": "passed",
      "duration": 0.001697,
      "longrepr": null
    },
    {
      "doc": "Mirrors the real case: a red heart badge just below-right of an outgoing ('me') bubble's bottom edge.",
      "nodeid": "tests/test_vision.py::TestFindReactionBadge::test_detects_saturated_blob_near_outgoing_bubble_corner",
      "outcome": "passed",
      "duration": 0.000951,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestFindReactionBadge::test_detects_badge_near_incoming_bubble_left_edge",
      "outcome": "passed",
      "duration": 0.000601,
      "longrepr": null
    },
    {
      "doc": "A big colorful region (e.g. a media thumbnail poking into the search strip) must not be mistaken for a small reaction badge.",
      "nodeid": "tests/test_vision.py::TestFindReactionBadge::test_ignores_large_saturated_area_as_false_positive",
      "outcome": "passed",
      "duration": 0.00053,
      "longrepr": null
    },
    {
      "doc": "Real bug: WA's own UI chrome (blue double-check 'read' mark, audio playback-position dot) is saturated and sits right at a bubble's edge — it must not be mistaken for a reaction badge.",
      "nodeid": "tests/test_vision.py::TestFindReactionBadge::test_ignores_wa_accent_blue_as_false_positive",
      "outcome": "passed",
      "duration": 0.000468,
      "longrepr": null
    },
    {
      "doc": null,
      "nodeid": "tests/test_vision.py::TestFindReactionBadge::test_ignores_badge_too_far_from_bubble_edge",
      "outcome": "passed",
      "duration": 0.001297,
      "longrepr": null
    }
  ]
};
