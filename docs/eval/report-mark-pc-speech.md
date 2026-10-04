# Evaluation report: mark-pc, input from speech

Model `medgemma:4b`. Speech-to-text: Whisper small. Synthetic consultations read by the
Windows voices. Scored with `clinassist.evaluation`; every flagged item below shows the
clause that triggered it, so a person can confirm it.

## Summary

| Measure | Result |
|---|---|
| scenarios | 8 |
| notes produced | 8 |
| failed after two attempts | [] |
| needed a retry | ['s03_child_diarrhoea'] |
| fact recall | 0.899 |
| critical fact recall | 0.9 |
| facts in wrong section | 16 |
| contradicted negatives | 0 |
| traps triggered | 0 |
| notes with a trap | 0 |
| number flags | 0 |
| merged word flags | 0 |
| median draft seconds | 53.3 |
| median transcribe seconds | 22.6 |

## Per consultation

| Consultation | Recall | Critical recall | Contradictions | Traps | Attempts | Draft s |
|---|---|---|---|---|---|---|
| s01_fever | 17/18 | 7/7 | 0 | 0 | 1 | 45.4 |
| s02_hypertension_diabetes | 28/32 | 11/12 | 0 | 0 | 1 | 124.5 |
| s03_child_diarrhoea | 21/22 | 9/10 | 0 | 0 | 2 | 90.2 |
| s04_urinary_infection | 13/16 | 4/7 | 0 | 0 | 1 | 39.3 |
| s05_asthma | 21/24 | 8/9 | 0 | 0 | 1 | 53.3 |
| s06_possible_tb | 18/19 | 10/10 | 0 | 0 | 1 | 39.4 |
| s07_leg_infection | 16/19 | 6/7 | 0 | 0 | 1 | 53.4 |
| s08_antenatal | 17/18 | 8/8 | 0 | 0 | 1 | 53.2 |

### s01_fever: Fever and headache, malaria to be excluded

Other facts missed: no_regular_medicines

### s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

Critical facts missed: no_allergies
Other facts missed: headache_back_of_head, weight_loss, paracetamol_1g

### s03_child_diarrhoea: Child with watery diarrhoea and some dehydration

Critical facts missed: age_18_months

### s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

Critical facts missed: sulfa_allergy, pregnancy_test_negative, nitrofurantoin_100mg

### s05_asthma: Moderate asthma attack with an aspirin allergy

Critical facts missed: full_sentences
Other facts missed: dust_trigger, night_cough

### s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed

Other facts missed: hiv_status_unknown

### s07_leg_infection: Cellulitis of the leg with a penicillin allergy

Critical facts missed: clindamycin_300mg
Other facts missed: redness_3_days, allergy_reaction

### s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

Other facts missed: second_pregnancy
Advisory flags: pronoun_not_in_transcript:she
