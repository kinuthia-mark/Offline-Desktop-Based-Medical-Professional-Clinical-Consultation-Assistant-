# PriMock57: 57 consultations, input from speech

Dataset: PriMock57 (Korfiatis et al., ACL 2022; Babylon Health), CC BY 4.0, https://github.com/babylonhealth/primock57. The dataset is not stored in this repository; only these
scores are. Machine: 12 logical CPUs, 7.9 GB RAM, 0.4 GB free at the start.

## Summary

| Measure | Result |
|---|---|
| consultations run | 57 |
| notes produced | 48/57 (84.2%) |
| needed the second attempt | 20 |
| speech-to-text word error rate (fillers removed; weighted by words) | 0.146 |
| notes stating a diagnosis | 41 of 48 |
| clinician's diagnosis among the AI's suggestions | 21/41 (51.2%) |
| ... as the first suggestion | 21/41 (51.2%) |
| clinician's highlights covered by the note | 118/212 (55.7%) |
| ROUGE-1 / ROUGE-2 / ROUGE-L against the clinician's note (mean F1) | 0.324 / 0.074 / 0.18 |
| median seconds: speech-to-text / drafting | 106.5 / 98.1 |

No note after two attempts: day1_consultation04, day1_consultation07, day1_consultation12, day1_consultation13, day2_consultation05, day3_consultation09, day4_consultation06, day4_consultation08, day5_consultation08.

## Each consultation

| Consultation | WER | Clinician's diagnosis | AI suggestions | Rank | Highlights | R-1 | R-L |
|---|---|---|---|---|---|---|---|
| day1_consultation01 | 0.1675 | gastroenteritis | Gastroenteritis; Dehydration; Gastroenteritis secondary to food poisoning | 1 | 5/5 | 0.3769 | 0.2128 |
| day1_consultation02 | 0.1605 | flare up of eczema |  | - | 3/5 | 0.2904 | 0.1639 |
| day1_consultation03 | 0.1496 | migraine | Migraine | 1 | 4/6 | 0.4161 | 0.2298 |
| day1_consultation04 | 0.2047 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day1_consultation05 | 0.1257 | UTI |  | - | 3/5 | 0.2866 | 0.162 |
| day1_consultation06 | 0.179 | exacerbation of heart failure | Heart failure exacerbation; Anemia; Kidney dysfunction | 1 | 5/6 | 0.3664 | 0.2239 |
| day1_consultation07 | 0.2559 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day1_consultation08 | 0.2054 | dermatitis | Dermatitis | 1 | 3/5 | 0.2791 | 0.1938 |
| day1_consultation09 | 0.17 | UTI; cystitis | Urinary Tract Infection (UTI); IBS; Pregnancy | 1 | 2/5 | 0.2857 | 0.1603 |
| day1_consultation10 | 0.208 | UTI | UTI; IBS | 1 | 4/5 | 0.2771 | 0.1905 |
| day1_consultation11 | 0.166 | gastroenteritis | Gastroenteritis; Dehydration; Dietary adjustments | 1 | 5/7 | 0.2934 | 0.1677 |
| day1_consultation12 | 0.1324 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day1_consultation13 | 0.0984 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day1_consultation14 | 0.179 | viral URTI | Viral Upper Respiratory Infection; Type 2 Diabetes; Hypertension | 1 | 4/5 | 0.3608 | 0.1782 |
| day1_consultation15 | 0.1588 | contact dermatitis | Contact dermatitis; Diabetes | 1 | 2/5 | 0.3228 | 0.1899 |
| day2_consultation01 | 0.1272 | (none written) | Wax blockage; Tinnitus; Dizziness (possible vestibular issue) | - | 2/4 | 0.3568 | 0.2347 |
| day2_consultation02 | 0.1628 | possible bursitis | Bursitis; Osteoarthritis; Septic Arthritis | 1 | 3/7 | 0.2478 | 0.1326 |
| day2_consultation03 | 0.1957 | Bell's Palsy |  | - | 2/5 | 0.3024 | 0.121 |
| day2_consultation04 | 0.1164 | probable LRTI | Chest infection; Pneumonia; Lung cancer | 1 | 1/1 | 0.3179 | 0.1921 |
| day2_consultation05 | 0.104 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day2_consultation06 | 0.1436 | localized inflammatory reaction to insect bite; cellulitis | Anaphylaxis; Eczema | - | 1/6 | 0.335 | 0.15 |
| day2_consultation07 | 0.1477 | acute cardiac event | Possible myocardial infarction | - | 4/9 | 0.1852 | 0.1333 |
| day2_consultation08 | 0.1214 | PUO | Malaria; Influenza; Viral infection | - | 5/14 | 0.3333 | 0.2419 |
| day2_consultation09 | 0.1255 | CVA |  | - | 3/6 | 0.3866 | 0.2605 |
| day2_consultation10 | 0.1077 | tension type headache | Tension headache; Migraine; Anxiety | 1 | 7/7 | 0.3828 | 0.1654 |
| day3_consultation01 | 0.1853 | anaphylactic reaction |  | - | 4/4 | 0.3203 | 0.1637 |
| day3_consultation02 | 0.1366 | (none written) |  | - | 3/3 | 0.4324 | 0.227 |
| day3_consultation03 | 0.1378 | (none written) | Hypothyroidism | - | 3/4 | 0.381 | 0.2105 |
| day3_consultation04 | 0.1651 | (none written) | Asthma Exacerbation; Poor Asthma Control | - | 3/4 | 0.358 | 0.1718 |
| day3_consultation05 | 0.1002 | labrynthitis | Labyrinthitis; Premature Ovarian Failure | 1 | 3/4 | 0.4605 | 0.2405 |
| day3_consultation06 | 0.1289 | urticaria | Local reaction; Anaphylaxis; Eczema | - | 2/4 | 0.3774 | 0.239 |
| day3_consultation07 | 0.1552 | (none written) | Eczema; Hypothyroidism; Asthma | - | 4/4 | 0.425 | 0.2167 |
| day3_consultation08 | 0.1193 | Upper respiratory tract infection | Viral upper respiratory tract infection; Diabetes mellitus; Hypertension | 1 | 1/2 | 0.3602 | 0.2559 |
| day3_consultation09 | 0.102 | | no note (['invalid_output', 'repetition_detected']) | | | | |
| day3_consultation10 | 0.1077 | Gastroenteritis | Diarrhea; Asthma (Lexipro) | - | 2/4 | 0.3416 | 0.1983 |
| day4_consultation01 | 0.1275 | MI; PE; GORD | Angina; Shortness of Breath | - | 1/1 | 0.3158 | 0.1754 |
| day4_consultation02 | 0.0923 | hypothyroid |  | - | 1/1 | 0.2636 | 0.1433 |
| day4_consultation03 | 0.0884 | PE | Possible pulmonary embolism; Possible musculoskeletal pain from C-section scar; Tachycardia secondary to anxiety and/or pain | 1 | 1/1 | 0.2466 | 0.1644 |
| day4_consultation04 | 0.0816 | acute exacerbation of asthma; allergy | Asthma exacerbation; Hay fever | 1 | 1/1 | 0.3291 | 0.1772 |
| day4_consultation05 | 0.1945 | gastroenteritis | Gastroenteritis | 1 | 1/1 | 0.3118 | 0.1521 |
| day4_consultation06 | 0.1256 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day4_consultation07 | 0.1703 | (none written) | Viral upper respiratory infection; Bronchitis; Asthma exacerbation | - | 1/1 | 0.3172 | 0.1586 |
| day4_consultation08 | 0.1501 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day4_consultation09 | 0.1545 | Asthma exacerbation | Asthma exacerbation; Asthma; Viral upper respiratory infection | 1 | 1/1 | 0.2931 | 0.1595 |
| day4_consultation10 | 0.1318 | Simple constipation; PID; STI; UTI | Constipation; Pregnancy; Urinary Tract Infection (UTI) | 1 | 1/1 | 0.176 | 0.136 |
| day5_consultation01 | 0.1564 | Tension headache; first episode migraine | Migraine; Tension Headache; Medication Overuse Headache | 1 | 2/6 | 0.3065 | 0.1256 |
| day5_consultation02 | 0.0944 | Likely UTI |  | - | 1/4 | 0.2684 | 0.1526 |
| day5_consultation03 | 0.1215 | Work related anxiety | Anxiety; Palpitations; Sleep disturbance | 1 | 1/5 | 0.2922 | 0.1511 |
| day5_consultation04 | 0.2038 | Abdominal pain cause | Pregnancy; Pelvic Inflammatory Disease (PID); Ectopic Pregnancy | - | 1/4 | 0.2812 | 0.1661 |
| day5_consultation05 | 0.1342 | UTI |  | - | 3/5 | 0.3481 | 0.1899 |
| day5_consultation06 | 0.1473 | Gastroenteritis Viral; food poisoning |  | - | 1/5 | 0.3239 | 0.1488 |
| day5_consultation07 | 0.1131 | Viral bronchitis | Viral upper respiratory infection; Secondary bacterial infection due to diabetes; Hypertension | - | 0/4 | 0.3004 | 0.1344 |
| day5_consultation08 | 0.1056 | | no note (['invalid_output', 'repetition_detected']) | | | | |
| day5_consultation09 | 0.1617 | 6/52 hx fatigue; hx circular rash on calf | Lyme disease; Other bacterial infection; Asthma exacerbation | - | 2/6 | 0.2454 | 0.1282 |
| day5_consultation10 | 0.1542 | Likely migraine |  | - | 2/7 | 0.3723 | 0.2021 |
| day5_consultation11 | 0.1074 | (none written) | Osteoarthritis; Ligament sprain/injury; Meniscus tear | - | 3/6 | 0.3647 | 0.1765 |
| day5_consultation12 | 0.1229 | New onset headache | Tension-type headache; Migraine; Medication overuse headache | - | 1/1 | 0.3346 | 0.1933 |

## How to read this

- The diagnosis match and the highlight match are automatic (`public_scoring.py`): a match needs the same key words, after hedges such as "likely" and common shorthand are handled. A correct diagnosis in other words is counted as a miss, so check the table above by eye.
- ROUGE counts shared words. The clinicians wrote short notes in shorthand; the program writes full sentences in SOAP sections, so ROUGE is low even for a faithful note. It is useful for comparing runs, not as a grade.
- The two recordings of each consultation are mixed into one, as a single room microphone would hear them.
