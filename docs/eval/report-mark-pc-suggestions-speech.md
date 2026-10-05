# Evaluation report: mark-pc-suggestions, input from speech

Model `medgemma:4b`. Speech-to-text: Whisper small. Synthetic consultations read by the
Windows voices. Scored with `clinassist.evaluation`; every flagged item below shows the
clause that triggered it, so a person can confirm it.

## Summary

| Measure | Result |
|---|---|
| scenarios | 8 |
| notes produced | 8 |
| failed after two attempts | [] |
| needed a retry | [] |
| fact recall | 0.911 |
| critical fact recall | 0.914 |
| facts in wrong section | 14 |
| contradicted negatives | 3 |
| traps triggered | 0 |
| notes with a trap | 0 |
| number flags | 0 |
| merged word flags | 0 |
| median draft seconds | 76.1 |
| median transcribe seconds | 23.2 |

## Per consultation

| Consultation | Recall | Critical recall | Contradictions | Traps | Attempts | Draft s |
|---|---|---|---|---|---|---|
| s01_fever | 18/18 | 7/7 | 0 | 0 | 1 | 76.1 |
| s02_hypertension_diabetes | 27/32 | 11/12 | 3 | 0 | 1 | 187.5 |
| s03_child_diarrhoea | 21/22 | 9/10 | 0 | 0 | 1 | 64.1 |
| s04_urinary_infection | 13/16 | 5/7 | 0 | 0 | 1 | 57.4 |
| s05_asthma | 21/24 | 8/9 | 0 | 0 | 1 | 78.2 |
| s06_possible_tb | 19/19 | 10/10 | 0 | 0 | 1 | 57.8 |
| s07_leg_infection | 17/19 | 6/7 | 0 | 0 | 1 | 84.0 |
| s08_antenatal | 17/18 | 8/8 | 0 | 0 | 1 | 65.1 |

### s01_fever: Fever and headache, malaria to be excluded


### s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

Critical facts missed: no_allergies
Other facts missed: missed_amlodipine, home_bp_150_90, ex_smoker, diary
- contradiction `no_vomiting`: "patient reports headache becomes severe, vomiting, vision loss, chest pain, weakness on one side or confusion are concerning"
- contradiction `no_weakness`: "patient reports headache becomes severe, vomiting, vision loss, chest pain, weakness on one side or confusion are concerning"
- contradiction `no_chest_pain`: "patient reports headache becomes severe, vomiting, vision loss, chest pain, weakness on one side or confusion are concerning"

### s03_child_diarrhoea: Child with watery diarrhoea and some dehydration

Critical facts missed: age_18_months

### s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

Critical facts missed: sulfa_allergy, nitrofurantoin_100mg
Other facts missed: bladder_infection

### s05_asthma: Moderate asthma attack with an aspirin allergy

Critical facts missed: full_sentences
Other facts missed: dust_trigger, night_cough

### s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed


### s07_leg_infection: Cellulitis of the leg with a penicillin allergy

Critical facts missed: clindamycin_300mg
Other facts missed: redness_3_days

### s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

Other facts missed: previous_normal_delivery
