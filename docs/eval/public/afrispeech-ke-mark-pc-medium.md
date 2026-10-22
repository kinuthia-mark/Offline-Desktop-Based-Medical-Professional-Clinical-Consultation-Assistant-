# AfriSpeech-200, Kenyan speakers: 631 clips, Whisper medium

Dataset: AfriSpeech-200 (Olatunji et al., TACL 2023; Intron Health), CC BY-NC-SA 4.0, https://huggingface.co/datasets/intronhealth/afrispeech-200. The dataset is not stored in this repository; only these
scores are. Machine: 12 logical CPUs, 7.9 GB RAM, 0.5 GB free at the start.

Word error rate is total errors divided by total reference words (so long clips count more), after the same normalising as the other speech tests (numbers as digits, standard spellings).

Each WER cell shows two numbers: raw / with spoken punctuation removed. Many readers said the punctuation aloud ("comma", "full stop"), which the reference transcripts leave out, so Whisper's correct transcription of those words counts as errors in the first number.

| Accent | Clips | Minutes | WER, all | WER, clinical | WER, general |
|---|---|---|---|---|---|
| kikuyu | 27 | 4.4 | 0.237 / 0.136 | 0.274 / 0.181 | 0.173 / 0.060 |
| kiswahili | 16 | 1.8 | 0.200 / 0.090 | 0.204 / 0.092 | 0.000 / 0.000 |
| luhya | 82 | 15.1 | 0.346 / 0.252 | 0.351 / 0.259 | 0.311 / 0.199 |
| meru | 10 | 1.9 | 0.185 / 0.114 | - / - | 0.185 / 0.114 |
| swahili | 496 | 76.4 | 0.235 / 0.152 | 0.254 / 0.158 | 0.222 / 0.148 |
| **all Kenyan** | 631 | 99.6 | **0.248 / 0.162** | 0.276 / 0.180 | 0.222 / 0.145 |

## The ten hardest clips

| Accent | Domain | WER | Said | Heard |
|---|---|---|---|---|
| swahili | clinical | 2.0 | exocytosis 17. | Exocetrust is 17, full stop. |
| luhya | general | 2.0 | Makeup: @nickbarose | Makeup, full colon, ethnic, barrels. |
| swahili | clinical | 1.8333 | In general,phagocytosisisawayofkeepingthetissuesfreeofdebris and infectious microbes. | In general, phagocytosis is a way of keeping the tissues free of debris and infectious microbes. |
| luhya | clinical | 1.6667 | Avoid moving thesyringe. | Avoid moving the C range, don't stop. |
| swahili | clinical | 1.5 | Magnesium mg 100ml 2225. | magnesium, milligrams, 100 milliliters, 2,225, full stop. |
| kikuyu | clinical | 1.5 | Stable cells. | Stembo cells full stop |
| swahili | clinical | 1.3333 | Disease like tuberculosis, syphilis, midlinegranuloma, atrophic rhinitis, and lupusvulgaris. | This is like tuberculosis coma, syphilis coma, midline granuloma coma, atrophic rhinitis coma, and lupus vulgaris full stop. |
| swahili | clinical | 1.25 | SUPPORT RESP NEEDS.ENC INDEPENDANCE. | supports, risks, needs and independence. |
| swahili | clinical | 1.1429 | 06 May 1986 1: 54 PM BILAT LOWER EXT VEINS Reason: eval for DVT Admitting Diagnosis: FAILURE TO THRIVE PANCREATIC CANCER | Since May 19th, since 1.54 p.m. by the time lower external days within column are valid for dbt Even though them to process admitting diagnosis column we just try pancreatic cancer |
| swahili | clinical | 1.125 | UO 3cc/kg/hr this shift no stool. | You owe three cc per kg per hour this shift nose tool. |

Accent groups are as labelled by the dataset; some groups have few speakers, so their numbers say little on their own. The example sentences above are quoted from AfriSpeech-200 under CC BY-NC-SA 4.0; the full set of sentences is not in this repository.

Some reference transcripts in the dataset have their own errors: words run together ("phagocytosisisawayof"), typing slips ("forwardd", "thesyringe") and text that was not read as written ("@nickbarose"). A correct transcription of such a clip still counts as errors, so the true word error rate is somewhat lower than shown. The ten hardest clips above show both kinds: real mistakes by Whisper, and faults in the reference.
