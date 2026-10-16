# PriMock57: 57 consultations, input from speech

Dataset: PriMock57 (Korfiatis et al., ACL 2022; Babylon Health), CC BY 4.0, https://github.com/babylonhealth/primock57. The dataset is not stored in this repository; only these
scores are. Machine: 12 logical CPUs, 7.9 GB RAM, 0.5 GB free at the start.

## Summary

| Measure | Result |
|---|---|
| consultations run | 57 |
| notes produced | 56/57 (98.2%) |
| needed the second attempt | 13 |
| speech-to-text word error rate (fillers removed; weighted by words) | 0.146 |
| notes stating a diagnosis | 48 of 56 |
| clinician's diagnosis among the AI's suggestions | 38/48 (79.2%) |
| ... as the first suggestion | 35/48 (72.9%) |
| clinician's highlights covered by the note | 129/238 (54.2%) |
| ROUGE-1 / ROUGE-2 / ROUGE-L against the clinician's note (mean F1) | 0.327 / 0.08 / 0.182 |
| median seconds: speech-to-text / drafting | 108.7 / 98.8 |

No note after two attempts: day1_consultation14.

## Each consultation

| Consultation | WER | Clinician's diagnosis | AI suggestions | Rank | Highlights | R-1 | R-L |
|---|---|---|---|---|---|---|---|
| day1_consultation01 | 0.1675 | gastroenteritis | Gastroenteritis | 1 | 5/5 | 0.3712 | 0.1773 |
| day1_consultation02 | 0.1605 | flare up of eczema | Eczema | 1 | 3/5 | 0.3442 | 0.2077 |
| day1_consultation03 | 0.1496 | migraine | Migraine; Tension Headache; Medication Overuse Headache | 1 | 4/6 | 0.3631 | 0.1899 |
| day1_consultation04 | 0.2047 | viral URTI; influenza | Viral upper respiratory tract infection (URTI); Influenza; Myalgia | 1 | 4/5 | 0.4211 | 0.2632 |
| day1_consultation05 | 0.1257 | UTI | Urinary Tract Infection (UTI) | 1 | 4/5 | 0.3032 | 0.1663 |
| day1_consultation06 | 0.179 | exacerbation of heart failure | Heart failure exacerbation | 1 | 6/6 | 0.3782 | 0.2539 |
| day1_consultation07 | 0.2559 | viral URTI; LRTI | Upper Respiratory Infection; Elevated Blood Pressure; Possible Bacterial Superinfection (Secondary) | 1 | 3/5 | 0.3472 | 0.1944 |
| day1_consultation08 | 0.2054 | dermatitis | Dermatitis | 1 | 2/5 | 0.2623 | 0.1967 |
| day1_consultation09 | 0.17 | UTI; cystitis | Urinary Tract Infection; IBS; Pregnancy | 1 | 2/5 | 0.3111 | 0.1833 |
| day1_consultation10 | 0.208 | UTI | Urinary Tract Infection (UTI); Interstitial Cystitis; Vaginitis | 1 | 3/5 | 0.2422 | 0.1553 |
| day1_consultation11 | 0.166 | gastroenteritis | Gastroenteritis; Dehydration; Possible food poisoning | 1 | 5/7 | 0.3721 | 0.1993 |
| day1_consultation12 | 0.1324 | gastroenteritis | Gastroenteritis | 1 | 2/4 | 0.3649 | 0.2456 |
| day1_consultation13 | 0.0984 | migraines | Migraine; Tension Headache; Medication Overuse Headache | 1 | 3/6 | 0.2871 | 0.1412 |
| day1_consultation14 | 0.179 | | no note (['repetition_detected', 'repetition_detected']) | | | | |
| day1_consultation15 | 0.1588 | contact dermatitis | Contact dermatitis | 1 | 1/5 | 0.3052 | 0.1688 |
| day2_consultation01 | 0.1272 | (none written) | Tinnitus; Wax impaction; Vestibular dysfunction | - | 3/4 | 0.3587 | 0.2283 |
| day2_consultation02 | 0.1628 | possible bursitis | Bursitis | 1 | 3/7 | 0.2604 | 0.144 |
| day2_consultation03 | 0.1957 | Bell's Palsy | Valve palsy | - | 1/5 | 0.3516 | 0.1844 |
| day2_consultation04 | 0.1164 | probable LRTI | Possible chest infection or pneumonia; Consider lung cancer; SLE (Systemic Lupus Erythematosus) | 1 | 1/1 | 0.354 | 0.1925 |
| day2_consultation05 | 0.104 | TIAs | Transient ischemic attack (TIA); Stroke; Peripheral neuropathy | 1 | 1/1 | 0.2863 | 0.145 |
| day2_consultation06 | 0.1436 | localized inflammatory reaction to insect bite; cellulitis |  | - | 1/6 | 0.29 | 0.14 |
| day2_consultation07 | 0.1477 | acute cardiac event | Acute Coronary Syndrome (ACS) | - | 3/9 | 0.2329 | 0.1285 |
| day2_consultation08 | 0.1214 | PUO | Malaria; Viral illness (e.g., influenza-like illness); Other infectious cause | - | 4/14 | 0.402 | 0.229 |
| day2_consultation09 | 0.1255 | CVA | Stroke | 1 | 3/6 | 0.3394 | 0.1949 |
| day2_consultation10 | 0.1077 | tension type headache | Tension Headache; Migraine; Stress-related headache | 1 | 7/7 | 0.4041 | 0.2226 |
| day3_consultation01 | 0.1853 | anaphylactic reaction | Anaphylaxis | - | 4/4 | 0.3698 | 0.1811 |
| day3_consultation02 | 0.1366 | (none written) | Viral illness; Meningitis; Dengue Fever; Zika Virus | - | 2/3 | 0.4098 | 0.2732 |
| day3_consultation03 | 0.1378 | (none written) | Major Depressive Disorder; Hypothyroidism (untreated); Anxiety Disorder | - | 1/4 | 0.344 | 0.1881 |
| day3_consultation04 | 0.1651 | (none written) | Asthma exacerbation; Eczema; Hay fever | - | 3/4 | 0.4096 | 0.1915 |
| day3_consultation05 | 0.1002 | labrynthitis | Labyrinthitis | 1 | 2/4 | 0.3985 | 0.2452 |
| day3_consultation06 | 0.1289 | urticaria | Anaphylaxis; Articulatory reaction; Asthma exacerbation | - | 2/4 | 0.3012 | 0.2048 |
| day3_consultation07 | 0.1552 | (none written) | Eczema; Hypothyroidism; Asthma | - | 3/4 | 0.4359 | 0.2222 |
| day3_consultation08 | 0.1193 | Upper respiratory tract infection | Viral URI | 1 | 2/2 | 0.4 | 0.2947 |
| day3_consultation09 | 0.102 | (none written) | Multiple Sclerosis | - | 0/3 | 0.3833 | 0.2021 |
| day3_consultation10 | 0.1077 | Gastroenteritis | Acute infectious gastroenteritis; Irritable Bowel Syndrome (IBS); Medication-induced diarrhea | 1 | 2/4 | 0.3099 | 0.1972 |
| day4_consultation01 | 0.1275 | MI; PE; GORD | Angina pectoris; Myocardial infarction; Pulmonary embolism | 2 | 1/1 | 0.3161 | 0.1884 |
| day4_consultation02 | 0.0923 | hypothyroid | Hypothyroidism; Anxiety/Stress related headache; Cardiovascular issues | 1 | 1/1 | 0.284 | 0.1479 |
| day4_consultation03 | 0.0884 | PE | possible pulmonary embolism | 1 | 1/1 | 0.2166 | 0.1227 |
| day4_consultation04 | 0.0816 | acute exacerbation of asthma; allergy | Asthma; Not stated | 1 | 1/1 | 0.2203 | 0.1145 |
| day4_consultation05 | 0.1945 | gastroenteritis | Gastroenteritis | 1 | 1/1 | 0.2468 | 0.1447 |
| day4_consultation06 | 0.1256 | migraine | Migraine | 1 | 1/1 | 0.3732 | 0.1749 |
| day4_consultation07 | 0.1703 | (none written) | Acute bronchitis; Viral upper respiratory infection; Pneumonia | - | 1/1 | 0.2806 | 0.1373 |
| day4_consultation08 | 0.1501 | depression | Hypothyroidism; Depression; Anxiety | 2 | 1/1 | 0.3223 | 0.2231 |
| day4_consultation09 | 0.1545 | Asthma exacerbation | Asthma exacerbation | 1 | 1/1 | 0.2827 | 0.1627 |
| day4_consultation10 | 0.1318 | Simple constipation; PID; STI; UTI | Constipation; Gastroenteritis; Pregnancy | 1 | 1/1 | 0.2014 | 0.1439 |
| day5_consultation01 | 0.1564 | Tension headache; first episode migraine | Migraine; Tension Headache; Cluster Headache | 1 | 2/6 | 0.3205 | 0.1543 |
| day5_consultation02 | 0.0944 | Likely UTI | Urinary tract infection; IBS; Kidney stones | 1 | 1/4 | 0.2887 | 0.1512 |
| day5_consultation03 | 0.1215 | Work related anxiety | Generalized Anxiety Disorder (GAD); Panic Disorder; Adjustment Disorder with Anxious Distress | - | 0/5 | 0.2796 | 0.1505 |
| day5_consultation04 | 0.1841 | Abdominal pain cause | Pelvic Inflammatory Disease (PID); Ectopic Pregnancy; Ovarian Cyst | - | 1/4 | 0.2824 | 0.1527 |
| day5_consultation05 | 0.1342 | UTI | Urinary Tract Infection | 1 | 4/5 | 0.3093 | 0.1547 |
| day5_consultation06 | 0.1473 | Gastroenteritis Viral; food poisoning | Viral gastroenteritis; Bacterial gastroenteritis; Other causes of abdominal pain | 1 | 1/5 | 0.2974 | 0.1385 |
| day5_consultation07 | 0.1131 | Viral bronchitis | Viral upper respiratory infection; Secondary bacterial bronchitis/pneumonia (possible); Acute bronchitis | 2 | 1/4 | 0.3277 | 0.1303 |
| day5_consultation08 | 0.1056 | Exacerbation asthma | Asthma exacerbation; Viral upper respiratory infection | 1 | 3/5 | 0.3604 | 0.1486 |
| day5_consultation09 | 0.1617 | 6/52 hx fatigue; hx circular rash on calf | Lyme Disease; Viral Infection; Asthma exacerbation | - | 3/6 | 0.303 | 0.1595 |
| day5_consultation10 | 0.1542 | Likely migraine | Migraine; Tension Headache; Cluster Headache | 1 | 4/7 | 0.3903 | 0.161 |
| day5_consultation11 | 0.1074 | (none written) | Osteoarthritis; Patellofemoral Pain Syndrome; Ligament Injury (ACL or MCL) | - | 3/6 | 0.3844 | 0.1946 |
| day5_consultation12 | 0.1229 | New onset headache | Tension headache | - | 1/1 | 0.3177 | 0.2022 |

## How to read this

- The diagnosis match and the highlight match are automatic (`public_scoring.py`): a match needs the same key words, after hedges such as "likely" and common shorthand are handled. A correct diagnosis in other words is counted as a miss, so check the table above by eye.
- ROUGE counts shared words. The clinicians wrote short notes in shorthand; the program writes full sentences in SOAP sections, so ROUGE is low even for a faithful note. It is useful for comparing runs, not as a grade.
- The two recordings of each consultation are mixed into one, as a single room microphone would hear them.
