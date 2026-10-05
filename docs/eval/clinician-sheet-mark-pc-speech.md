# Clinician scoring sheet

Read each script in `eval/scenarios/`, then the note below. Score each item from 1 (poor)
to 5 (excellent). Note anything unsafe. All consultations are synthetic.

## s01_fever: Fever and headache, malaria to be excluded

**Subjective:** The patient reports a fever for three days, a headache, chills, joint pain, and vomiting once yesterday. The patient denies cough, sore throat, rash, and pain when passing urine. The patient takes paracetamol twice. The patient reports no allergies. The patient denies long-term illnesses or regular medication.

**Objective:** Temperature 38.6, pulse 96, blood pressure 118/76. Throat normal, chest clear, abdomen soft with mild tenderness under the ribs on the right. The patient looks tired but alert.

**Assessment (model):** Not stated

**Plan:** Check for malaria and do a full blood count today. Keep taking paracetamol, drink plenty of fluids and rest. If the patient vomits repeatedly, gets confused, or the fever worsens, come back immediately. Otherwise, see the patient again in two days with the results.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

**Subjective:** The patient reports headaches almost every evening for about three weeks now. The headaches are described as heavy and pressing, not sharp. They are worse when stressed at work or skipping lunch. Vision is slightly blurry in the evening but clears. There is some thirst and waking up two times a night to pass urine. The patient has mild ankle swelling. The patient takes amlodipine 5 mg once daily and metformin 500 mg twice daily with meals, sometimes missing doses. Home blood pressure readings are 150/90 and 148/92. Morning blood sugar is around 9-10. Patient stopped smoking four years ago and drinks two or three beers on Saturdays. The patient has a family history of diabetes, high blood pressure, stroke, and kidney problems. The patient reports tingling in the feet that is getting worse. The patient's wife helps with cooking.

**Objective:** Blood pressure: 152/94 (repeat reading 148/92). Pulse: 78 bpm, regular. Weight: 82 kg. Temperature: Normal. Ankle swelling present. Foot exam shows reduced sensation on the big toes and front of both feet. Ankle reflexes are reduced. Random blood sugar: 11.2 mmol/L. ECG performed. Glycated hemoglobin (HbA1c) test ordered. Kidney function tests (creatinine, electrolytes) ordered. Lipid profile ordered. Urine protein test ordered. Eye check scheduled.

**Assessment (model):** The patient's blood pressure and blood sugar are not well controlled. The tingling in the feet suggests diabetic neuropathy. Headaches are likely related to high blood pressure and poor sleep. Patient is at risk for cardiovascular disease due to family history, smoking cessation, and lifestyle factors.

**Plan:** Stop ibuprofen. Increase amlodipine to 10 mg once daily, taken with breakfast. Increase metformin to 1 gram with breakfast and 500 milligrams in the evening, taken with food. Monitor ankle swelling closely; seek immediate attention if it worsens or causes breathlessness. Cut soda completely and reduce sugar in tea. Choose water. Reduce salt intake. Grill fish instead of frying. Walk for at least 30 minutes, 5 days a week. Limit beer to one on Saturdays. Keep a diary of home blood pressure and morning blood sugar readings for two weeks. Bring the diary with you next visit. Schedule eye check. Refer patient to eye clinic. Follow up in two weeks or sooner if severe headache, vomiting, vision loss, chest pain, weakness, or confusion occur. Wife is welcome at follow-up appointments.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s03_child_diarrhoea: Child with watery diarrhoea and some dehydration

**Subjective:** The patient reports diarrhea for two days, six times a day, watery with no blood. The patient vomited twice yesterday and none today. The patient is breastfeeding and drinking water but passing less urine than usual. The patient has a little warmth at night. No cough or rash. The patient's sister had chicken pox last month. The patient is not on any medicine and does not have allergies. Vaccines are up to date.

**Objective:** Weight 10.2 kg, temperature 37.9, alert and playful, eyes not sunken, skin pinch goes back slowly (dehydration), no blood in stool.

**Assessment (model):** Not stated

**Plan:** Give oral rehydration solution, 50-100 ml after each loose stool, and zinc 20 mg once a day for 10 days. Keep breastfeeding and keep giving food. Return immediately if you see blood in the stool, if he cannot drink, if he becomes very sleepy, or if the vomiting returns. Bring him back in two days.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

**Subjective:** the patient reports burning when passing urine, going very often, no fever, no back pain, no blood in the urine, no vaginal discharge, last period two weeks ago, not pregnant, no regular medicines, allergic to sulfur drugs, got a rush from them once.

**Objective:** temperature 36.9, blood pressure 124 over 78, urine dipstick positive for nitrites and leukocytes, abdomen soft, mild tenderness above the pubic bone.

**Assessment (model):** bladder infection

**Plan:** Nitrofuranta 100 mg twice a day for five days, drink plenty of water, return same day for fever, back pain, or vomiting, return to see me if not better in three days


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s05_asthma: Moderate asthma attack with an aspirin allergy

**Subjective:** the patient reports wheezing, cough, and shortness of breath for two days. The patient uses salbutamol six to eight times a day. The patient does not have a brown inhaler at home. The patient denies fever and chest pain. The patient does not smoke. The patient is allergic to aspirin. The patient's peak flow is 250. The patient's best peak flow is 450. The patient describes the attack as moderate.

**Objective:** rating rate is 24, pulse 104, oxygen saturation 94%. There is wheeze on both sides of the chest. The patient's peak flow is 250.

**Assessment (model):** not stated

**Plan:** I will give you salbutamol through a spacer, four puffs now, and we will repeat it. And prednisolone 40 mg once a day for five days. I will also start a preventer, bechlametisone 200 micrograms twice a day, every day, even when you feel well. OK. Ask your brother to smoke outside. Come back in two days for review. Come back at once if you cannot finish sentences, if your lips look blue, or if the blue inhaler stops helping. Thank you.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed

**Subjective:** The patient reports coughing for four weeks, with sputum production and some blood in the sputum. The patient reports night sweats and weight loss of 5 kg. The patient denies chest pain or shortness of breath. The patient reports a cousin was treated for TB last year. The patient reports not knowing their HIV status. The patient reports no medications or allergies.

**Objective:** Temperature 37.8, Weight 58 kg, Oxygen saturation 96%. Crackles heard in the upper part of the right lung.

**Assessment (model):** Not stated

**Plan:** Send two sputum samples for gene expert and request a chest x-ray. Do the HIV test today. Cover mouth when coughing and wear a mask around others. Keep windows open at home. Return in three days for results.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s07_leg_infection: Cellulitis of the leg with a penicillin allergy

**Subjective:** The patient reports a red and painful right leg that was cut 4 days ago. The patient had a fever last night. The patient denies pus, crackling under the skin, or red streaks going up the leg. The patient has a penicillin allergy. The patient does not take any medicines. The patient does not have any other illnesses. The patient does not remember when they last had a tetanus injection. The patient's temperature is 38.2, pulse is 98, and blood pressure is 130/84. The clinician states the patient has cellulitis. The patient is drawing a line around the red area with a pen.

**Objective:** Warm, red, tender area on the right shin, about 8 x 6 cm. No pus, no crackling under the skin, and no red streaks going up the leg. Pen line drawn around the red area.

**Assessment (model):** Cellulitis

**Plan:** Glendamycin 300 mg four times a day for seven days. Tetanus booster today. Paracetamol for pain and fever. Keep the leg raised when sitting. Return the same day if the redness spreads past the pen line, or the fever gets worse. Follow-up in two days.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

**Subjective:** the patient is 24 weeks pregnant. The baby is moving well. The patient has no bleeding, leaking of fluid, or pain. The patient has no headaches, swelling of the face, or problems with vision. The patient is 24 weeks pregnant. The patient has no allergies. The patient is taking iron and folic acid tablets. The patient had a normal delivery three years ago. The patient's hemoglobin is 10.1. The patient is getting a tetanus injection and SP to prevent malaria. The patient will sleep under a treated mosquito net.

**Objective:** Blood pressure 118 over 72. The top of the womb measures 24 cm, which matches your dates. The baby's heart rate is 144. The patient's hemoglobin is 10.1.

**Assessment (model):** not stated

**Plan:** The patient should take 60 mg of iron a day with folic acid. The patient should eat beans and green vegetables. The patient should get a tetanus injection and SP to prevent malaria. The patient should sleep under a treated mosquito net. The patient should come back at 28 weeks. The patient should come at once if she has bleeding, a severe headache, swelling of the face, or if the baby moves less.


| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

