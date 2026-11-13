# Typed consultation summaries (synthetic)

All 16 files here are **synthetic**: invented for testing and demonstration. None is a
real patient.

Each file holds only what a clinician would type into "Type or paste the consultation": a short
summary of the history, the examination and any bedside tests, written in the clinician's own
words rather than as a conversation. There is no diagnosis in the summary, so the AI's suggestions
can be shown; the clinician types the assessment at the last step.

The Reports tab counts conditions from the clinician's assessment (and accepted suggestions), not
from this text. Typing the assessment below for each one gives the charts something to show.
Malaria, upper respiratory tract infection, urinary tract infection and hypertension each have
at least 3 cases; the last three files have 1 case each, so the Reports tab folds them into
"Other conditions" (fewer than 3 cases are never shown on their own).

| File | Assessment to type |
|---|---|
| `01_fever_chills.txt` | Uncomplicated malaria |
| `02_child_fever.txt` | Uncomplicated malaria |
| `03_fever_returned_traveller.txt` | Uncomplicated malaria |
| `04_fever_vomiting.txt` | Malaria with vomiting |
| `05_sore_throat.txt` | Upper respiratory tract infection |
| `06_child_cough_cold.txt` | Upper respiratory tract infection |
| `07_blocked_nose_headache.txt` | Upper respiratory tract infection (sinusitis) |
| `08_burning_urine.txt` | Urinary tract infection |
| `09_urine_frequency_older.txt` | Urinary tract infection |
| `10_fever_loin_pain.txt` | Urinary tract infection (possible pyelonephritis) |
| `11_bp_review.txt` | Hypertension, not controlled |
| `12_headache_high_bp.txt` | Hypertension, newly found |
| `13_bp_dizziness.txt` | Hypertension on treatment, controlled |
| `14_diarrhoea_child.txt` | Acute diarrhoea with some dehydration |
| `15_cough_fever_adult.txt` | Pneumonia |
| `16_wheeze.txt` | Asthma, acute mild attack |
