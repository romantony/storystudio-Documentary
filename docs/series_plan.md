# Series plan: "Wars That Shaped the World"

**Premise.** One war per episode, from antiquity to the Cold War. Each episode asks the same question: *what did this war change that is still with us?* Episode 1 is the WWI video already produced, so every later episode is built to match it.

**Format (fixed, so the pipeline is reusable)**
- 8 to 10 minutes, about 1,300 words of narration (the TTS pace measured 2.5 words/second when no style prefix is sent)
- Structure: cold open (the spark) → the world before → causes → course in three beats → consequences → "what we still live with"
- Same voice, same caption style (centred, word highlight), same thumbnail template (real archival image + two-line coloured title)
- Mid-roll call to action at about 50% and an end card that names the next episode

## Season 1: proposed release order

| # | Working title | Era | Impact on history (the episode's thesis) | Visual sources |
|---|---|---|---|---|
| 1 | How One Assassination Started World War I | 1914-18 | The alliance system turned a local crisis into a continental war and ended four empires | Done: Wikimedia Commons photos (public domain) |
| 2 | The Man Who Redrew Europe | Napoleonic Wars, 1803-15 | Nationalism, modern legal codes, and the balance-of-power order that the 1914 alliances grew out of | Paintings, engravings, maps (Commons, Met and Rijksmuseum open access) |
| 3 | The War That Ended Slavery | American Civil War, 1861-65 | First industrial war; abolition; a stronger federal state | Library of Congress photographs (public domain) |
| 4 | Why the Peace Failed | World War II, 1939-45 | Reordered the world; UN, decolonisation, nuclear age | NARA / IWM archive photos; check each film licence |
| 5 | Rome vs Carthage | Punic Wars, 264-146 BC | Rome becomes the Mediterranean power | Busts, mosaics, maps, engravings |
| 6 | The Empire That Connected Asia and Europe | Mongol conquests, 1206-1368 | Trade routes, ideas, and the spread of disease along them | Manuscripts and miniatures (Commons) |
| 7 | The War That Invented Sovereignty | Thirty Years' War, 1618-48 | Peace of Westphalia: the modern state system | Engravings (Callot etc.), maps |
| 8 | The War That Made France and England | Hundred Years' War, 1337-1453 | National identity, professional armies | Illuminated manuscripts |
| 9 | The First World War (Before WWI) | Seven Years' War, 1756-63 | A global conflict that expanded the British empire and set up the American Revolution | Paintings, maps |
| 10 | Democracy at War | Peloponnesian War, 431-404 BC | Athens vs Sparta; the "Thucydides trap" idea | Sculpture, vase art |
| 11 | Faith, Trade and Conquest | Crusades, 1095-1291 | Lasting contact between Europe and the Middle East | Manuscripts, castles |
| 12 | The War Nobody Won | Korea / Vietnam (Cold War proxy wars) | Superpower rivalry fought through other countries | NARA photos; check licences |

Release order alternates modern and ancient so new viewers from the WWI video get a related episode next (Napoleon), then a very different era.

## Production notes from episode 1 (carry forward)
1. **Do not prefix the TTS text with a style instruction.** The model reads it aloud. Episode 1 narration shrank from 764 s to 525 s once fixed.
2. **Captions:** Whisper on Replicate gives word timestamps; align them to the script text, not the transcription.
3. **Period imagery:** Storyblocks has almost no WWI-era material. Use Wikimedia Commons / Library of Congress / NARA for archival images and keep Storyblocks for abstract inserts (clock, fire, chess).
4. **Pre-photographic eras (episodes 2, 5 to 11):** use paintings, engravings, manuscripts and maps, which are largely public domain; check each licence before use.
5. Keep a `verify` flag on any date, number or causal claim in the script and check it before publishing.

## Channel setup
- One playlist for the series; each description links the previous and next episode
- Title pattern: "How X Changed the World" (or the working titles above); thumbnail text at most 4 words
- Weekly cadence is realistic with the existing pipeline (about half a day per episode including review)
- Pinned comment each time asks a "what would you have done" question
