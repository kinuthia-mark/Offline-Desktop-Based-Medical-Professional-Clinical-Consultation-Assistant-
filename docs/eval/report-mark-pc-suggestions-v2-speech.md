# Evaluation report: mark-pc-suggestions-v2, input from speech

Model `medgemma:4b`. Speech-to-text: Whisper small. Synthetic consultations read by the
Windows voices. Scored with `clinassist.evaluation`; every flagged item below shows the
clause that triggered it, so a person can confirm it.

## Summary

| Measure | Result |
|---|---|
| scenarios | 8 |
| notes produced | 8 |
| failed after two attempts | [] |
| needed a retry | ['s04_urinary_infection', 's06_possible_tb', 's07_leg_infection'] |
| fact recall | 0.917 |
| critical fact recall | 0.9 |
| facts in wrong section | 13 |
| contradicted negatives | 3 |
| traps triggered | 1 |
| notes with a trap | 1 |
| number flags | 1 |
| merged word flags | 0 |
| median draft seconds | 118.3 |
| median transcribe seconds | 23.3 |

## Per consultation

| Consultation | Recall | Critical recall | Contradictions | Traps | Attempts | Draft s |
|---|---|---|---|---|---|---|
| s01_fever | 17/18 | 7/7 | 0 | 0 | 1 | 69.4 |
| s02_hypertension_diabetes | 29/32 | 11/12 | 0 | 1 | 1 | 181.4 |
| s03_child_diarrhoea | 21/22 | 9/10 | 0 | 0 | 1 | 85.4 |
| s04_urinary_infection | 14/16 | 5/7 | 0 | 0 | 2 | 118.3 |
| s05_asthma | 19/24 | 7/9 | 0 | 0 | 1 | 82.8 |
| s06_possible_tb | 18/19 | 10/10 | 0 | 0 | 2 | 120.1 |
| s07_leg_infection | 18/19 | 6/7 | 0 | 0 | 2 | 142.1 |
| s08_antenatal | 18/18 | 8/8 | 3 | 0 | 1 | 64.6 |

### s01_fever: Fever and headache, malaria to be excluded

Other facts missed: no_regular_medicines

### s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

Critical facts missed: no_allergies
Other facts missed: missed_amlodipine, diary
- trap `wrong_bp`: "the patient reports headaches, high blood pressure (150/94), elevated random blood glucose (11"
Advisory flags: number_not_in_transcript:150/94

### s03_child_diarrhoea: Child with watery diarrhoea and some dehydration

Critical facts missed: age_18_months

### s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

Critical facts missed: sulfa_allergy, nitrofurantoin_100mg
Advisory flags: pronoun_not_in_transcript:she

### s05_asthma: Moderate asthma attack with an aspirin allergy

Critical facts missed: full_sentences, beclometasone_200
Other facts missed: dust_trigger, night_cough, no_preventer

### s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed

Other facts missed: hiv_status_unknown

### s07_leg_infection: Cellulitis of the leg with a penicillin allergy

Critical facts missed: clindamycin_300mg

### s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

- contradiction `no_bleeding`: "1, mild, eat beans and green vegetables, second tetanus injection and first dose of sp to prevent malaria, sleep under a treated mosquito net, return precautions are bleeding, severe headache, swelling of the face, or if the baby moves less, return in 28 weeks"
- contradiction `no_headache`: "1, mild, eat beans and green vegetables, second tetanus injection and first dose of sp to prevent malaria, sleep under a treated mosquito net, return precautions are bleeding, severe headache, swelling of the face, or if the baby moves less, return in 28 weeks"
- contradiction `no_swelling`: "1, mild, eat beans and green vegetables, second tetanus injection and first dose of sp to prevent malaria, sleep under a treated mosquito net, return precautions are bleeding, severe headache, swelling of the face, or if the baby moves less, return in 28 weeks"
