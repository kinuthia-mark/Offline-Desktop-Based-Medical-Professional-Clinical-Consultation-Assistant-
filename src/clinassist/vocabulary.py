"""Common medicine names for primary care in Kenya (AMD-38, ADR-013).

Used in two places:
  - as a vocabulary hint for speech-to-text, so a spoken "clindamycin" is less likely to come out
    as "Glendamycin" (Whisper's `initial_prompt`);
  - by the medicine-name check, which flags a word in the transcript that looks like a medicine
    but is not a known name.

The list holds generic (INN) names commonly used in Kenyan primary care, drawn from the
categories of the Kenya Essential Medicines List: pain and fever, antimalarials, antibiotics,
TB and HIV, cardiovascular, diabetes, respiratory, gastrointestinal, maternal health and
supplements. It is a working list for this prototype, not a complete or authoritative formulary,
and a pharmacist should review it before any clinical use.
"""

from __future__ import annotations

MEDICINES: tuple[str, ...] = (
    # pain and fever
    "paracetamol", "ibuprofen", "diclofenac", "aspirin", "tramadol", "morphine",
    # antimalarials
    "artemether", "lumefantrine", "artesunate", "quinine", "sulfadoxine", "pyrimethamine",
    # antibiotics
    "amoxicillin", "co-amoxiclav", "flucloxacillin", "benzylpenicillin", "ampicillin",
    "ceftriaxone", "cefalexin", "azithromycin", "erythromycin", "doxycycline",
    "ciprofloxacin", "metronidazole", "nitrofurantoin", "co-trimoxazole", "clindamycin",
    "gentamicin",
    # tuberculosis and HIV
    "rifampicin", "isoniazid", "pyrazinamide", "ethambutol", "dolutegravir", "tenofovir",
    "lamivudine", "efavirenz",
    # cardiovascular
    "amlodipine", "nifedipine", "hydrochlorothiazide", "furosemide", "enalapril", "losartan",
    "atenolol", "atorvastatin", "simvastatin",
    # diabetes
    "metformin", "glibenclamide", "gliclazide", "insulin",
    # respiratory and allergy
    "salbutamol", "beclometasone", "budesonide", "prednisolone", "hydrocortisone",
    "chlorphenamine", "cetirizine", "loratadine",
    # gastrointestinal
    "omeprazole", "ranitidine", "oral rehydration salts", "zinc", "albendazole",
    "mebendazole", "loperamide",
    # maternal health and supplements
    "ferrous sulphate", "folic acid", "oxytocin", "misoprostol", "magnesium sulphate",
    "tetanus toxoid", "vitamin A",
    # skin and fungal
    "clotrimazole", "fluconazole", "nystatin", "miconazole",
)  # fmt: skip


def speech_prompt(limit_words: int = 120) -> str:
    """A short text Whisper reads before listening, so these words are expected. Whisper keeps
    only the last 224 tokens of a prompt, so the list is kept short."""
    names = ", ".join(MEDICINES)
    words = names.split()
    if len(words) > limit_words:
        names = " ".join(words[:limit_words]).rstrip(",")
    return f"Clinical consultation in a Kenyan clinic. Medicines that may be mentioned: {names}."
