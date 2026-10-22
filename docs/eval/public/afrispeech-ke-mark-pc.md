# AfriSpeech-200, Kenyan speakers: 631 clips, Whisper small

Dataset: AfriSpeech-200 (Olatunji et al., TACL 2023; Intron Health), CC BY-NC-SA 4.0, https://huggingface.co/datasets/intronhealth/afrispeech-200. The dataset is not stored in this repository; only these
scores are. Machine: 12 logical CPUs, 7.9 GB RAM, 0.5 GB free at the start.

Word error rate is total errors divided by total reference words (so long clips count more), after the same normalising as the other speech tests (numbers as digits, standard spellings).

Each WER cell shows two numbers: raw / with spoken punctuation removed. Many readers said the punctuation aloud ("comma", "full stop"), which the reference transcripts leave out, so Whisper's correct transcription of those words counts as errors in the first number.

| Accent | Clips | Minutes | WER, all | WER, clinical | WER, general |
|---|---|---|---|---|---|
| kikuyu | 27 | 4.4 | 0.263 / 0.162 | 0.302 / 0.201 | 0.196 / 0.095 |
| kiswahili | 16 | 1.8 | 0.295 / 0.181 | 0.301 / 0.184 | 0.000 / 0.000 |
| luhya | 82 | 15.1 | 0.384 / 0.301 | 0.383 / 0.301 | 0.391 / 0.298 |
| meru | 10 | 1.9 | 0.237 / 0.156 | - / - | 0.237 / 0.156 |
| swahili | 496 | 76.4 | 0.282 / 0.188 | 0.293 / 0.189 | 0.274 / 0.188 |
| **all Kenyan** | 631 | 99.6 | **0.293 / 0.200** | 0.314 / 0.216 | 0.274 / 0.187 |

## The ten hardest clips

| Accent | Domain | WER | Said | Heard |
|---|---|---|---|---|
| luhya | clinical | 2.0 | palms forwardd. | Palms for the post-op |
| luhya | general | 2.0 | Makeup: @nickbarose | Makeup Full Column Atnique Barrow |
| swahili | clinical | 1.8333 | In general,phagocytosisisawayofkeepingthetissuesfreeofdebris and infectious microbes. | In general, phagocytosis is a way of keeping the tissues free of debris and infectious microbes. |
| luhya | clinical | 1.6667 | Avoid moving thesyringe. | Avoid moving the C-Range. Don't stop. |
| swahili | clinical | 1.5 | exocytosis 17. | Exorcitosis 17, full stop. |
| kikuyu | clinical | 1.5 | Stable cells. | Stimbo cells full stop |
| swahili | clinical | 1.3333 | Disease like tuberculosis, syphilis, midlinegranuloma, atrophic rhinitis, and lupusvulgaris. | This is like tuberculosis comma, syphilis comma, midline granuloma comma, atrophic rhinitis comma, and lupus vulgaris full stop. |
| swahili | general | 1.2857 | A voice commands Simon Peter to eat. | I've always come much same on Peter to eat. Will you stop? |
| luhya | clinical | 1.2 | Medication administration throughenteral feeding tubes. | Medication and demonstration through internal feeding tubes, full stop. |
| luhya | general | 1.1667 | Vince had an uninspired art career. | This has inspired our career for us. |

Accent groups are as labelled by the dataset; some groups have few speakers, so their numbers say little on their own. The example sentences above are quoted from AfriSpeech-200 under CC BY-NC-SA 4.0; the full set of sentences is not in this repository.

Some reference transcripts in the dataset have their own errors: words run together ("phagocytosisisawayof"), typing slips ("forwardd", "thesyringe") and text that was not read as written ("@nickbarose"). A correct transcription of such a clip still counts as errors, so the true word error rate is somewhat lower than shown. The ten hardest clips above show both kinds: real mistakes by Whisper, and faults in the reference.
