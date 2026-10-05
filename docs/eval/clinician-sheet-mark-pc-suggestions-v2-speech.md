# Clinician scoring sheet

Read each script in `eval/scenarios/`, then the note below. Score each item from 1 (poor)
to 5 (excellent). Note anything unsafe. All consultations are synthetic.

## s01_fever: Fever and headache, malaria to be excluded

**Subjective:** The patient reports a fever for three days, a headache that will not go away, chills mostly at night, and joint aches. The patient vomited once yesterday. The patient takes paracetamol twice. The patient denies cough, sore throat, rash, or pain when passing urine. The patient denies long-term illnesses or regular medication. The patient denies allergies to medicines.

**Objective:** Temperature 38.6, pulse 96, blood pressure 118 over 76. Throat looks normal, chest is clear, abdomen is soft with mild tenderness under the ribs on the right.

**Assessment (model):** not stated

**Plan:** Check for malaria and do a full blood count today. Keep taking paracetamol, drink plenty of fluids and rest. If you vomit repeatedly, get confused, or the fever worsens, come back immediately. Otherwise, see me again in two days with the results.

**AI suggestion 1:** Fever (The patient reports a fever for three days.; Keep taking paracetamol, drink plenty of fluids and rest.)
**AI suggestion 2:** Headache (The patient reports a headache that will not go away.; Keep taking paracetamol, drink plenty of fluids and rest.)
**AI suggestion 3:** Joint pain (The patient reports joint aches.; Keep taking paracetamol, drink plenty of fluids and rest.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s02_hypertension_diabetes: Hypertension and type 2 diabetes follow-up

**Subjective:** The patient reports headaches almost every evening for about three weeks now. The headaches are described as heavy and pressing, felt at the back of the head and sometimes across the forehead. Paracetamol helps a little. It is worse when stressed at work or skipping lunch. No vomiting, blurred vision, flashing lights, or weakness in arms/legs. Sometimes vision is slightly blurry when reading in the evening, clearing up later. Wakes up two times per night to pass urine, and thirsty a lot. Weight loss of about 2-3 kg over two months. Tingling in feet, mostly at night, worse on toes. Has been going on for about two months. No sores or wounds on feet. Ankle reflexes are reduced. Random blood sugar is 11.2 mmol/L. Patient stopped smoking four years ago and drinks 2-3 beers on Saturdays. Not much exercise, just walking to the stage in the morning (about 10 minutes). Father had diabetes and died of stroke at 63. Mother has high blood pressure. Brother has diabetes too. The patient is worried about their health and work. Patient takes amlodipine 5 mg once daily, metformin 500mg twice daily with meals, and sometimes bupren when headache is very bad. Blood pressure readings are 150/90 and 148/92 at home. Morning blood sugar is 9-10. Patient has a glucometer. The patient's wife helps with food.

**Objective:** Blood pressure: 152/94, 148/92. Pulse: 78 bpm, regular. Weight: 82 kg (3 kg less than last time). Temperature: Normal. Ankle swelling present at both ankles. Foot exam shows reduced sensation on big toes and front of feet. Reduced ankle reflexes. Random blood sugar: 11.2 mmol/L. ECG performed. Patient has a glucometer.

**Assessment (model):** The patient reports headaches, high blood pressure (150/94), elevated random blood glucose (11.2 mmol/L), and peripheral neuropathy with reduced sensation in the feet. The patient is also experiencing nocturia and polydipsia. The patient's lifestyle contributes to poor control of hypertension and diabetes.

**Plan:** Increase amlodipine to 10 mg once daily, take at the same time every morning. Increase metformin to 1 gram with breakfast and 500mg with evening meal, take with food. Stop ibuprofen. Refer for eye check. Order glycated hemoglobin (HbA1c), kidney function tests (creatinine and electrolytes), lipid profile, urine test for protein, and ECG. Patient should monitor home blood pressure and morning blood sugar for two weeks and bring results to follow-up appointment. Encourage patient to reduce soda intake and sugar in tea. Reduce salt intake and choose grilled fish over fried. Increase walking to 30 minutes at least 5 days a week. Limit beer to one on Saturdays, if possible. Patient should check feet daily, wear closed shoes, and inspect inside before putting them on. If any wounds or sores are found, return immediately. Follow-up appointment in two weeks, sooner if headache is severe, vomiting occurs, vision loss, chest pain, weakness, or confusion develops. Wife to accompany patient to follow-up appointments.

**AI suggestion 1:** Hypertension (Blood pressure readings are consistently elevated above target (152/94 and 148/92).; Increase amlodipine dosage.)
**AI suggestion 2:** Hyperglycemia (Random blood glucose is elevated at 11.2 mmol/L, indicating poor glycemic control.; Increase metformin dosage and emphasize dietary modifications (reduce sugar intake, choose water).)
**AI suggestion 3:** Peripheral Neuropathy (Reduced sensation in the feet suggests nerve damage due to diabetes.; Monitor blood glucose levels closely. Encourage lifestyle changes (walking, foot care) to improve circulation and reduce nerve damage.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s03_child_diarrhoea: Child with watery diarrhoea and some dehydration

**Subjective:** The patient reports diarrhea for two days, six times a day, watery, no blood. The patient reports vomiting twice yesterday, none today. The patient reports breastfeeding and drinking water, but passing less urine than usual. The patient reports a little warm at night. The patient reports no cough and no rash. The patient's sister had chicken pox last month. The patient is not on any medicine and has no allergies. The patient's vaccines are up to date. The patient's weight is 10.2 kg. The patient's temperature is 37.9. The patient is alert and playful. The patient's eyes are not sunken. The skin pinch goes back slowly, so he has some dehydration. The patient does not need antibiotics.

**Objective:** Weight 10.2 kg. Temperature 37.9. Alert and playful. Eyes not sunken. Skin pinch goes back slowly, so he has some dehydration.

**Assessment (model):** not stated

**Plan:** Give oral rehydration solution, 50-100 ml after each loose stool, and zinc 20 mg once a day for 10 days. Keep breastfeeding and keep giving food. Come back immediately if you see blood in the stool, if he cannot drink, if he becomes very sleepy, or if the vomiting returns. Otherwise bring him back in two days.

**AI suggestion 1:** viral diarrhea (The patient reports diarrhea for two days, watery, no blood. The clinician states this looks like a viral diarrhea.; Give oral rehydration solution, 50-100 ml after each loose stool, and zinc 20 mg once a day for 10 days.)
**AI suggestion 2:** dehydration (The skin pinch goes back slowly, so he has some dehydration.; Give oral rehydration solution, 50-100 ml after each loose stool.)
**AI suggestion 3:** mild fever (The patient reports a little warm at night. The patient's temperature is 37.9.; Keep breastfeeding and keep giving food.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s04_urinary_infection: Uncomplicated bladder infection with a sulfa allergy

**Subjective:** The patient reports burning when passing urine and increased frequency of urination for three days. The patient denies fever, back pain, or pain in the sides. The patient denies blood in the urine or vaginal discharge. The patient's last period was two weeks ago and she does not think she is pregnant. The patient takes no regular medicines but is allergic to sulfur drugs. A urine dipstick test is positive for nitrites and leukocytes. A pregnancy test is negative.

**Objective:** Temperature 36.9, blood pressure 124/78. Urine dipstick: positive for nitrites and leukocytes. Abdomen soft with mild tenderness above the pubic bone. Pregnancy test negative.

**Assessment (model):** Bladder infection

**Plan:** Nitrofuranta 100 mg twice a day for five days. Drink plenty of water. Return precautions: fever, back pain, or vomiting. If not better in three days, return to see me.

**AI suggestion 1:** Urinary tract infection (Positive nitrites and leukocytes on urine dipstick test.; Nitrofuranta prescribed.)
**AI suggestion 2:** Bladder inflammation (Burning sensation when passing urine and increased frequency of urination, along with positive nitrites and leukocytes.; Nitrofuranta prescribed.)
**AI suggestion 3:** Possible cystitis (Symptoms are consistent with bladder infection.; Nitrofuranta prescribed.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s05_asthma: Moderate asthma attack with an aspirin allergy

**Subjective:** The patient reports wheezing, cough, shortness of breath, and increased use of salbutamol inhaler (6-8 times a day). The patient denies fever and chest pain. The patient reports no smoking. The patient reports aspirin allergy. The patient reports peak flow of 250, best of 450. The patient reports moderate attack.

**Objective:** Rating rate is 24, pulse 104, oxygen saturation 94%. There is wheeze on both sides of the chest. Peak flow is 250.

**Assessment (model):** not stated

**Plan:** Give salbutamol through a spacer, four puffs now, and repeat. Give prednisolone 40 mg once a day for five days. Start bechlametisone 200 micrograms twice a day, every day, even when the patient feels well. Ask the patient's brother to smoke outside. Return in two days for review. Return at once if the patient cannot finish sentences, if the patient's lips look blue, or if the blue inhaler stops helping.

**AI suggestion 1:** Asthma exacerbation (The patient reports wheezing, cough, shortness of breath, and increased use of salbutamol inhaler. The patient's peak flow is 250, best of 450. The patient reports moderate attack.; Administer salbutamol, prednisolone, and bechlametisone. Advise the patient to smoke outside.)
**AI suggestion 2:** Aspirin-exacerbated respiratory disease (AERD) (The patient reports aspirin allergy. The patient reports wheezing, cough, shortness of breath, and increased use of salbutamol inhaler.; Advise the patient to avoid aspirin. Consider bechlametisone.)
**AI suggestion 3:** Bronchospasm (The patient reports wheezing, cough, shortness of breath, and increased use of salbutamol inhaler.; Administer salbutamol. Advise the patient to smoke outside.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s06_possible_tb: Chronic cough, tuberculosis suspected but not diagnosed

**Subjective:** The patient reports coughing for four weeks that is not going away. The patient brings up sputum with blood two times. The patient has night sweats and weight loss of about 5 kg. The patient denies chest pain or shortness of breath. The patient's cousin was treated for TB last year. The patient does not know their HIV status. The patient takes no medicines and has no allergies.

**Objective:** Temperature 37.8, Weight 58 kg, Oxygen saturation 96%, Crackles in the upper part of the right lung.

**Assessment (model):** not stated

**Plan:** Send two sputum samples for gene expert and request a chest x-ray. Do the HIV test today. Cover your mouth when you cough and wear a mask around others, and keep windows open at home. Come back in three days for the results.

**AI suggestion 1:** Pneumonia (The patient reports coughing for four weeks that is not going away. The patient brings up sputum with blood two times. Crackles are heard in the upper part of the right lung.; Antibiotics)
**AI suggestion 2:** Tuberculosis (TB) (The patient's cousin was treated for TB last year. The patient suspects TB and has night sweats and weight loss.; Further testing is needed to confirm or rule out TB.)
**AI suggestion 3:** HIV Infection (The patient does not know their HIV status. An HIV test will be done today.; Initiate appropriate management based on the HIV test results.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s07_leg_infection: Cellulitis of the leg with a penicillin allergy

**Subjective:** The patient reports a red and painful right leg that was cut on a hoe four days ago. The redness started three days ago. The patient had a fever last night. There is no pus, crackling under the skin or red streaks going up the leg. The patient has a penicillin allergy with hives and lip swelling. The patient does not have diabetes or other illnesses. The patient takes no medicines. The patient's last tetanus injection was many years ago. Temperature 38.2, pulse 98, blood pressure 130 over 84.

**Objective:** Warm, red, tender area on the right shin, about 8 x 6 cm. No pus, no crackling under the skin, and no red streaks going up the leg. Pen line drawn around the red area.

**Assessment (model):** Cellulitis

**Plan:** Glendamycin 300 mg four times a day for seven days. Tetanus booster today. Paracetamol for pain and fever. Keep the leg raised when sitting. Return same day if redness spreads past pen line or fever gets worse. Follow-up in two days.

**AI suggestion 1:** Cellulitis (The patient reports a red, painful area on their shin that started three days ago after being cut with a hoe. The skin is warm and tender.; Glendamycin 300 mg four times a day for seven days.)
**AI suggestion 2:** Tetanus (The patient's last tetanus injection was many years ago, and they were exposed to a potential wound source.; Tetanus booster today.)
**AI suggestion 3:** Fever (The patient reports having a fever last night. The temperature is 38.2 degrees Celsius.; Paracetamol for pain and fever.)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

## s08_antenatal: Routine antenatal visit at 24 weeks with mild anaemia

**Subjective:** the patient is 24 weeks pregnant, the baby is moving well, no bleeding, leaking, or pain, no headaches or swelling, vision is fine, second pregnancy, first baby was born normally three years ago, taking iron and folic acid tablets every day, no allergies, hemoglobin is 10.1, mild, eat beans and green vegetables, second tetanus injection and first dose of SP to prevent malaria, sleep under a treated mosquito net, return precautions are bleeding, severe headache, swelling of the face, or if the baby moves less, return in 28 weeks

**Objective:** blood pressure 118 over 72, top of the womb measures 24 cm, baby's heart rate is 144, hemoglobin is 10.1

**Assessment (model):** not stated

**Plan:** take iron 60 mg a day with folic acid, take second tetanus injection and first dose of SP to prevent malaria, sleep under a treated mosquito net, return in 28 weeks, return at once if you have bleeding, a severe headache, swelling of your face, or if the baby moves less

**AI suggestion 1:** iron deficiency anemia (hemoglobin is 10.1; take iron 60 mg a day with folic acid)
**AI suggestion 2:** malaria (first dose of SP to prevent malaria; sleep under a treated mosquito net)
**AI suggestion 3:** tetanus (second tetanus injection; take second tetanus injection)

| Item | Score 1 to 5 | Comment |
|---|---|---|
| Accurate (nothing wrong or invented) | | |
| Complete (nothing important missing) | | |
| Organised (right section, easy to read) | | |
| Safe to use after review | | |
| AI suggestions sensible (if any) | | |

