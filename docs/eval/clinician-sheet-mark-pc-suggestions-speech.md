# Clinician scoring sheet

Read each script in `eval/scenarios/`, then the note below. Score each item from 1 (poor)
to 5 (excellent). Note anything unsafe. All consultations are synthetic.

## s01_fever: Fever and headache, malaria to be excluded

**Subjective:** the patient reports a fever for three days, a headache that will not go away, chills mostly at night, joint aches, vomiting once yesterday, no cough, no sore throat, no rash, no pain when passing urine, no long-term illnesses, no regular medication, paracetamol twice, it helps for a few hours, no allergies to medicines.

**Objective:** temperature is 38.6, pulse 96, blood pressure 118 over 76, throat looks normal, chest is clear, abdomen is soft with mild tenderness under the ribs on the right.

**Assessment (model):** not stated

**Plan:** check for malaria and do a full blood count today, keep taking paracetamol, drink plenty of fluids and rest, if you vomit repeatedly, get confused, or the fever worsens, come back immediately, see me again in two days with the results.

**AI suggestion 1:** malaria (the patient reports a fever and chills, and the doctor is checking for malaria.; check for malaria)
**AI suggestion 2:** infection (the patient reports a fever, headache, and joint aches.; check for malaria and do a full blood count)
**AI suggestion 3:** dehydration (the patient reports vomiting and the doctor is advising to drink plenty of fluids.; drink plenty of fluids)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

**Subjective:** The patient reports headaches almost every evening for about three weeks now. The headaches are at the back of the head and sometimes across the forehead, described as heavy and pressing, not sharp. Paracetamol helps a little. It is worse when stressed at work or skipping lunch. No vomiting, blurred vision, flashing lights, or weakness in arms/legs. Sometimes blurry vision with reading in the evening clears. No fever, neck stiffness, or recent fall/knock to the head. The patient reports waking up two times in the night to pass urine and is thirsty a lot. Weight loss of 2-3 kg over two months. Tingling in feet mostly at night, getting worse for about two months. No sores on feet, walks barefoot. Chest pain, palpitations or shortness of breath are not present. Mild ankle swelling by evening. The patient reports drinking 1-2 sodas daily (half liter). Likes salty food. Stops smoking four years ago. Drinks 2-3 beers on Saturdays. Walks 10 minutes in the morning to the stage. Father had diabetes and died of stroke at 63. Mother has high blood pressure. Brother has diabetes too. The patient reports mood is not low, but worried about health and work. Sleeps badly (5 hours). Patient reports headache becomes severe, vomiting, vision loss, chest pain, weakness on one side or confusion are concerning. Patient states she will stop ibuprofen.

**Objective:** Blood pressure today: 152/94. Repeat reading is 148/92. Pulse: 78 bpm, regular. Weight: 82 kg (3 kg less than last time). Temperature: Normal. Heart sounds: normal, no murmur. Chest: clear. Abdomen: soft, no tenderness. Mild pitting edema at both ankles. Foot exam: intact skin, no ulcers. Pulses present at feet. Reduced sensation on the soles of the feet and toes. Reduced ankle reflexes. Random blood sugar (finger prick): 11.2 mmol/L. HbA1c will be ordered. Kidney function tests will be ordered. Lipid profile will be ordered. Urine test for protein will be ordered. ECG will be performed today. Patient reports she has a glucometer and checks morning blood sugar around 9-10, and after meals around 12. Patient reports her neighbor has a blood pressure machine.

**Assessment (model):** Poorly controlled hypertension and diabetes mellitus with peripheral neuropathy suggested by symptoms of tingling in the feet and reduced sensation/reflexes. Lifestyle factors contributing to poor control (soda consumption, salty food).

**Plan:** Increase amlodipine from 5 mg daily to 10 mg daily, taken at the same time every morning. Increase metformin from 500 mg twice daily to 1 gram with breakfast and 500 milligrams with evening meal, taken with food. Stop ibuprofen due to potential kidney strain and blood pressure elevation. Order glycated hemoglobin (HbA1c), kidney function tests (creatinine and electrolytes), lipid profile, and urine test for protein. Order ECG today. Refer patient to eye clinic. Advise patient to cut soda completely and reduce sugar in tea. Choose water. Reduce salt intake and grill fish instead of frying it. Walk 30 minutes at least 5 days a week. Limit beer to 1 on Saturdays if possible. Patient should monitor home blood pressure and morning blood sugar for two weeks, bringing results with her next visit. Advise patient to check feet daily, wear closed shoes, and inspect inside shoes before wearing. If headache becomes severe, vomiting, vision loss, chest pain, weakness on one side or confusion occurs, return immediately. Wife is welcome at follow-up appointments.

**AI suggestion 1:** Hypertension (Blood pressure readings are elevated above target range.; Increase amlodipine dosage and advise lifestyle modifications.)
**AI suggestion 2:** Diabetes Mellitus with Peripheral Neuropathy (Elevated blood sugar, symptoms of tingling in feet, reduced sensation/reflexes suggest diabetic neuropathy.; Optimize diabetes control (metformin), foot care education, monitor for complications.)
**AI suggestion 3:** Dyslipidemia (Lipid profile is needed to assess risk factors for cardiovascular disease.; Recommend lifestyle modifications and consider statin therapy if indicated based on lipid panel results.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s03_child_diarrhoea: Child with watery diarrhoea and some dehydration

**Subjective:** The patient reports diarrhea for two days, six times a day, watery, no blood. No vomiting today. The patient is breastfeeding and drinking water, but passing less urine than usual. The patient is a little warm at night. The patient's sister had chicken pox last month, and the patient did not catch it. The patient is not on any medicine and has no allergies. The patient's vaccines are up to date.

**Objective:** Weight 10.2 kg. Temperature 37.9. Alert and playful. Eyes not sunken. Skin pinch goes back slowly, so he has some dehydration.

**Assessment (model):** Not stated

**Plan:** Give oral rehydration solution, 50-100 ml after each loose stool. Give zinc 20 mg once a day for 10 days. Keep breastfeeding and keep giving food. Return immediately if you see blood in the stool, if he cannot drink, if he becomes very sleepy, or if the vomiting returns. Bring him back in two days.

**AI suggestion 1:** Dehydration (Skin pinch goes back slowly.; Oral rehydration solution)
**AI suggestion 2:** Viral diarrhea (Diarrhea for two days, watery, no blood.; Oral rehydration solution, zinc)
**AI suggestion 3:** Possible mild dehydration (Passing less urine than usual.; Oral rehydration solution)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

**Subjective:** The patient reports burning when passing urine, increased frequency, no fever, no back pain, no blood or vaginal discharge, last period two weeks ago, denies pregnancy, no regular medicines, allergic to sulfur drugs, and a reaction to sulfur drugs.

**Objective:** Temperature 36.9, blood pressure 124/78, urine dipstick positive for nitrites and leukocytes, abdomen soft with mild tenderness above the pubic bone, pregnancy test negative.

**Assessment (model):** Not stated

**Plan:** Nitrofuranta 100 mg twice a day for five days, drink plenty of water, return same day for fever, back pain, or vomiting, return to see the doctor if not better in three days.

**AI suggestion 1:** Urinary tract infection (Positive nitrites and leukocytes on urine dipstick, burning with urination, increased frequency.; Nitrofuranta is an appropriate antibiotic for a simple UTI.)
**AI suggestion 2:** Sulfur allergy (Patient reports a reaction to sulfur drugs.; Avoid sulfa drugs like Coetrimoxazole.)
**AI suggestion 3:** Pregnancy (Patient denies pregnancy and the pregnancy test is negative.; Consider other causes of urinary symptoms.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s05_asthma: Moderate asthma attack with an aspirin allergy

**Subjective:** The patient reports wheezing, cough, and shortness of breath for two days. The patient uses salbutamol six to eight times a day. The patient does not have a brown inhaler at home. The patient denies fever and chest pain. The patient does not smoke. The patient is allergic to aspirin. The patient's peak flow is 250, with a best of 450. The patient describes the attack as moderate.

**Objective:** Rating rate is 24, pulse 104, oxygen saturation 94%. There is wheeze on both sides of the chest. Peak flow is 250.

**Assessment (model):** Not stated

**Plan:** Give salbutamol through a spacer, four puffs now, and repeat it. Give prednisolone 40 mg once a day for five days. Start beclomethasone 200 micrograms twice a day, every day, even when the patient feels well. Ask the patient's brother to smoke outside. Return in two days for review. Return at once if the patient cannot finish sentences, if the patient's lips look blue, or if the blue inhaler stops helping.

**AI suggestion 1:** Asthma exacerbation (Based on the patient's symptoms of wheezing, cough, and shortness of breath, along with the use of salbutamol and the peak flow reading.; Administer salbutamol, prednisolone, and beclomethasone. Educate the patient on proper inhaler technique and the importance of using the preventer medication even when feeling well.)
**AI suggestion 2:** Aspirin sensitivity (The patient reports that aspirin makes their wheezing worse.; Advise the patient to avoid aspirin and other NSAIDs.)
**AI suggestion 3:** Smoking exposure (The patient's brother smokes inside the house, which could be contributing to the patient's asthma symptoms.; Advise the patient's brother to smoke outside to protect the patient from secondhand smoke.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed

**Subjective:** The patient reports coughing for four weeks, bringing up sputum with blood, night sweats, weight loss of 5 kg, no chest pain or shortness of breath. The patient's cousin was treated for TB last year. The patient has never tested for HIV. The patient takes no medicines and has no allergies.

**Objective:** Temperature 37.8, Weight 58 kg, Oxygen saturation 96%, crackles in the upper part of the right lung.

**Assessment (model):** Not stated

**Plan:** Send two sputum samples for gene expert and request a chest x-ray. Do the HIV test today. Cover your mouth when you cough and wear a mask around others, and keep windows open at home. Come back in three days for the results.

**AI suggestion 1:** Possible tuberculosis (The patient reports coughing with blood, night sweats, weight loss, and a family history of TB.; Send sputum samples for gene expert and chest x-ray.)
**AI suggestion 2:** Possible HIV infection (The patient has never tested for HIV.; Do the HIV test today.)
**AI suggestion 3:** Possible pneumonia (Crackles in the upper part of the right lung.; Monitor the patient's symptoms and follow up with a chest x-ray.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s07_leg_infection: Cellulitis of the leg with a penicillin allergy

**Subjective:** The patient reports a red and painful right leg that was cut with a hoe 4 days ago. The patient had a fever last night. The patient denies pus, crackling under the skin, or red streaks going up the leg. The patient has a penicillin allergy with hives and lip swelling. The patient does not have diabetes or other illnesses. The patient takes no medicines. The patient does not remember when they last had a tetanus injection. The patient's temperature is 38.2, pulse is 98, and blood pressure is 130/84. The clinician states the patient has cellulitis.

**Objective:** The patient has a warm, red, tender area on the right shin, about 8 x 6 cm. No pus, no crackling under the skin, and no red streaks going up the leg. The clinician drew a line around the red area with a pen.

**Assessment (model):** Not stated

**Plan:** The clinician will give Glendamycin 300 mg four times a day for seven days. The patient will get a tetanus booster today. The patient should take paracetamol for pain and fever, and keep the leg raised when sitting. The patient should return the same day if the redness spreads past the pen line, or the fever gets worse. The patient will be seen again in two days.

**AI suggestion 1:** Cellulitis (Based on the patient's symptoms and physical exam findings.; Administer Glendamycin 300 mg four times a day for seven days. Provide tetanus booster today. Advise patient to keep leg elevated and take paracetamol for pain and fever. Instruct patient to return immediately if symptoms worsen or spread.)
**AI suggestion 2:** Penicillin Allergy (Patient reports a history of hives and lip swelling with penicillin.; Avoid amoxicillin and fluocloxicillin. Administer Glendamycin instead.)
**AI suggestion 3:** Tetanus (Patient does not remember when they last had a tetanus injection.; Administer tetanus booster today.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

**Subjective:** the patient is 24 weeks pregnant. The baby is moving well. No bleeding, leaking of fluid, or pain. No headaches, swelling of the face, or problems with vision. The patient is taking iron and folic acid tablets. No allergies. Hemoglobin is 10.1. The top of the womb measures 24 cm, which matches your dates. The baby's heart rate is 144.

**Objective:** Blood pressure 118 over 72. The top of the womb measures 24 cm. The baby's heart rate is 144. Hemoglobin is 10.1.

**Assessment (model):** not stated

**Plan:** The patient will get their second tetanus injection and their first dose of SP to prevent malaria. Sleep under a treated mosquito net. The patient should take 60 mg of iron a day with folic acid and eat beans and green vegetables. The patient should come back at 28 weeks. The patient should come at once if they have bleeding, a severe headache, swelling of the face, or if the baby moves less.

**AI suggestion 1:** iron deficiency (hemoglobin is 10.1; take 60 mg of iron a day with folic acid and eat beans and green vegetables)
**AI suggestion 2:** malaria prevention (first dose of SP; sleep under a treated mosquito net)
**AI suggestion 3:** tetanus prevention (second injection; come back at 28 weeks)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

