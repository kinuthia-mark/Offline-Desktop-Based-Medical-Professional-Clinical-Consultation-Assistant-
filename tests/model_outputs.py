"""Real MedGemma outputs captured in the spike (docs/spikes), on SYNTHETIC consultations only.
Used to check the repetition detector and grounding flags against genuine model behaviour."""

import json

GOOD_LONG_632 = json.dumps(
    {
        "subjective": "The patient reports headaches almost every evening for three weeks. The headaches are described as heavy and pressing at the back of the head and sometimes across the forehead. They are not sharp. Paracetamol helps a little. The headaches worsen with stress at work and skipping lunch. The patient experiences slight blurry vision in the evening, clearing up on its own. No vomiting or weakness is reported. The patient reports waking two times per night to urinate and experiencing increased thirst. The patient has lost about 2-3 kg in weight over the last two months. The patient reports tingling/pins and needles sensation in both feet, especially at night, which has been going on for approximately two months and is getting worse. Patient states that ibuprofen helps with headache but it raises blood pressure.",
        "objective": "Blood pressure: 152/94 mmHg (twice). Pulse: 78 bpm, regular. Weight: 82 kg (3 kg less than last visit). Temperature: Normal. Heart sounds: Normal. Chest: Clear. Abdomen: Soft, no tenderness. Mild pitting edema at both ankles. Foot exam: Intact skin, no ulcers. Pulses present in feet. Reduced sensation on the big toes and front of both feet. Reduced ankle reflexes. Random blood sugar (finger prick): 11.2 mmol/L. HbA1c not stated. Kidney function tests not stated. Lipid profile not stated. Urine test not stated. ECG not stated. Patient reports that he has a neighbour's blood pressure machine and it read 150/90 and 148/92.",
        "assessment": "The patient presents with uncontrolled hypertension, hyperglycemia (elevated random blood sugar), peripheral neuropathy (tingling in feet), and possible ankle edema. The headaches are likely related to the high blood pressure and poor sleep quality. The patient's lifestyle contributes to both conditions: excessive soda consumption, salt intake, lackof exercise, and irregular medication adherence.",
        "plan": "1. Increase amlodipine from 5 mg daily to 10 mg daily once daily (morning). 2. Increase metformin from 500mg twice daily to 1 gram with breakfast and 500mg in the evening. 3. Stop ibuprofen due to potential kidney strain and blood pressure elevation. 4. Blood tests: HbA1c, kidney function (creatinine and electrolytes), lipid profile, urine protein. 5. Eye exam referral. 6. ECG today. 7. Lifestyle modifications: Cut soda completely, reduce sugar in tea, drink water, reduce salt intake, grill fish instead of frying, walk for at least 30 minutes five days a week, limit beer to one on Saturdays, and check feet daily. 8. Patient should keep a diary of home blood pressure and morning blood sugar for two weeks. 9. Follow-up appointment in two weeks or sooner if severe headache, vomiting,vision loss, chest pain, weakness, or confusion occur. 10. Wife to attend follow up appointments.",
    }
)

GOOD_LONG_670 = json.dumps(
    {
        "subjective": "The patient reports headaches almost every evening for three weeks. The headaches are described as heavy and pressing at the back of the head and sometimes across the forehead. They are not sharp. Paracetamol helps a little. Stress and skipping lunch worsen them. Patient experiences blurry vision in the evening, but it clears. No vomiting or weakness. Experiences increased thirst and waking to urinate two times per night. Reports weight loss of 2-3 kg over two months. Experiences tingling/pins and needles in both feet, worse at night, for about two months. The patient is taking amlodipine five milligrams once daily and metformin five hundred milligrams twice daily with meals. Patient checks blood pressure at home, reading one fifty over ninety and one forty-eight over ninety-two last week. Random blood sugar is around nine to ten in the morning before eating and twelve after meals. Experiences ankle swelling. The patient states that she has a glucometer. She drinks one or two sodas daily. Patient reports family history of diabetes, stroke (father), high blood pressure (mother), and diabetes (brother). The patient denies smoking and drinks 2-3 beers on Saturdays. Patient does not exercise regularly. Patient is in mood but worried about healthand work. Patient has been taking ibuprofen three times a week for the headache.",
        "objective": "Blood pressure: one fifty-two over ninety-four, one forty-eight over ninety-two. Pulse: seventy-eight bpm. Weight: eighty-two kg (loss of 3kg). Temperature: normal. Heart sounds: normal.Chest: clear. Abdomen: soft, no tenderness. Ankle swelling: mild pitting at both ankles. Feet: intact skin, no ulcers. Pulses present in feet. Reduced sensation on the soles of both feet and toes. Reduced ankle reflexes. Random blood sugar: eleven point two mmol/L. Patient reports that she has a glucometer.",
        "assessment": "The patient presents with headaches likely related to uncontrolled hypertension and possibly diabetic neuropathy. Poor lifestyle choices contribute to elevated blood pressure and glucose levels. The patient's symptoms suggest possible diabetes, hypertension, and peripheral neuropathy. Medication adherence is suboptimal for both amlodipine and metformin. Patient reports ankle swelling which may be due to amlodipine.",
        "plan": "Increase amlodipine to ten milligrams once daily with breakfast. Increase metformin to one gramin the morning and five hundred milligrams in the evening with meals. Stop ibuprofen use. Order glycated hemoglobin, kidney function (creatinine and electrolytes), lipid profile, urine protein test, and ECG. Refer patient to eye clinic for examination. Advise patient to cut soda completely and reduce sugar intake. Encourage reduced salt consumption and grilled fish instead of fried. Recommend thirty minutes of walking at least five days a week. Limit beer to one on Saturdays. Instruct patient to monitor home blood pressure and morning glucose levels for two weeks, bringing results next visit. Patient should keep a diary of her home blood pressure and morning sugar for the next two weeks and bring it with you. Advise patient to check feet daily and wear closed shoes. Schedule follow-up appointment in two weeks or sooner if severe headache, vomiting, vision loss, chest pain, weakness, or confusion occur. Wife is welcome at appointments.",
    }
)

GOOD_SHORT = json.dumps(
    {
        "subjective": "Patient reports fever for three days, headache, chills, joint pain, and one episode of vomiting. Patient takes paracetamol twice daily.",
        "objective": "Temperature 38.6, pulse 96, blood pressure 118/76. Throat normal, chest clear, abdomen soft with mild tenderness under the ribs on the right. Patient appears tired but alert.",
        "assessment": "Possible viral illness. Malaria and full blood count ordered.",
        "plan": "Continue paracetamol, drink plenty of fluids, and rest. Return in two days with results. Seek immediate medical attention if vomiting is frequent, patient becomes confused, or fever worsens.",
    }
)

# The start of the output that never ended (no repetition penalty, long consultation).
LOOP_HEAD = (
    '{"subjective": "Patient reports headaches, worse in the evening, at the back of the head and '
    "sometimes across the forehead. Headaches are made worse by stress and skipping lunch. Patient "
    "takes amlodipine and metformin inconsistently. Patient reports occasional blurred vision, "
    "thirst, and nighttime urination. Patient reports tingling in the feet, worse at night. Patient "
    "reports a slight weight loss and ankle swelling. Patient reports a family history of "
    "diabetes, hypertension, and stroke. Patient reports mood is okay, but worried about health "
    "and work. Patient reports no chest pain, palpitations, or shortness of breath. Patient reports "
    "no numbness, tingling, or burning in the hands or legs. Patient reports no wounds or sores on "
    "the feet. Patient reports no chest pain, palpitations, or shortness of breath. Patient reports "
    "no swelling of the legs or face. Patient reports a normal mood and sleep, but with headaches "
    "and nighttime urination. Patient reports a desire to cut soda and reduce sugar in tea. Patient "
    "reports a desire to walk more and reduce beer consumption. Patient reports a family history of "
    "diabetes, hypertension, and stroke. Patient reports no allergies. Patient reports no "
)
