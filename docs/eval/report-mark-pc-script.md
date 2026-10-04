# Evaluation report: mark-pc, input from script

Model `medgemma:4b`. Speech-to-text: Whisper small. Synthetic consultations read by the
Windows voices. Scored with `clinassist.evaluation`; every flagged item below shows the
clause that triggered it, so a person can confirm it.

## Summary

| Measure | Result |
|---|---|
| scenarios | 8 |
| notes produced | 8 |
| failed after two attempts | [] |
| needed a retry | ['s08_antenatal'] |
| fact recall | 0.923 |
| critical fact recall | 0.971 |
| facts in wrong section | 6 |
| contradicted negatives | 0 |
| traps triggered | 0 |
| notes with a trap | 0 |
| number flags | 0 |
| merged word flags | 0 |
| median draft seconds | 51.5 |
| median transcribe seconds | 28.1 |

## Per consultation

| Consultation | Recall | Critical recall | Contradictions | Traps | Attempts | Draft s |
|---|---|---|---|---|---|---|
| s01_fever | 18/18 | 7/7 | 0 | 0 | 1 | 46.9 |
| s02_hypertension_diabetes | 26/32 | 11/12 | 0 | 0 | 1 | 182.0 |
| s03_child_diarrhoea | 22/22 | 10/10 | 0 | 0 | 1 | 72.8 |
| s04_urinary_infection | 16/16 | 7/7 | 0 | 0 | 1 | 49.6 |
| s05_asthma | 20/24 | 8/9 | 0 | 0 | 1 | 51.5 |
| s06_possible_tb | 18/19 | 10/10 | 0 | 0 | 1 | 46.1 |
| s07_leg_infection | 17/19 | 7/7 | 0 | 0 | 1 | 51.5 |
| s08_antenatal | 18/18 | 8/8 | 0 | 0 | 2 | 82.9 |

### s01_fever: Fever and headache, malaria to be excluded


### s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

Critical facts missed: no_allergies
Other facts missed: family_history, ex_smoker, hba1c, kidney_tests, lipids

### s03_child_diarrhoea: Child with watery diarrhoea and some dehydration


### s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

Advisory flags: pronoun_not_in_transcript:she

### s05_asthma: Moderate asthma attack with an aspirin allergy

Critical facts missed: full_sentences
Other facts missed: dust_trigger, night_cough, no_preventer

### s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed

Other facts missed: hiv_status_unknown

### s07_leg_infection: Cellulitis of the leg with a penicillin allergy

Other facts missed: redness_3_days, allergy_reaction

### s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

