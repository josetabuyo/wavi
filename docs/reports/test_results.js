window.WAVI_TEST_RESULTS = {
  "timestamp": "2026-06-04 14:53:29",
  "duration": 0.58,
  "total": 118,
  "passed": 118,
  "failed": 0,
  "skipped": 0,
  "exit_code": 0,
  "tests": [
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr1_direct_match",
      "outcome": "passed",
      "duration": 0.000421,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr2_retina_match",
      "outcome": "passed",
      "duration": 0.000178,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_dpr1_would_fail_on_retina_data",
      "outcome": "passed",
      "duration": 0.000166,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_picks_nearest_of_multiple_buttons",
      "outcome": "passed",
      "duration": 0.000149,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_no_match_beyond_tolerance",
      "outcome": "passed",
      "duration": 0.000151,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_empty_buttons_returns_none",
      "outcome": "passed",
      "duration": 0.000151,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestMatchBubbleToButton::test_tall_bubble_center_used",
      "outcome": "passed",
      "duration": 0.000141,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestInstallBlobMonitor::test_calls_evaluate_with_init_script",
      "outcome": "passed",
      "duration": 0.000981,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestInstallBlobMonitor::test_script_contains_guard",
      "outcome": "passed",
      "duration": 0.0005,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestGetDpr::test_returns_page_device_pixel_ratio",
      "outcome": "passed",
      "duration": 0.00067,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_ids_sequential_and_unique",
      "outcome": "passed",
      "duration": 0.001608,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_chronological_order",
      "outcome": "passed",
      "duration": 0.001486,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_screen_id_preserved",
      "outcome": "passed",
      "duration": 0.00165,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_overlap_counted_once",
      "outcome": "passed",
      "duration": 0.001551,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_empty_iteration_is_noop",
      "outcome": "passed",
      "duration": 0.001457,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistory::test_identical_text_different_timestamp_both_survive",
      "outcome": "passed",
      "duration": 0.001667,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_matches_by_y",
      "outcome": "passed",
      "duration": 0.00019,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_no_match_beyond_tolerance",
      "outcome": "passed",
      "duration": 0.000157,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestAssignDomIds::test_assign_dom_ids_empty_dom_msgs_noop",
      "outcome": "passed",
      "duration": 0.000148,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestAnchorMatchingStrategy::test_anchor_found_by_dom_id_even_if_ocr_differs",
      "outcome": "passed",
      "duration": 0.000139,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestAnchorMatchingStrategy::test_anchor_falls_back_to_ocr_when_no_dom_id",
      "outcome": "passed",
      "duration": 0.000132,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_dom_id_takes_priority_over_ocr",
      "outcome": "passed",
      "duration": 0.000132,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_different_dom_ids_not_deduped",
      "outcome": "passed",
      "duration": 0.000128,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestBubbleKeyWithDomId::test_fallback_to_ocr_when_no_dom_id",
      "outcome": "passed",
      "duration": 0.000127,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_returns_empty_for_no_audio_bubbles",
      "outcome": "passed",
      "duration": 0.000883,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_filters_out_non_audio_bubbles",
      "outcome": "passed",
      "duration": 0.001039,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestDownloadAudioForBubbles::test_skips_already_downloaded_dom_id",
      "outcome": "passed",
      "duration": 0.000927,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_stops_at_first_duplicate",
      "outcome": "passed",
      "duration": 0.00632,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_falls_back_when_no_json",
      "outcome": "passed",
      "duration": 0.002466,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_runner.py::TestCaptureFullHistoryNewest::test_newest_merges_and_renumbers",
      "outcome": "passed",
      "duration": 0.00278,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_clicks_search_box_by_coordinate",
      "outcome": "passed",
      "duration": 0.001854,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_clears_with_keyboard_not_dom",
      "outcome": "passed",
      "duration": 0.001671,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_types_contact_name",
      "outcome": "passed",
      "duration": 0.001855,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_never_uses_locator",
      "outcome": "passed",
      "duration": 0.00174,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_opens_result_with_keyboard_not_locator",
      "outcome": "passed",
      "duration": 0.001723,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_dom_scroll_to_bottom_called_after_load",
      "outcome": "passed",
      "duration": 0.001685,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_dom_scroll_fallback_uses_large_delta",
      "outcome": "passed",
      "duration": 0.001819,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_fires_after_selector_wait",
      "outcome": "passed",
      "duration": 0.00224,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_fires_after_selector_even_on_timeout",
      "outcome": "passed",
      "duration": 0.001741,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_retries_if_not_at_bottom",
      "outcome": "passed",
      "duration": 0.002264,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestNavigateToContact::test_scroll_no_extra_retries_when_already_at_bottom",
      "outcome": "passed",
      "duration": 0.002021,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_headless_blank_calls_set_viewport_before_goto",
      "outcome": "passed",
      "duration": 0.001419,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_headless_blank_viewport_dimensions",
      "outcome": "passed",
      "duration": 0.001372,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_headful_never_sets_viewport",
      "outcome": "passed",
      "duration": 0.001214,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestSetupPageViewport::test_wa_already_loaded_skips_viewport_and_goto",
      "outcome": "passed",
      "duration": 0.001181,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_window_w_is_1280",
      "outcome": "passed",
      "duration": 0.000171,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_window_h_is_1920",
      "outcome": "passed",
      "duration": 0.000151,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_cli_headless_args_include_force_dpr",
      "outcome": "passed",
      "duration": 0.012623,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_cli_headless_args_include_window_size",
      "outcome": "passed",
      "duration": 0.000158,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_session_fallback_args_include_force_dpr",
      "outcome": "passed",
      "duration": 0.000842,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_session_fallback_args_include_window_size",
      "outcome": "passed",
      "duration": 0.000457,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestViewportRegression::test_screenshot_dimensions_match_window_constants",
      "outcome": "passed",
      "duration": 0.000135,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestWindowConstants::test_sidebar_formula_exact_at_dpr1",
      "outcome": "passed",
      "duration": 0.00013,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_session.py::TestWindowConstants::test_sidebar_formula_exact_at_dpr2",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_default_is_none",
      "outcome": "passed",
      "duration": 0.000135,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_absent_from_as_dict_when_none",
      "outcome": "passed",
      "duration": 0.000131,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_present_in_as_dict_when_set",
      "outcome": "passed",
      "duration": 0.00013,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_transcript_not_added_to_non_audio_bubble",
      "outcome": "passed",
      "duration": 0.000127,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestBubbleTranscript::test_as_dict_does_not_include_empty_string_as_none",
      "outcome": "passed",
      "duration": 0.000127,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeGroqSuccess::test_returns_groq_text_on_success",
      "outcome": "passed",
      "duration": 0.126808,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeGroqSuccess::test_groq_called_with_correct_model_and_language",
      "outcome": "passed",
      "duration": 0.001788,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_returns_none_when_no_key_and_no_pywhispercpp",
      "outcome": "passed",
      "duration": 0.00124,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_falls_back_to_local_when_groq_fails",
      "outcome": "passed",
      "duration": 0.001192,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_returns_none_when_both_methods_fail",
      "outcome": "passed",
      "duration": 0.00116,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeFallback::test_no_key_skips_groq_directly",
      "outcome": "passed",
      "duration": 0.00114,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestRunnerDownloadNoInlineTranscription::test_download_does_not_set_transcript",
      "outcome": "passed",
      "duration": 0.002018,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_adds_transcript_to_audio_bubbles",
      "outcome": "passed",
      "duration": 0.001432,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_skips_already_transcribed_bubbles",
      "outcome": "passed",
      "duration": 0.001262,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_raises_if_json_missing",
      "outcome": "passed",
      "duration": 0.000761,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_skips_bubble_without_audio_path",
      "outcome": "passed",
      "duration": 0.001054,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_transcription.py::TestTranscribeHistoryAudios::test_ogg_found_via_audio_path",
      "outcome": "passed",
      "duration": 0.001204,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_plain_text",
      "outcome": "passed",
      "duration": 0.000153,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_audio_by_duration",
      "outcome": "passed",
      "duration": 0.000143,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_audio_duration_not_confused_with_time",
      "outcome": "passed",
      "duration": 0.000138,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_audio_by_waveform_garbage",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_file_by_extension",
      "outcome": "passed",
      "duration": 0.000134,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_file_by_size",
      "outcome": "passed",
      "duration": 0.000131,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_file_takes_priority_over_audio",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_media_empty_text",
      "outcome": "passed",
      "duration": 0.000132,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_media_blank_blocks",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyMsgType::test_multiline_text",
      "outcome": "passed",
      "duration": 0.000182,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_waveform_noise",
      "outcome": "passed",
      "duration": 0.000139,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_waveform_pipe_heavy",
      "outcome": "passed",
      "duration": 0.000134,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_normal_text",
      "outcome": "passed",
      "duration": 0.000136,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_too_short",
      "outcome": "passed",
      "duration": 0.000128,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsWaveformGarbage::test_mixed_but_below_threshold",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_standalone_block",
      "outcome": "passed",
      "duration": 0.000139,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_embedded_at_end",
      "outcome": "passed",
      "duration": 0.00013,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_am_time",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_no_timestamp",
      "outcome": "passed",
      "duration": 0.000134,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_duration_not_matched_as_timestamp",
      "outcome": "passed",
      "duration": 0.000127,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_prefers_standalone_over_embedded",
      "outcome": "passed",
      "duration": 0.000124,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_ocr_artifact_single_block",
      "outcome": "passed",
      "duration": 0.000133,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_ocr_artifact_separate_block",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_does_not_match_zero_duration",
      "outcome": "passed",
      "duration": 0.000127,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_does_not_match_plain_russian_text",
      "outcome": "passed",
      "duration": 0.000131,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestExtractTimestamp::test_cyrillic_long_duration_ambiguous_edge_case",
      "outcome": "passed",
      "duration": 0.000128,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyX::test_right_edge_is_me",
      "outcome": "passed",
      "duration": 0.000125,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyX::test_left_edge_is_other",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyX::test_center_right_is_me",
      "outcome": "passed",
      "duration": 0.000125,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestClassifyX::test_center_left_is_other",
      "outcome": "passed",
      "duration": 0.000123,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsNoise::test_empty",
      "outcome": "passed",
      "duration": 0.000132,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsNoise::test_single_char",
      "outcome": "passed",
      "duration": 0.000126,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsNoise::test_plus_sign",
      "outcome": "passed",
      "duration": 0.000124,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsNoise::test_real_text",
      "outcome": "passed",
      "duration": 0.000309,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsNoise::test_audio_duration_kept",
      "outcome": "passed",
      "duration": 0.000263,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestIsNoise::test_cyrillic_filtered",
      "outcome": "passed",
      "duration": 0.000129,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_creates_file",
      "outcome": "passed",
      "duration": 0.018815,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_output_is_valid_image",
      "outcome": "passed",
      "duration": 0.002224,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_empty_bubbles",
      "outcome": "passed",
      "duration": 0.001324,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_box_drawn_changes_pixels",
      "outcome": "passed",
      "duration": 0.004487,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_drawn_only_on_audio_and_file",
      "outcome": "passed",
      "duration": 0.007664,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_me_vs_other_x_offset",
      "outcome": "passed",
      "duration": 0.005349,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_tall_bubble_bottom_anchored",
      "outcome": "passed",
      "duration": 0.007076,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestSaveDebugImage::test_cross_uses_exact_play_position_when_provided",
      "outcome": "passed",
      "duration": 0.002539,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestEmbeddedImageFooters::test_footer_below_image_is_merged",
      "outcome": "passed",
      "duration": 0.007759,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestEmbeddedImageFooters::test_white_footer_below_image_is_merged",
      "outcome": "passed",
      "duration": 0.005862,
      "longrepr": null
    },
    {
      "nodeid": "tests/test_vision.py::TestEmbeddedImageFooters::test_two_bubbles_separate_images",
      "outcome": "passed",
      "duration": 0.008859,
      "longrepr": null
    }
  ]
};
