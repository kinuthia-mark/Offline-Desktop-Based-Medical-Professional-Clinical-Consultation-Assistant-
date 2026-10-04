"""Plain-language messages for every error code the app can show.

Every part of the program reports problems as short codes (never with patient text). This table
turns each code into a sentence a clinician can act on. A code that is missing here falls back to
a general message that still names the code, so support can look it up.
"""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # workflow (controller)
    "empty_transcript": "The transcript is empty. Type or correct it before approving.",
    "attempts_exhausted": "The note could not be drafted after two tries. Write it by hand.",
    "history_not_confirmed": "Tick allergies, medications and pertinent negatives first.",
    "assessment_required": "Write your own assessment before finalizing.",
    "invalid_suggestion_index": "That suggestion is no longer in the list.",
    # input guard
    "transcript_too_long": "The transcript is too long to send to the model. Shorten it.",
    "prompt_injection": (
        "The transcript contains text aimed at the AI (for example 'ignore all previous "
        "instructions'). Remove it, or write the note by hand."
    ),
    # note generation
    "timeout": "The model took too long. Try again, or write the note by hand.",
    "repetition_detected": "The model started repeating itself and was stopped. Try again.",
    "output_truncated": "The model's note was cut off. Try again, or write the note by hand.",
    "invalid_output": "The model's reply was not a usable note. Try again.",
    "ollama_unreachable": "The local model service (Ollama) is not running. Start it and retry.",
    "model_not_available": "The language model is not installed in Ollama.",
    "ollama_error": "The local model service reported an error. Try again.",
    "bad_stream": "The model's reply was garbled. Try again.",
    "prompt_leak": "The model's reply was rejected as unsafe. Try again or write by hand.",
    "link_in_output": "The model's reply contained a web link and was rejected. Try again.",
    # microphone
    "no_microphone": "No microphone was found. Plug one in or check Windows sound settings.",
    "microphone_unavailable": "The microphone could not be opened. Is another program using it?",
    "sample_rate_not_supported": "This microphone cannot record at 16 kHz. Choose another one.",
    "already_recording": "Recording is already running.",
    "not_recording": "Recording has not started.",
    # speech-to-text
    "asr_model_missing": "The speech model is missing. Reinstall the application.",
    "asr_model_failed_to_load": "The speech model could not be loaded. Reinstall the application.",
    "asr_failed": "Speech-to-text failed. Type the transcript, or record again.",
    "unreadable_audio": "The recording could not be read. Record again.",
    "unsupported_audio_format": "The recording is in an unexpected format. Record again.",
    # vault
    "incorrect_passphrase": "That passphrase is not correct.",
    "incorrect_recovery_code": "That recovery code is not correct.",
    "weak_passphrase": "Use at least 12 characters, and not a common password.",
    "vault_exists": "A vault already exists in this folder.",
    "vault_not_found": "No vault was found. Create one first.",
    "vault_corrupt": "The vault file is damaged. Restore it from a backup.",
    "vault_locked": "The vault is locked. Unlock it again.",
    "schema_newer_than_program": "This vault was made by a newer version of the application.",
    # accounts
    "invalid_credentials": "Username or password is not correct.",
    "account_locked": "Too many wrong attempts. The account is locked for 15 minutes.",
    "account_inactive": "This account has been turned off. Ask an administrator.",
    "session_expired": "You were logged out after 10 minutes without activity.",
    "forbidden": "Only an administrator can do that.",
    "weak_password": "Use at least 12 characters, not a common password, and not your username.",
    "invalid_username": "Usernames are 3 to 64 characters with no spaces.",
    "username_taken": "That username is already in use.",
    "setup_already_done": "An administrator account already exists.",
    "cannot_deactivate_self": "You cannot turn off your own account.",
    "user_not_found": "That account no longer exists.",
    "invalid_role": "Choose clinician or admin.",
    # network guard
    "outbound_connection_blocked": "A connection outside this PC was blocked (offline rule).",
    "listening_socket_blocked": "Opening a network port was blocked (offline rule).",
    "name_lookup_blocked": "A lookup of an internet address was blocked (offline rule).",
    # audit log (these mean a programming error, not something the user did)
    "invalid_event_name": "Internal error while writing the audit log. Please report it.",
    "invalid_id": "Internal error while writing the audit log. Please report it.",
    # optional audio retention
    "audio_corrupt": "The saved recording is damaged or belongs to another consultation.",
    "audio_exists": "A recording is already saved for this consultation.",
    "audio_not_found": "No recording was kept for this consultation.",
    "invalid_session_id": "Internal error: unexpected consultation id. Please report it.",
    # settings and set-up
    "non_loopback_host": "The model address must be on this computer (127.0.0.1).",
    "settings_unreadable": "The settings file could not be read. Fix or delete settings.json.",
    "unknown_whisper_model": "The settings name a speech model that is not supported.",
    # storage
    "duplicate_session": "This consultation has already been saved.",
    "rejected_by_schema": "The record was refused as incomplete. Check the checklist and note.",
    "storage_failed": "Saving failed. Your note is still on screen; try again.",
    "session_not_found": "That consultation was not found.",
}

# Startup check codes, shown on the readiness screen.
CHECKS: dict[str, str] = {
    "python_ok": "Python version is supported.",
    "python_too_old": "Python 3.11 or newer is needed.",
    "data_folder_ok": "The data folder can be written.",
    "data_folder_not_writable": "The data folder cannot be written. Check permissions.",
    "whisper_ok": "The speech model is present and unchanged.",
    "whisper_missing_files": "The speech model is missing. Reinstall the application.",
    "whisper_wrong_size": "The speech model file is damaged. Reinstall the application.",
    "whisper_wrong_checksum": "The speech model file has changed. Reinstall the application.",
    "llm_ok": "The language model is ready.",
    "ollama_not_running": "Ollama is not running: notes must be written by hand until it is.",
    "llm_model_missing": "The language model is not installed in Ollama.",
    "free_ram_ok": "Enough free memory.",
    "free_ram_low": "Free memory is low: drafting will be slower. Close other programs.",
    "free_ram_very_low": "Free memory is very low: close other programs before a consultation.",
    "microphone_ok": "A microphone is available.",
    "no_microphone": "No microphone found.",
    "chosen_microphone_missing": "The chosen microphone is not connected.",
    "microphone_check_failed": "The microphone could not be checked.",
    "check_crashed": "This check could not run.",
    "network_verified": "Offline: no connection leaves this PC, and the firewall rules are set.",
    "firewall_rule_missing": (
        "The app blocks network use itself, but the Windows firewall rules are not set. "
        "Ask an administrator to run scripts\airgap_firewall.ps1 -Apply."
    ),
    "guard_not_installed": "The in-app network guard is not running.",
    "outbound_connection_open": "This app has a network connection open. Stop and report it.",
    "app_listening_on_network": "This app is reachable from the network. Stop and report it.",
    "ollama_exposed": (
        "The model service (Ollama) accepts connections from other computers. "
        "Remove the OLLAMA_HOST setting so it listens on 127.0.0.1 only."
    ),
}


def message_for(code: str) -> str:
    """The sentence for a code. "prompt_injection:override_all" uses the "prompt_injection"
    entry; the part after the colon is a detail for the audit log, not for the screen."""
    base = code.split(":", 1)[0]
    return MESSAGES.get(code) or MESSAGES.get(base) or f"Something went wrong ({code})."


def check_message(code: str) -> str:
    return CHECKS.get(code, code)
